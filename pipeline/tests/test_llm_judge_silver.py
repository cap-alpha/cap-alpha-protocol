"""
Tests for pipeline/src/resolvers/llm_judge_silver.py (Issue #1129 Slice 2).

The LLM provider is always mocked (MagicMock) -- no real network calls in
this file, mirroring test_llm_judge.py's approach for the gold-layer LLM
judge. DB access for evidence retrieval uses an in-memory DuckDB connection
wrapped in a minimal adapter, mirroring test_silver_v2_resolver.py's
approach for the same silver_v2_claims schema family (scoped down here to
just the `claim` and `raw_utterance` tables that retrieve_evidence_snippets
actually touches).
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import duckdb
import pandas as pd
import pytest

from src.resolvers.llm_judge_silver import (
    CONFIDENCE_THRESHOLD,
    LLM_JUDGE_METHOD_ADAPTER_PATH,
    LLM_JUDGE_METHOD_DATA_SOURCE,
    LLM_JUDGE_METHOD_DOMAIN,
    LLM_JUDGE_METHOD_ID,
    LLM_JUDGE_METHOD_NAME,
    LLMJudgeResolutionMethod,
    _extract_keywords,
    _parse_llm_response,
    _serialise_snippet,
    ensure_llm_judge_resolution_method,
    retrieve_evidence_snippets,
)

NOW = datetime(2026, 7, 27, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# In-memory DuckDB fixture (claim.asserted_at + raw_utterance only)
# ---------------------------------------------------------------------------

_DDL = """
CREATE SCHEMA IF NOT EXISTS silver_v2_claims;

CREATE TABLE IF NOT EXISTS silver_v2_claims.claim (
    claim_id     VARCHAR NOT NULL,
    asserted_at  TIMESTAMP
);

CREATE TABLE IF NOT EXISTS silver_v2_claims.raw_utterance (
    utterance_id   VARCHAR NOT NULL,
    text           VARCHAR NOT NULL,
    uttered_at     TIMESTAMP NOT NULL,
    source_doc_id  VARCHAR
);

CREATE TABLE IF NOT EXISTS silver_v2_claims.resolution_method (
    resolution_method_id VARCHAR NOT NULL,
    domain                 VARCHAR NOT NULL,
    name                    VARCHAR NOT NULL,
    adapter_path            VARCHAR NOT NULL,
    data_source             VARCHAR NOT NULL,
    config                   JSON
);
"""


def _naive_utc(dt: datetime | None) -> datetime | None:
    """Strip tzinfo after normalising to UTC -- DuckDB's Python binding
    silently converts tz-aware datetimes bound via `?` to the local system
    timezone when the destination column is a naive TIMESTAMP. See
    test_silver_v2_resolver.py's identical helper for the full rationale."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _substitute(query: str, query_parameters) -> str:
    """Translate BigQuery @param placeholders to DuckDB literals."""
    if not query_parameters:
        return query
    for p in query_parameters:
        value = p.value
        if value is None:
            literal = "NULL"
        elif isinstance(value, bool):
            literal = "TRUE" if value else "FALSE"
        elif isinstance(value, str):
            literal = "'" + value.replace("'", "''") + "'"
        elif isinstance(value, datetime):
            literal = "TIMESTAMP '" + value.strftime("%Y-%m-%d %H:%M:%S.%f") + "'"
        else:
            literal = str(value)
        query = re.sub(rf"@{re.escape(p.name)}\b", literal, query)
    return query


class _InMemoryDB:
    def __init__(self, conn):
        self._conn = conn

    def fetch_df(self, query: str, query_parameters=None, **kwargs) -> pd.DataFrame:
        return self._conn.execute(_substitute(query, query_parameters)).df()

    def execute(self, query: str, query_parameters=None, **kwargs):
        return self._conn.execute(_substitute(query, query_parameters))

    def append_dataframe_to_table(self, df: pd.DataFrame, table_name: str) -> None:
        parts = table_name.split(".")
        ref = ".".join(parts[-2:]) if len(parts) >= 2 else table_name
        cols = ", ".join(f'"{c}"' for c in df.columns)
        view = f"__tmp_{uuid.uuid4().hex[:6]}"
        self._conn.register(view, df)
        try:
            self._conn.execute(f"INSERT INTO {ref} ({cols}) SELECT {cols} FROM {view}")
        finally:
            self._conn.unregister(view)


