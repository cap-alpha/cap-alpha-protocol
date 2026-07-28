"""
Tests for pipeline/src/matching/claim_index.py (Issue #1133 — Stage-1
retrieval funnel: claim embedding index + candidate retrieval).

Uses an in-memory DuckDB connection wrapped in a minimal DB adapter that
mirrors how the real DBManager is used (fetch_df/execute with `@param`
BigQuery-style query_parameters, append_dataframe_to_table) -- the same
approach pipeline/tests/test_silver_v2_resolver.py uses for the same
silver_v2_claims schema family. No BigQuery, no fastembed/ONNX model:
`src.matching.claim_index.embed_texts` is monkeypatched with a
deterministic fake so these tests never load the real embedding model.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone

import duckdb
import pandas as pd
import pytest

from src.matching.claim_index import (
    CLAIM_EMBEDDING_TABLE,
    build_claim_embeddings,
    retrieve_candidates,
)

# ---------------------------------------------------------------------------
# In-memory DuckDB fixture
# ---------------------------------------------------------------------------

_DDL = """
CREATE SCHEMA IF NOT EXISTS silver_v2_claims;

CREATE TABLE IF NOT EXISTS silver_v2_claims.claim (
    claim_id     VARCHAR NOT NULL,
    utterance_id VARCHAR
);

CREATE TABLE IF NOT EXISTS silver_v2_claims.raw_utterance (
    utterance_id VARCHAR NOT NULL,
    text         VARCHAR
);