@pytest.fixture
def db():
    conn = duckdb.connect(":memory:")
    for stmt in _DDL.split(";"):
        stmt = stmt.strip()
        if stmt:
            conn.execute(stmt)
    yield _InMemoryDB(conn)
    conn.close()


def _seed_claim(db: _InMemoryDB, claim_id: str, asserted_at: datetime | None) -> None:
    db._conn.execute(
        "INSERT INTO silver_v2_claims.claim (claim_id, asserted_at) VALUES (?, ?)",
        [claim_id, _naive_utc(asserted_at)],
    )


def _seed_utterance(
    db: _InMemoryDB,
    utterance_id: str,
    text: str,
    uttered_at: datetime,
    source_doc_id: str = "doc-1",
) -> None:
    db._conn.execute(
        "INSERT INTO silver_v2_claims.raw_utterance "
        "(utterance_id, text, uttered_at, source_doc_id) VALUES (?, ?, ?, ?)",
        [utterance_id, text, _naive_utc(uttered_at), source_doc_id],
    )


# ---------------------------------------------------------------------------
# _extract_keywords
# ---------------------------------------------------------------------------


class TestExtractKeywords:
    def test_combines_speaker_and_subjects(self):
        claim = {
            "speaker_name": "Adam Schefter",
            "subject_entity_names": "Patrick Mahomes, Kansas City Chiefs",
        }
        keywords = _extract_keywords(claim)
        assert keywords == ["Adam Schefter", "Patrick Mahomes", "Kansas City Chiefs"]

    def test_no_entity_data_returns_empty(self):
        assert _extract_keywords({}) == []
        assert (
            _extract_keywords({"speaker_name": None, "subject_entity_names": None})
            == []
        )

    def test_dedupes_case_insensitively(self):
        claim = {
            "speaker_name": "Patrick Mahomes",
            "subject_entity_names": "patrick mahomes, Travis Kelce",
        }
        keywords = _extract_keywords(claim)
        assert keywords == ["Patrick Mahomes", "Travis Kelce"]

    def test_filters_trivial_short_names(self):
        claim = {"speaker_name": "Al", "subject_entity_names": "KC"}
        assert _extract_keywords(claim) == []


# ---------------------------------------------------------------------------
# retrieve_evidence_snippets
# ---------------------------------------------------------------------------


class TestRetrieveEvidenceSnippets:
    def test_no_keywords_returns_empty_without_querying_db(self):
        db = MagicMock()
        result = retrieve_evidence_snippets(db, {"claim_id": "c1"}, top_k=5)
        assert result == []
        db.fetch_df.assert_not_called()

    def test_missing_asserted_at_returns_empty(self, db):
        # claim not seeded at all -> asserted_at lookup finds nothing
        claim = {
            "claim_id": "claim-ghost",
            "speaker_name": "Adam Schefter",
            "subject_entity_names": None,
        }
        assert retrieve_evidence_snippets(db, claim, top_k=5) == []

    def test_excludes_utterances_before_asserted_at(self, db):
        _seed_claim(db, "claim-1", asserted_at=NOW - timedelta(days=10))
        _seed_utterance(
            db,
            "utt-old",
            "Patrick Mahomes wins MVP",
            uttered_at=NOW - timedelta(days=20),
        )
        claim = {
            "claim_id": "claim-1",
            "speaker_name": None,
            "subject_entity_names": "Patrick Mahomes",
        }
        assert retrieve_evidence_snippets(db, claim, top_k=5) == []

    def test_excludes_non_matching_text(self, db):
        _seed_claim(db, "claim-1", asserted_at=NOW - timedelta(days=10))
        _seed_utterance(
            db,
            "utt-nomatch",
            "The Eagles signed a new kicker",
            uttered_at=NOW - timedelta(days=1),
        )
        claim = {
            "claim_id": "claim-1",
            "speaker_name": None,
            "subject_entity_names": "Patrick Mahomes",
        }
        assert retrieve_evidence_snippets(db, claim, top_k=5) == []

    def test_matches_and_orders_most_recent_first(self, db):
        _seed_claim(db, "claim-1", asserted_at=NOW - timedelta(days=10))
        _seed_utterance(
            db, "utt-a", "Patrick Mahomes named MVP", uttered_at=NOW - timedelta(days=3)
        )
        _seed_utterance(
            db,
            "utt-b",
            "Patrick Mahomes confirmed as league MVP",
            uttered_at=NOW - timedelta(days=1),
        )
        claim = {
            "claim_id": "claim-1",
            "speaker_name": "Adam Schefter",
            "subject_entity_names": "Patrick Mahomes",
        }
        rows = retrieve_evidence_snippets(db, claim, top_k=5)
        assert [r["utterance_id"] for r in rows] == ["utt-b", "utt-a"]

    def test_respects_top_k(self, db):
        _seed_claim(db, "claim-1", asserted_at=NOW - timedelta(days=10))
        for i in range(5):
            _seed_utterance(
                db,
                f"utt-{i}",
                "Patrick Mahomes update",
                uttered_at=NOW - timedelta(days=i),
            )
        claim = {
            "claim_id": "claim-1",
            "speaker_name": None,
            "subject_entity_names": "Patrick Mahomes",
        }
        rows = retrieve_evidence_snippets(db, claim, top_k=2)
        assert len(rows) == 2

    def test_matches_on_speaker_name_too(self, db):
        _seed_claim(db, "claim-1", asserted_at=NOW - timedelta(days=10))
        _seed_utterance(
            db,
            "utt-a",
            "Adam Schefter reports a trade",
            uttered_at=NOW - timedelta(days=1),
        )
        claim = {
            "claim_id": "claim-1",
            "speaker_name": "Adam Schefter",
            "subject_entity_names": None,
        }
        rows = retrieve_evidence_snippets(db, claim, top_k=5)
        assert [r["utterance_id"] for r in rows] == ["utt-a"]


# ---------------------------------------------------------------------------
# _serialise_snippet
# ---------------------------------------------------------------------------


class TestSerialiseSnippet:
    def test_datetime_becomes_iso_string(self):
        snippet = {
            "utterance_id": "u1",
            "text": "hello",
            "uttered_at": NOW,
            "source_doc_id": "doc-1",
        }
        out = _serialise_snippet(snippet)
        assert out["uttered_at"] == NOW.isoformat()
        # Must be JSON serialisable end to end.
        json.dumps(out)

    def test_text_truncated(self):
        snippet = {
            "utterance_id": "u1",
            "text": "x" * 5000,
            "uttered_at": NOW,
            "source_doc_id": "doc-1",
        }
        out = _serialise_snippet(snippet)
        assert len(out["text"]) == 1000


# ---------------------------------------------------------------------------
# _parse_llm_response
# ---------------------------------------------------------------------------


class TestParseLLMResponse:
    def test_valid_true_verdict(self):
        raw = json.dumps(
            {"verdict": "TRUE", "confidence": 0.9, "reasoning": "It happened."}
        )
        parsed = _parse_llm_response(raw)
        assert parsed == {
            "verdict": "TRUE",
            "confidence": 0.9,
            "reasoning": "It happened.",
        }

    def test_strips_markdown_fences(self):
        raw = (
            '```json\n{"verdict": "FALSE", "confidence": 0.8, "reasoning": "No."}\n```'
        )
        parsed = _parse_llm_response(raw)
        assert parsed["verdict"] == "FALSE"

    def test_lowercase_verdict_normalised(self):
        raw = json.dumps({"verdict": "void", "confidence": 0.7, "reasoning": "moot"})
        parsed = _parse_llm_response(raw)
        assert parsed["verdict"] == "VOID"

    def test_confidence_clamped(self):
        raw = json.dumps({"verdict": "TRUE", "confidence": 5.0, "reasoning": "x"})
        assert _parse_llm_response(raw)["confidence"] == 1.0
        raw = json.dumps({"verdict": "TRUE", "confidence": -5.0, "reasoning": "x"})
        assert _parse_llm_response(raw)["confidence"] == 0.0

    def test_reasoning_truncated(self):
        raw = json.dumps(
            {"verdict": "TRUE", "confidence": 0.9, "reasoning": "x" * 1000}
        )
        assert len(_parse_llm_response(raw)["reasoning"]) == 500

    def test_empty_response_returns_none(self):
        assert _parse_llm_response("") is None
        assert _parse_llm_response(None) is None

    def test_non_json_returns_none(self):
        assert _parse_llm_response("sorry, I cannot help with that") is None

    def test_json_array_returns_none(self):
        assert _parse_llm_response("[1, 2, 3]") is None

    def test_unrecognised_verdict_returns_none(self):
        raw = json.dumps({"verdict": "MAYBE", "confidence": 0.5, "reasoning": "?"})
        assert _parse_llm_response(raw) is None

    def test_missing_verdict_key_returns_none(self):
        raw = json.dumps({"confidence": 0.9, "reasoning": "no verdict field"})
        assert _parse_llm_response(raw) is None

    def test_extracts_json_object_embedded_in_prose(self):
        raw = (
            'Sure, here is my answer: {"verdict": "TRUE", "confidence": 0.75, '
            '"reasoning": "clear evidence"} -- hope that helps!'
        )
        parsed = _parse_llm_response(raw)
        assert parsed is not None
        assert parsed["verdict"] == "TRUE"