CREATE TABLE IF NOT EXISTS silver_v2_claims.resolution (
    claim_id VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS silver_v2_claims.claim_embedding (
    claim_id    VARCHAR NOT NULL,
    embedding   DOUBLE[] NOT NULL,
    model_id    VARCHAR NOT NULL,
    embedded_at TIMESTAMP NOT NULL
);
"""


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
    """Minimal DB adapter wrapping an in-memory DuckDB connection, satisfying
    the interface claim_index.py expects: fetch_df/execute with
    BigQuery-style query_parameters, append_dataframe_to_table."""

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


NOW = datetime(2026, 7, 27, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


def _seed_claim(db: _InMemoryDB, claim_id: str, utterance_id: str | None) -> None:
    db._conn.execute(
        "INSERT INTO silver_v2_claims.claim (claim_id, utterance_id) VALUES (?, ?)",
        [claim_id, utterance_id],
    )


def _seed_utterance(db: _InMemoryDB, utterance_id: str, text: str | None) -> None:
    db._conn.execute(
        "INSERT INTO silver_v2_claims.raw_utterance (utterance_id, text) VALUES (?, ?)",
        [utterance_id, text],
    )


def _seed_resolution(db: _InMemoryDB, claim_id: str) -> None:
    db._conn.execute(
        "INSERT INTO silver_v2_claims.resolution (claim_id) VALUES (?)", [claim_id]
    )


def _seed_embedding(
    db: _InMemoryDB,
    claim_id: str,
    embedding: list[float],
    model_id: str = "test-model",
    embedded_at: datetime = NOW,
) -> None:
    db._conn.execute(
        "INSERT INTO silver_v2_claims.claim_embedding "
        "(claim_id, embedding, model_id, embedded_at) VALUES (?, ?, ?, ?)",
        [claim_id, embedding, model_id, embedded_at.replace(tzinfo=None)],
    )


def _claim_with_utterance(
    db: _InMemoryDB, claim_id: str, text: str, utterance_id: str | None = None
) -> None:
    utterance_id = utterance_id or f"utt-{claim_id}"
    _seed_utterance(db, utterance_id, text)
    _seed_claim(db, claim_id, utterance_id)


# ---------------------------------------------------------------------------
# Fake embedder for build_claim_embeddings tests
# ---------------------------------------------------------------------------


class _FakeEmbed:
    """Deterministic, order-preserving fake standing in for
    src.matching.embed.embed_texts: records every call's input texts and
    returns one fixed-length vector per text, derived from a hash of the
    text so identical texts always produce identical vectors."""

    def __init__(self):
        self.calls: list[list[str]] = []

    def __call__(self, texts, model_id="test-model"):
        self.calls.append(list(texts))
        vectors = []
        for t in texts:
            seed = sum(ord(c) for c in t) or 1
            vectors.append([((seed * (i + 1)) % 97) / 97.0 for i in range(4)])
        return vectors


@pytest.fixture
def fake_embed(monkeypatch):
    fake = _FakeEmbed()
    monkeypatch.setattr("src.matching.claim_index.embed_texts", fake)
    return fake


# ---------------------------------------------------------------------------
# build_claim_embeddings
# ---------------------------------------------------------------------------


class TestBuildClaimEmbeddings:
    def test_embeds_active_claims(self, db, fake_embed):
        _claim_with_utterance(db, "claim-1", "Mahomes will win MVP")
        _claim_with_utterance(db, "claim-2", "Chiefs miss the playoffs")

        summary = build_claim_embeddings(db, model_id="test-model", now=NOW)

        assert summary == {"checked": 2, "embedded": 2, "skipped": 0}
        rows = db._conn.execute(
            "SELECT claim_id, model_id FROM silver_v2_claims.claim_embedding "
            "ORDER BY claim_id"
        ).df()
        assert rows["claim_id"].tolist() == ["claim-1", "claim-2"]
        assert (rows["model_id"] == "test-model").all()

    def test_excludes_already_resolved_claims(self, db, fake_embed):
        _claim_with_utterance(db, "claim-resolved", "Old resolved claim")
        _seed_resolution(db, "claim-resolved")
        _claim_with_utterance(db, "claim-active", "Still-pending claim")

        summary = build_claim_embeddings(db, model_id="test-model", now=NOW)

        assert summary == {"checked": 1, "embedded": 1, "skipped": 0}
        rows = db._conn.execute(
            "SELECT claim_id FROM silver_v2_claims.claim_embedding"
        ).df()
        assert rows["claim_id"].tolist() == ["claim-active"]

    def test_second_build_is_idempotent_no_op(self, db, fake_embed):
        _claim_with_utterance(db, "claim-1", "Mahomes will win MVP")

        first = build_claim_embeddings(db, model_id="test-model", now=NOW)
        second = build_claim_embeddings(db, model_id="test-model", now=NOW)

        assert first == {"checked": 1, "embedded": 1, "skipped": 0}
        assert second == {"checked": 0, "embedded": 0, "skipped": 0}
        rows = db._conn.execute("SELECT * FROM silver_v2_claims.claim_embedding").df()
        assert len(rows) == 1
        # embed_texts was only called once -- the second run's anti-join
        # found nothing to embed, so it never even reached embed_texts.
        assert len(fake_embed.calls) == 1

    def test_new_claim_after_first_build_gets_embedded(self, db, fake_embed):
        _claim_with_utterance(db, "claim-1", "First claim")
        build_claim_embeddings(db, model_id="test-model", now=NOW)

        _claim_with_utterance(db, "claim-2", "Second claim, added later")
        summary = build_claim_embeddings(db, model_id="test-model", now=NOW)

        assert summary == {"checked": 1, "embedded": 1, "skipped": 0}
        rows = db._conn.execute(
            "SELECT claim_id FROM silver_v2_claims.claim_embedding ORDER BY claim_id"
        ).df()
        assert rows["claim_id"].tolist() == ["claim-1", "claim-2"]

    def test_new_model_id_reembeds_independently_of_old_rows(self, db, fake_embed):
        _claim_with_utterance(db, "claim-1", "Mahomes will win MVP")
        build_claim_embeddings(db, model_id="model-a", now=NOW)

        summary = build_claim_embeddings(db, model_id="model-b", now=NOW)

        assert summary == {"checked": 1, "embedded": 1, "skipped": 0}
        rows = db._conn.execute(
            "SELECT claim_id, model_id FROM silver_v2_claims.claim_embedding "
            "ORDER BY model_id"
        ).df()
        assert len(rows) == 2
        assert rows["model_id"].tolist() == ["model-a", "model-b"]
        # both rows still reference the same claim -- old model's row untouched
        assert (rows["claim_id"] == "claim-1").all()

    def test_skips_claims_with_missing_claim_text(self, db, fake_embed):
        # utterance_id points at a row that doesn't exist -> LEFT JOIN gives NULL text
        _seed_claim(db, "claim-dangling", utterance_id="missing-utterance")
        _claim_with_utterance(db, "claim-good", "A valid claim")

        summary = build_claim_embeddings(db, model_id="test-model", now=NOW)

        assert summary == {"checked": 2, "embedded": 1, "skipped": 1}
        rows = db._conn.execute(
            "SELECT claim_id FROM silver_v2_claims.claim_embedding"
        ).df()
        assert rows["claim_id"].tolist() == ["claim-good"]

    def test_empty_active_claim_set_returns_zeroed_summary(self, db, fake_embed):
        summary = build_claim_embeddings(db, model_id="test-model", now=NOW)
        assert summary == {"checked": 0, "embedded": 0, "skipped": 0}
        assert fake_embed.calls == []

    def test_embedded_at_shared_across_the_whole_batch(self, db, fake_embed):
        """All claims embedded in a single build_claim_embeddings() call must
        share the exact same injected `now` -- proves embedded_at comes from
        the injected `now` parameter (computed once) rather than
        datetime.now() called per-row.

        Compares rows to each other rather than to `NOW` directly: DuckDB's
        Python/Arrow binding silently converts tz-aware timestamps written
        via `register()`+`INSERT ... SELECT` (the append_dataframe_to_table
        path) to the *local system timezone* when the destination column is
        a naive TIMESTAMP -- see test_silver_v2_resolver.py's `_naive_utc`
        docstring for the same quirk on the `?`-param path. A relative
        (row-to-row) comparison sidesteps that entirely; it's portable
        across CI (UTC) and local dev (non-UTC) alike.
        """
        _claim_with_utterance(db, "claim-1", "First claim")
        _claim_with_utterance(db, "claim-2", "Second claim")
        build_claim_embeddings(db, model_id="test-model", now=NOW)
        rows = db._conn.execute(
            "SELECT embedded_at FROM silver_v2_claims.claim_embedding"
        ).df()
        assert rows["embedded_at"].nunique() == 1

    def test_defaults_now_to_wall_clock_when_not_provided(self, db, fake_embed):
        """now=None must not crash and must still populate embedded_at for
        every written row (exact wall-clock value isn't asserted here --
        see the batch-sharing test above for why cross-checking DuckDB's
        stored value against a Python-side datetime is unreliable across
        timezones)."""
        _claim_with_utterance(db, "claim-1", "Some claim")
        summary = build_claim_embeddings(db, model_id="test-model")
        assert summary == {"checked": 1, "embedded": 1, "skipped": 0}
        row = (
            db._conn.execute(
                "SELECT embedded_at FROM silver_v2_claims.claim_embedding "
                "WHERE claim_id = 'claim-1'"
            )
            .df()
            .iloc[0]
        )
        assert pd.notna(row["embedded_at"])


# ---------------------------------------------------------------------------
# retrieve_candidates
# ---------------------------------------------------------------------------


class TestRetrieveCandidates:
    def test_empty_index_returns_empty_list(self, db, fake_embed):
        result = retrieve_candidates(db, "some news event", k=5, model_id="test-model")
        assert result == []
        # embed_texts is never called when there's nothing to compare against
        assert fake_embed.calls == []

    def test_k_zero_or_negative_returns_empty_without_querying(self, db, fake_embed):
        _seed_embedding(db, "claim-1", [1.0, 0.0], model_id="test-model")
        assert retrieve_candidates(db, "event", k=0, model_id="test-model") == []
        assert retrieve_candidates(db, "event", k=-1, model_id="test-model") == []

    def test_ranks_by_cosine_similarity(self, db, monkeypatch):
        # Synthetic 2D vectors with known cosine relationships to [1, 0]:
        #   claim-parallel   [1, 0]   -> cosine 1.0
        #   claim-diagonal   [1, 1]   -> cosine ~0.707
        #   claim-orthogonal [0, 1]   -> cosine 0.0
        _seed_embedding(db, "claim-parallel", [1.0, 0.0], model_id="test-model")
        _seed_embedding(db, "claim-diagonal", [1.0, 1.0], model_id="test-model")
        _seed_embedding(db, "claim-orthogonal", [0.0, 1.0], model_id="test-model")

        monkeypatch.setattr(
            "src.matching.claim_index.embed_texts",
            lambda texts, model_id="test-model": [[1.0, 0.0]],
        )

        result = retrieve_candidates(db, "news event text", k=3, model_id="test-model")

        assert [claim_id for claim_id, _ in result] == [
            "claim-parallel",
            "claim-diagonal",
            "claim-orthogonal",
        ]
        scores = dict(result)
        assert scores["claim-parallel"] == pytest.approx(1.0)
        assert scores["claim-diagonal"] == pytest.approx(0.7071, abs=1e-3)
        assert scores["claim-orthogonal"] == pytest.approx(0.0, abs=1e-9)

    def test_respects_k(self, db, monkeypatch):
        for i in range(5):
            _seed_embedding(db, f"claim-{i}", [float(i), 1.0], model_id="test-model")
        monkeypatch.setattr(
            "src.matching.claim_index.embed_texts",
            lambda texts, model_id="test-model": [[1.0, 1.0]],
        )
        result = retrieve_candidates(db, "event", k=2, model_id="test-model")
        assert len(result) == 2

    def test_ties_broken_by_claim_id_ascending(self, db, monkeypatch):
        _seed_embedding(db, "claim-b", [1.0, 0.0], model_id="test-model")
        _seed_embedding(db, "claim-a", [1.0, 0.0], model_id="test-model")
        monkeypatch.setattr(
            "src.matching.claim_index.embed_texts",
            lambda texts, model_id="test-model": [[1.0, 0.0]],
        )
        result = retrieve_candidates(db, "event", k=2, model_id="test-model")
        assert [claim_id for claim_id, _ in result] == ["claim-a", "claim-b"]

    def test_filters_by_model_id(self, db, monkeypatch):
        _seed_embedding(db, "claim-a", [1.0, 0.0], model_id="model-a")
        _seed_embedding(db, "claim-b", [1.0, 0.0], model_id="model-b")
        monkeypatch.setattr(
            "src.matching.claim_index.embed_texts",
            lambda texts, model_id="model-a": [[1.0, 0.0]],
        )
        result = retrieve_candidates(db, "event", k=10, model_id="model-a")
        assert [claim_id for claim_id, _ in result] == ["claim-a"]

    def test_zero_vector_event_returns_empty_list(self, db, monkeypatch):
        _seed_embedding(db, "claim-1", [1.0, 0.0], model_id="test-model")
        monkeypatch.setattr(
            "src.matching.claim_index.embed_texts",
            lambda texts, model_id="test-model": [[0.0, 0.0]],
        )
        result = retrieve_candidates(db, "event", k=5, model_id="test-model")
        assert result == []

    def test_end_to_end_uses_real_module_default(self, db):
        """CLAIM_EMBEDDING_TABLE constant matches what build_claim_embeddings
        writes to -- a lightweight cross-check that both functions agree on
        the table name (would fail loudly if one changed without the other)."""
        assert CLAIM_EMBEDDING_TABLE == "silver_v2_claims.claim_embedding"