# ---------------------------------------------------------------------------
# ensure_llm_judge_resolution_method
# ---------------------------------------------------------------------------


class TestEnsureLLMJudgeResolutionMethod:
    def test_inserts_and_is_idempotent(self, db):
        assert ensure_llm_judge_resolution_method(db) is True
        assert ensure_llm_judge_resolution_method(db) is False
        rows = db._conn.execute(
            f"SELECT * FROM silver_v2_claims.resolution_method "
            f"WHERE resolution_method_id = '{LLM_JUDGE_METHOD_ID}'"
        ).df()
        assert len(rows) == 1
        assert rows.iloc[0]["domain"] == LLM_JUDGE_METHOD_DOMAIN
        assert rows.iloc[0]["name"] == LLM_JUDGE_METHOD_NAME
        assert rows.iloc[0]["adapter_path"] == LLM_JUDGE_METHOD_ADAPTER_PATH
        assert rows.iloc[0]["data_source"] == LLM_JUDGE_METHOD_DATA_SOURCE


# ---------------------------------------------------------------------------
# LLMJudgeResolutionMethod.resolve()
# ---------------------------------------------------------------------------


def _mock_provider(response_text: str, model: str = "gemini-2.5-flash"):
    provider = MagicMock()
    provider.classify.return_value = response_text
    provider.model = model
    return provider


BASE_CLAIM = {
    "claim_id": "claim-1",
    "claim_text": "Patrick Mahomes will win NFL MVP",
    "speaker_name": "Adam Schefter",
    "subject_entity_names": "Patrick Mahomes",
}


class TestLLMJudgeResolutionMethodResolve:
    def test_defers_when_claim_text_missing(self):
        db = MagicMock()
        provider = _mock_provider("irrelevant")
        method = LLMJudgeResolutionMethod(db=db, provider=provider)
        claim = dict(BASE_CLAIM, claim_text="")
        assert method.resolve(claim) is None
        db.fetch_df.assert_not_called()
        provider.classify.assert_not_called()

    def test_defers_when_no_evidence_found(self, db):
        _seed_claim(db, "claim-1", asserted_at=NOW - timedelta(days=10))
        # No raw_utterance rows seeded at all.
        provider = _mock_provider("irrelevant")
        method = LLMJudgeResolutionMethod(db=db, provider=provider)
        assert method.resolve(BASE_CLAIM) is None
        provider.classify.assert_not_called()

    def test_returns_true_on_clear_evidence(self, db):
        _seed_claim(db, "claim-1", asserted_at=NOW - timedelta(days=10))
        _seed_utterance(
            db,
            "utt-1",
            "Patrick Mahomes was officially named NFL MVP on Sunday.",
            uttered_at=NOW - timedelta(days=1),
        )
        provider = _mock_provider(
            json.dumps(
                {
                    "verdict": "TRUE",
                    "confidence": 0.92,
                    "reasoning": "Evidence #1 confirms the MVP win.",
                }
            )
        )
        method = LLMJudgeResolutionMethod(db=db, provider=provider)
        result = method.resolve(BASE_CLAIM)
        assert result is not None
        outcome, confidence, evidence, notes = result
        assert outcome == "true"
        assert confidence == 0.92
        assert "MVP" in notes
        # evidence must be JSON-serialisable and carry the retrieved snippet.
        json.dumps(evidence)
        assert evidence["llm_verdict"] == "TRUE"
        assert evidence["provider_model"] == "gemini-2.5-flash"
        assert len(evidence["snippets"]) == 1
        assert evidence["snippets"][0]["utterance_id"] == "utt-1"

    def test_returns_false_on_clear_contradicting_evidence(self, db):
        _seed_claim(db, "claim-1", asserted_at=NOW - timedelta(days=10))
        _seed_utterance(
            db,
            "utt-1",
            "Patrick Mahomes finished third in NFL MVP voting.",
            uttered_at=NOW - timedelta(days=1),
        )
        provider = _mock_provider(
            json.dumps(
                {"verdict": "FALSE", "confidence": 0.88, "reasoning": "He did not win."}
            )
        )
        method = LLMJudgeResolutionMethod(db=db, provider=provider)
        result = method.resolve(BASE_CLAIM)
        assert result is not None
        outcome, confidence, evidence, notes = result
        assert outcome == "false"
        assert confidence == 0.88

    def test_void_verdict_maps_to_vacuous_outcome(self, db):
        _seed_claim(db, "claim-1", asserted_at=NOW - timedelta(days=10))
        _seed_utterance(
            db,
            "utt-1",
            "Patrick Mahomes announced his retirement, ending the MVP race question.",
            uttered_at=NOW - timedelta(days=1),
        )
        provider = _mock_provider(
            json.dumps(
                {
                    "verdict": "VOID",
                    "confidence": 0.8,
                    "reasoning": "Retired, claim moot.",
                }
            )
        )
        method = LLMJudgeResolutionMethod(db=db, provider=provider)
        outcome, confidence, evidence, notes = method.resolve(BASE_CLAIM)
        assert outcome == "vacuous"

    def test_defers_on_uncertain_verdict(self, db):
        _seed_claim(db, "claim-1", asserted_at=NOW - timedelta(days=10))
        _seed_utterance(
            db,
            "utt-1",
            "Patrick Mahomes played well this week.",
            uttered_at=NOW - timedelta(days=1),
        )
        provider = _mock_provider(
            json.dumps(
                {
                    "verdict": "UNCERTAIN",
                    "confidence": 0.5,
                    "reasoning": "Not enough info.",
                }
            )
        )
        method = LLMJudgeResolutionMethod(db=db, provider=provider)
        assert method.resolve(BASE_CLAIM) is None

    def test_defers_below_confidence_threshold(self, db):
        _seed_claim(db, "claim-1", asserted_at=NOW - timedelta(days=10))
        _seed_utterance(
            db,
            "utt-1",
            "Patrick Mahomes might be in MVP contention.",
            uttered_at=NOW - timedelta(days=1),
        )
        provider = _mock_provider(
            json.dumps(
                {"verdict": "TRUE", "confidence": 0.3, "reasoning": "Weak signal."}
            )
        )
        method = LLMJudgeResolutionMethod(
            db=db, provider=provider, confidence_threshold=CONFIDENCE_THRESHOLD
        )
        assert method.resolve(BASE_CLAIM) is None

    def test_defers_on_malformed_llm_response_no_crash(self, db):
        _seed_claim(db, "claim-1", asserted_at=NOW - timedelta(days=10))
        _seed_utterance(
            db,
            "utt-1",
            "Patrick Mahomes news update.",
            uttered_at=NOW - timedelta(days=1),
        )
        provider = _mock_provider("this is not json at all, sorry")
        method = LLMJudgeResolutionMethod(db=db, provider=provider)
        result = method.resolve(BASE_CLAIM)
        assert result is None

    def test_defers_on_llm_exception_no_crash(self, db):
        _seed_claim(db, "claim-1", asserted_at=NOW - timedelta(days=10))
        _seed_utterance(
            db,
            "utt-1",
            "Patrick Mahomes news update.",
            uttered_at=NOW - timedelta(days=1),
        )
        provider = MagicMock()
        provider.classify.side_effect = Exception("network error")
        provider.model = "gemini-2.5-flash"
        method = LLMJudgeResolutionMethod(db=db, provider=provider)
        result = method.resolve(BASE_CLAIM)
        assert result is None

    def test_method_id_defaults_to_registered_constant(self, db):
        method = LLMJudgeResolutionMethod(db=db, provider=_mock_provider("{}"))
        assert method.method_id == LLM_JUDGE_METHOD_ID

    def test_lazy_provider_not_constructed_when_explicit_provider_given(self, db):
        """Passing provider= explicitly must never touch get_provider()/env
        credentials -- this is what keeps these tests network-free."""
        provider = _mock_provider("{}")
        method = LLMJudgeResolutionMethod(db=db, provider=provider)
        assert method._get_provider() is provider
