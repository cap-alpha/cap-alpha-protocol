"""
Tests for pipeline/src/resolvers/silver_v2_resolver.py (Issue #1129 Slice 1)

Uses an in-memory DuckDB connection wrapped in a minimal DB adapter that
mirrors how the real DBManager is used (fetch_df/execute with `@param`
BigQuery-style query_parameters, append_dataframe_to_table). No BigQuery, no
LLM, no external services — mirrors pipeline/tests/test_promote_claims.py's
approach for the same silver_v2_claims schema family.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone

import duckdb
import pandas as pd
import pytest

from src.resolvers.silver_v2_resolver import (
    NOOP_METHOD_ID,
    NoopResolutionMethod,
    _canonical_content_hash,
    _normalise_hash_value,
    ensure_noop_resolution_method,
    ensure_resolution_method,
    run_resolution_pass,
    select_due_claims,
    write_resolution,
)

# ---------------------------------------------------------------------------
# In-memory DuckDB fixture
# ---------------------------------------------------------------------------

_DDL = """
CREATE SCHEMA IF NOT EXISTS silver_v2_claims;
CREATE SCHEMA IF NOT EXISTS silver_v2_core;

CREATE TABLE IF NOT EXISTS silver_v2_claims.claim (
    claim_id                 VARCHAR NOT NULL,
    utterance_id              VARCHAR NOT NULL,
    speaker_entity_id          VARCHAR NOT NULL,
    domain                     VARCHAR NOT NULL,
    predicate                  VARCHAR NOT NULL,
    predicate_args             JSON NOT NULL,
    resolution_window_start   TIMESTAMP NOT NULL,
    resolution_window_end     TIMESTAMP NOT NULL,
    resolution_method_id      VARCHAR NOT NULL,
    prev_hash                  VARCHAR NOT NULL,
    this_hash                  VARCHAR NOT NULL,
    created_at                 TIMESTAMP NOT NULL,
    priority_score             DOUBLE,
    next_check_at               TIMESTAMP,
    attempt                     BIGINT
);

CREATE TABLE IF NOT EXISTS silver_v2_claims.resolution (
    resolution_id          VARCHAR NOT NULL,
    claim_id                VARCHAR NOT NULL,
    resolved_at              TIMESTAMP NOT NULL,
    outcome                  VARCHAR NOT NULL,
    outcome_confidence       DOUBLE NOT NULL,
    evidence                  JSON NOT NULL,
    resolution_method_id     VARCHAR NOT NULL,
    prev_hash                 VARCHAR NOT NULL,
    this_hash                 VARCHAR NOT NULL,
    notes                     VARCHAR
);

CREATE TABLE IF NOT EXISTS silver_v2_claims.claim_state_history (
    history_id        VARCHAR NOT NULL,
    claim_id           VARCHAR NOT NULL,
    state               VARCHAR NOT NULL,
    effective_from      TIMESTAMP NOT NULL,
    effective_to        TIMESTAMP,
    effective_source    VARCHAR NOT NULL,
    resolution_id       VARCHAR,
    brier_score          DOUBLE,
    binary_correct       BOOLEAN,
    notes                VARCHAR,
    created_at           TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS silver_v2_claims.resolution_method (
    resolution_method_id VARCHAR NOT NULL,
    domain                 VARCHAR NOT NULL,
    name                    VARCHAR NOT NULL,
    adapter_path            VARCHAR NOT NULL,
    data_source             VARCHAR NOT NULL,
    config                   JSON
);

CREATE TABLE IF NOT EXISTS silver_v2_claims.raw_utterance (
    utterance_id VARCHAR NOT NULL,
    text          VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS silver_v2_claims.claim_entity_link (
    link_id       VARCHAR NOT NULL,
    claim_id      VARCHAR NOT NULL,
    entity_id     VARCHAR NOT NULL,
    entity_role   VARCHAR NOT NULL,
    ordinal       BIGINT,
    created_at    TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS silver_v2_core.entity_current (
    entity_id VARCHAR NOT NULL,
    attr      VARCHAR NOT NULL,
    value     VARCHAR NOT NULL
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
    the interface silver_v2_resolver.py expects: fetch_df/execute with
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


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------

NOW = datetime(2026, 7, 27, 12, 0, 0, tzinfo=timezone.utc)


def _naive_utc(dt: datetime | None) -> datetime | None:
    """Strip tzinfo after normalising to UTC wall-clock.

    DuckDB's Python binding silently converts a tz-aware datetime bound via
    `?` params to the *local system timezone* when the destination column is
    a naive TIMESTAMP (not TIMESTAMPTZ) -- passing NOW straight through would
    seed rows several hours off from what the test intends. Every datetime
    seeded directly via positional params in this test file goes through
    this helper first.
    """
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _seed_claim(
    db: _InMemoryDB,
    claim_id: str,
    *,
    utterance_id: str = "utt-1",
    speaker_entity_id: str = "entity-speaker-1",
    domain: str = "sports.nfl",
    predicate: str = "will_win",
    resolution_window_end: datetime = NOW - timedelta(days=1),
    resolution_window_start: datetime | None = None,
    resolution_method_id: str = "nfl_game_outcome_scores",
    this_hash: str = "claimhash",
    priority_score: float | None = 0.5,
    next_check_at: datetime | None = None,
    attempt: int | None = 0,
):
    if resolution_window_start is None:
        resolution_window_start = resolution_window_end - timedelta(days=30)
    db._conn.execute(
        """
        INSERT INTO silver_v2_claims.claim
            (claim_id, utterance_id, speaker_entity_id, domain, predicate,
             predicate_args, resolution_window_start, resolution_window_end,
             resolution_method_id, prev_hash, this_hash, created_at,
             priority_score, next_check_at, attempt)
        VALUES (?, ?, ?, ?, ?, '{}', ?, ?, ?, '', ?, ?, ?, ?, ?)
        """,
        [
            claim_id,
            utterance_id,
            speaker_entity_id,
            domain,
            predicate,
            _naive_utc(resolution_window_start),
            _naive_utc(resolution_window_end),
            resolution_method_id,
            this_hash,
            _naive_utc(NOW),
            priority_score,
            _naive_utc(next_check_at),
            attempt,
        ],
    )


def _seed_utterance(db: _InMemoryDB, utterance_id: str, text: str) -> None:
    db._conn.execute(
        "INSERT INTO silver_v2_claims.raw_utterance (utterance_id, text) VALUES (?, ?)",
        [utterance_id, text],
    )


def _seed_entity_name(db: _InMemoryDB, entity_id: str, name: str) -> None:
    db._conn.execute(
        "INSERT INTO silver_v2_core.entity_current (entity_id, attr, value) "
        "VALUES (?, 'legal_name', ?)",
        [entity_id, name],
    )


def _seed_claim_entity_link(
    db: _InMemoryDB, claim_id: str, entity_id: str, role: str = "subject"
) -> None:
    db._conn.execute(
        "INSERT INTO silver_v2_claims.claim_entity_link "
        "(link_id, claim_id, entity_id, entity_role, ordinal, created_at) "
        "VALUES (?, ?, ?, ?, NULL, ?)",
        [str(uuid.uuid4()), claim_id, entity_id, role, _naive_utc(NOW)],
    )


# ---------------------------------------------------------------------------
# select_due_claims
# ---------------------------------------------------------------------------


class TestSelectDueClaims:
    def test_includes_due_claim_with_null_next_check_at(self, db):
        _seed_claim(db, "claim-1", next_check_at=None)
        rows = select_due_claims(db, limit=50, now=NOW)
        assert [r["claim_id"] for r in rows] == ["claim-1"]

    def test_excludes_window_not_yet_ended(self, db):
        _seed_claim(db, "claim-future", resolution_window_end=NOW + timedelta(days=1))
        rows = select_due_claims(db, limit=50, now=NOW)
        assert rows == []

    def test_excludes_already_resolved_claim(self, db):
        _seed_claim(db, "claim-resolved", next_check_at=None)
        write_resolution(
            db,
            claim_id="claim-resolved",
            outcome="true",
            outcome_confidence=1.0,
            evidence={"source": "test"},
            resolution_method_id=NOOP_METHOD_ID,
            now=NOW,
        )
        rows = select_due_claims(db, limit=50, now=NOW)
        assert rows == []

    def test_excludes_next_check_at_in_future(self, db):
        _seed_claim(db, "claim-scheduled-later", next_check_at=NOW + timedelta(hours=6))
        rows = select_due_claims(db, limit=50, now=NOW)
        assert rows == []

    def test_includes_next_check_at_in_past(self, db):
        _seed_claim(db, "claim-scheduled-past", next_check_at=NOW - timedelta(hours=1))
        rows = select_due_claims(db, limit=50, now=NOW)
        assert [r["claim_id"] for r in rows] == ["claim-scheduled-past"]

    def test_respects_limit(self, db):
        for i in range(3):
            _seed_claim(db, f"claim-{i}", next_check_at=None, priority_score=float(i))
        rows = select_due_claims(db, limit=2, now=NOW)
        assert len(rows) == 2

    def test_orders_by_priority_score_desc(self, db):
        _seed_claim(db, "low", next_check_at=None, priority_score=0.1)
        _seed_claim(
            db,
            "high",
            utterance_id="utt-2",
            next_check_at=None,
            priority_score=0.9,
        )
        rows = select_due_claims(db, limit=50, now=NOW)
        assert [r["claim_id"] for r in rows] == ["high", "low"]

    def test_null_priority_score_sorts_last(self, db):
        _seed_claim(db, "has-score", next_check_at=None, priority_score=0.1)
        _seed_claim(
            db,
            "null-score",
            utterance_id="utt-2",
            next_check_at=None,
            priority_score=None,
        )
        rows = select_due_claims(db, limit=50, now=NOW)
        assert [r["claim_id"] for r in rows] == ["has-score", "null-score"]

    def test_enrichment_joins_text_and_entity_names(self, db):
        _seed_claim(
            db,
            "claim-enriched",
            utterance_id="utt-enriched",
            speaker_entity_id="speaker-1",
            next_check_at=None,
        )
        _seed_utterance(db, "utt-enriched", "Mahomes will win MVP")
        _seed_entity_name(db, "speaker-1", "Adam Schefter")
        _seed_entity_name(db, "subject-1", "Patrick Mahomes")
        _seed_claim_entity_link(db, "claim-enriched", "subject-1")

        rows = select_due_claims(db, limit=50, now=NOW)
        assert len(rows) == 1
        row = rows[0]
        assert row["claim_text"] == "Mahomes will win MVP"
        assert row["speaker_name"] == "Adam Schefter"
        assert row["subject_entity_names"] == "Patrick Mahomes"

    def test_missing_entity_data_does_not_block_selection(self, db):
        """No raw_utterance / entity_current rows at all -- enrichment fields
        are None, but the claim is still due and returned."""
        _seed_claim(db, "claim-sparse", next_check_at=None)
        rows = select_due_claims(db, limit=50, now=NOW)
        assert len(rows) == 1
        assert rows[0]["claim_text"] is None
        assert rows[0]["speaker_name"] is None
        assert rows[0]["subject_entity_names"] is None

    def test_now_none_uses_current_timestamp_sql(self):
        """now=None must build a query using the DB's own CURRENT_TIMESTAMP(),
        not a Python-computed literal -- verified via a stub capturing SQL."""

        captured = {}

        class _CapturingDB:
            def fetch_df(self, query, query_parameters=None, **kwargs):
                captured["query"] = query
                captured["params"] = query_parameters
                return pd.DataFrame()

        select_due_claims(_CapturingDB(), limit=10, now=None)
        assert "CURRENT_TIMESTAMP()" in captured["query"]
        assert not any(p.name == "now" for p in captured["params"])

    def test_now_must_be_tz_aware(self, db):
        naive = datetime(2026, 7, 27, 12, 0, 0)
        with pytest.raises(ValueError):
            select_due_claims(db, limit=50, now=naive)


# ---------------------------------------------------------------------------
# write_resolution
# ---------------------------------------------------------------------------


class TestWriteResolution:
    def test_writes_one_row(self, db):
        _seed_claim(db, "claim-1", this_hash="claimhash1")
        wrote = write_resolution(
            db,
            claim_id="claim-1",
            outcome="true",
            outcome_confidence=0.9,
            evidence={"source": "test"},
            resolution_method_id=NOOP_METHOD_ID,
            notes="looks correct",
            now=NOW,
        )
        assert wrote is True
        rows = db._conn.execute(
            "SELECT * FROM silver_v2_claims.resolution WHERE claim_id = 'claim-1'"
        ).df()
        assert len(rows) == 1
        assert rows.iloc[0]["outcome"] == "true"
        assert rows.iloc[0]["notes"] == "looks correct"

    def test_idempotent_second_call_no_ops(self, db):
        _seed_claim(db, "claim-1", this_hash="claimhash1")
        first = write_resolution(
            db,
            claim_id="claim-1",
            outcome="true",
            outcome_confidence=0.9,
            evidence={},
            resolution_method_id=NOOP_METHOD_ID,
            now=NOW,
        )
        second = write_resolution(
            db,
            claim_id="claim-1",
            outcome="false",
            outcome_confidence=0.5,
            evidence={},
            resolution_method_id=NOOP_METHOD_ID,
            now=NOW,
        )
        assert first is True
        assert second is False
        rows = db._conn.execute(
            "SELECT * FROM silver_v2_claims.resolution WHERE claim_id = 'claim-1'"
        ).df()
        assert len(rows) == 1
        # The first (true) write must remain unchanged -- no double-write.
        assert rows.iloc[0]["outcome"] == "true"

    def test_prev_hash_chains_from_claim_this_hash(self, db):
        _seed_claim(db, "claim-1", this_hash="claim-this-hash-xyz")
        write_resolution(
            db,
            claim_id="claim-1",
            outcome="true",
            outcome_confidence=1.0,
            evidence={},
            resolution_method_id=NOOP_METHOD_ID,
            now=NOW,
        )
        row = (
            db._conn.execute(
                "SELECT prev_hash, this_hash FROM silver_v2_claims.resolution "
                "WHERE claim_id = 'claim-1'"
            )
            .df()
            .iloc[0]
        )
        assert row["prev_hash"] == "claim-this-hash-xyz"
        assert row["this_hash"] != row["prev_hash"]
        assert len(row["this_hash"]) == 64  # sha256 hex digest

    def test_this_hash_recomputable_from_chain_helper(self, db):
        """this_hash must equal compute_chain_hash(content_hash, prev_hash) --
        i.e. it really is chained via the imported cryptographic_ledger
        helper, not some other ad hoc scheme."""
        from src.cryptographic_ledger import compute_chain_hash
        from src.resolvers.silver_v2_resolver import _canonical_content_hash

        _seed_claim(db, "claim-1", this_hash="claim-this-hash-xyz")
        write_resolution(
            db,
            claim_id="claim-1",
            outcome="partial",
            outcome_confidence=0.6,
            evidence={"a": 1},
            resolution_method_id=NOOP_METHOD_ID,
            notes="n",
            now=NOW,
        )
        row = (
            db._conn.execute(
                "SELECT * FROM silver_v2_claims.resolution WHERE claim_id = 'claim-1'"
            )
            .df()
            .iloc[0]
        )

        recomputed_content_hash = _canonical_content_hash(
            {
                "resolution_id": row["resolution_id"],
                "claim_id": "claim-1",
                "resolved_at": NOW,
                "outcome": "partial",
                "outcome_confidence": 0.6,
                "evidence": {"a": 1},
                "resolution_method_id": NOOP_METHOD_ID,
                "notes": "n",
            }
        )
        expected_this_hash = compute_chain_hash(
            recomputed_content_hash, "claim-this-hash-xyz"
        )
        assert row["this_hash"] == expected_this_hash

    def test_two_claims_chain_independently(self, db):
        _seed_claim(db, "claim-a", this_hash="hash-a")
        _seed_claim(db, "claim-b", utterance_id="utt-2", this_hash="hash-b")
        write_resolution(
            db,
            claim_id="claim-a",
            outcome="true",
            outcome_confidence=1.0,
            evidence={},
            resolution_method_id=NOOP_METHOD_ID,
            now=NOW,
        )
        write_resolution(
            db,
            claim_id="claim-b",
            outcome="false",
            outcome_confidence=1.0,
            evidence={},
            resolution_method_id=NOOP_METHOD_ID,
            now=NOW,
        )
        df = db._conn.execute(
            "SELECT claim_id, prev_hash FROM silver_v2_claims.resolution"
        ).df()
        prev_by_claim = dict(zip(df["claim_id"], df["prev_hash"]))
        assert prev_by_claim["claim-a"] == "hash-a"
        assert prev_by_claim["claim-b"] == "hash-b"

    def test_missing_claim_falls_back_to_empty_root(self, db):
        """claim_id absent from the claim table (should not happen for a
        claim_id from select_due_claims, but must never crash)."""
        wrote = write_resolution(
            db,
            claim_id="ghost-claim",
            outcome="unresolvable",
            outcome_confidence=0.0,
            evidence={},
            resolution_method_id=NOOP_METHOD_ID,
            now=NOW,
        )
        assert wrote is True
        row = (
            db._conn.execute(
                "SELECT prev_hash FROM silver_v2_claims.resolution WHERE claim_id = 'ghost-claim'"
            )
            .df()
            .iloc[0]
        )
        assert row["prev_hash"] == ""

    def test_writes_claim_state_history_row(self, db):
        _seed_claim(db, "claim-1", this_hash="h1")
        write_resolution(
            db,
            claim_id="claim-1",
            outcome="true",
            outcome_confidence=1.0,
            evidence={},
            resolution_method_id=NOOP_METHOD_ID,
            now=NOW,
        )
        hist = db._conn.execute(
            "SELECT * FROM silver_v2_claims.claim_state_history WHERE claim_id = 'claim-1'"
        ).df()
        assert len(hist) == 1
        assert hist.iloc[0]["state"] == "CORRECT"
        assert bool(hist.iloc[0]["binary_correct"]) is True
        assert hist.iloc[0]["effective_to"] is None or pd.isna(
            hist.iloc[0]["effective_to"]
        )

    def test_state_history_closes_open_pending_row(self, db):
        _seed_claim(db, "claim-1", this_hash="h1")
        db._conn.execute(
            "INSERT INTO silver_v2_claims.claim_state_history "
            "(history_id, claim_id, state, effective_from, effective_to, "
            " effective_source, created_at) "
            "VALUES (?, ?, 'PENDING', ?, NULL, 'ingestion', ?)",
            [
                str(uuid.uuid4()),
                "claim-1",
                _naive_utc(NOW - timedelta(days=5)),
                _naive_utc(NOW - timedelta(days=5)),
            ],
        )
        write_resolution(
            db,
            claim_id="claim-1",
            outcome="false",
            outcome_confidence=1.0,
            evidence={},
            resolution_method_id=NOOP_METHOD_ID,
            now=NOW,
        )
        hist = db._conn.execute(
            "SELECT state, effective_to FROM silver_v2_claims.claim_state_history "
            "WHERE claim_id = 'claim-1' ORDER BY state"
        ).df()
        assert len(hist) == 2
        pending_row = hist[hist["state"] == "PENDING"].iloc[0]
        assert pending_row["effective_to"] is not None
        assert not pd.isna(pending_row["effective_to"])
        incorrect_row = hist[hist["state"] == "INCORRECT"].iloc[0]
        assert pd.isna(incorrect_row["effective_to"])

    @pytest.mark.parametrize(
        "outcome,expected_state,expected_binary_correct",
        [
            ("true", "CORRECT", True),
            ("false", "INCORRECT", False),
            ("partial", "PARTIAL", None),
            ("unresolvable", "UNVERIFIABLE", None),
            ("vacuous", "VOID", None),
            ("something_unrecognised", "UNVERIFIABLE", None),
        ],
    )
    def test_outcome_to_state_mapping(
        self, db, outcome, expected_state, expected_binary_correct
    ):
        claim_id = f"claim-{outcome}"
        _seed_claim(db, claim_id, this_hash=f"h-{outcome}")
        write_resolution(
            db,
            claim_id=claim_id,
            outcome=outcome,
            outcome_confidence=0.7,
            evidence={},
            resolution_method_id=NOOP_METHOD_ID,
            now=NOW,
        )
        hist = (
            db._conn.execute(
                f"SELECT state, binary_correct FROM silver_v2_claims.claim_state_history "
                f"WHERE claim_id = '{claim_id}'"
            )
            .df()
            .iloc[0]
        )
        assert hist["state"] == expected_state
        if expected_binary_correct is None:
            assert hist["binary_correct"] is None or pd.isna(hist["binary_correct"])
        else:
            assert bool(hist["binary_correct"]) is expected_binary_correct

    def test_now_must_be_tz_aware(self, db):
        _seed_claim(db, "claim-1")
        naive = datetime(2026, 7, 27, 12, 0, 0)
        with pytest.raises(ValueError):
            write_resolution(
                db,
                claim_id="claim-1",
                outcome="true",
                outcome_confidence=1.0,
                evidence={},
                resolution_method_id=NOOP_METHOD_ID,
                now=naive,
            )


# ---------------------------------------------------------------------------
# resolution_method registration
# ---------------------------------------------------------------------------


class TestEnsureResolutionMethod:
    def test_inserts_new_row(self, db):
        inserted = ensure_resolution_method(
            db,
            resolution_method_id="test_method",
            domain="sports.nfl",
            name="Test Method",
            adapter_path="pipeline.test:Method",
            data_source="test",
        )
        assert inserted is True
        rows = db._conn.execute(
            "SELECT * FROM silver_v2_claims.resolution_method "
            "WHERE resolution_method_id = 'test_method'"
        ).df()
        assert len(rows) == 1

    def test_second_call_is_idempotent(self, db):
        ensure_resolution_method(
            db,
            resolution_method_id="test_method",
            domain="sports.nfl",
            name="Test Method",
            adapter_path="p:M",
            data_source="test",
        )
        inserted_again = ensure_resolution_method(
            db,
            resolution_method_id="test_method",
            domain="sports.nfl",
            name="Test Method",
            adapter_path="p:M",
            data_source="test",
        )
        assert inserted_again is False
        rows = db._conn.execute(
            "SELECT * FROM silver_v2_claims.resolution_method "
            "WHERE resolution_method_id = 'test_method'"
        ).df()
        assert len(rows) == 1

    def test_ensure_noop_resolution_method(self, db):
        assert ensure_noop_resolution_method(db) is True
        assert ensure_noop_resolution_method(db) is False
        rows = db._conn.execute(
            f"SELECT * FROM silver_v2_claims.resolution_method "
            f"WHERE resolution_method_id = '{NOOP_METHOD_ID}'"
        ).df()
        assert len(rows) == 1


# ---------------------------------------------------------------------------
# NoopResolutionMethod
# ---------------------------------------------------------------------------


class TestNoopResolutionMethod:
    def test_always_returns_none(self):
        method = NoopResolutionMethod()
        assert method.resolve({"claim_id": "x"}) is None
        assert method.method_id == NOOP_METHOD_ID


# ---------------------------------------------------------------------------
# run_resolution_pass
# ---------------------------------------------------------------------------


class TestRunResolutionPass:
    def test_noop_method_resolves_nothing_but_does_not_crash(self, db):
        _seed_claim(db, "claim-1", next_check_at=None)
        _seed_claim(db, "claim-2", utterance_id="utt-2", next_check_at=None)

        summary = run_resolution_pass(db, NoopResolutionMethod(), limit=50, now=NOW)

        assert summary == {"checked": 2, "resolved": 0, "skipped": 2}
        rows = db._conn.execute("SELECT * FROM silver_v2_claims.resolution").df()
        assert len(rows) == 0

    def test_empty_due_set_returns_zeroed_summary(self, db):
        summary = run_resolution_pass(db, NoopResolutionMethod(), limit=50, now=NOW)
        assert summary == {"checked": 0, "resolved": 0, "skipped": 0}

    def test_summary_always_has_get_safe_keys(self, db):
        """Regression guard: resolve_all-style aggregation upstream does
        `.get(key, 0)` across summaries -- a summary must never be missing
        checked/resolved/skipped, the exact bug class that broke
        resolve_daily's llm_judge pass (missing 'voided')."""
        summary = run_resolution_pass(db, NoopResolutionMethod(), limit=50, now=NOW)
        for key in ("checked", "resolved", "skipped"):
            assert summary.get(key, "MISSING") != "MISSING"

    def test_stub_method_writes_a_resolution(self, db):
        _seed_claim(db, "claim-1", next_check_at=None, this_hash="h1")

        class _StubMethod:
            method_id = "stub_method"

            def resolve(self, claim):
                assert claim["claim_id"] == "claim-1"
                return ("true", 0.95, {"source": "stub"}, "stub verdict")

        summary = run_resolution_pass(db, _StubMethod(), limit=50, now=NOW)

        assert summary == {"checked": 1, "resolved": 1, "skipped": 0}
        rows = db._conn.execute("SELECT * FROM silver_v2_claims.resolution").df()
        assert len(rows) == 1
        assert rows.iloc[0]["resolution_method_id"] == "stub_method"
        assert rows.iloc[0]["outcome"] == "true"

    def test_respects_limit(self, db):
        for i in range(5):
            _seed_claim(db, f"claim-{i}", next_check_at=None)
        summary = run_resolution_pass(db, NoopResolutionMethod(), limit=2, now=NOW)
        assert summary["checked"] == 2


# ---------------------------------------------------------------------------
# Hash canonicalization helpers
# ---------------------------------------------------------------------------


class TestCanonicalContentHash:
    def test_deterministic(self):
        payload = {
            "resolution_id": "r1",
            "claim_id": "c1",
            "resolved_at": NOW,
            "outcome": "true",
            "outcome_confidence": 1.0,
            "evidence": {"b": 2, "a": 1},
            "resolution_method_id": "m1",
            "notes": None,
        }
        h1 = _canonical_content_hash(payload)
        h2 = _canonical_content_hash(dict(payload))
        assert h1 == h2
        assert len(h1) == 64

    def test_different_evidence_key_order_same_hash(self):
        payload_a = {"evidence": {"a": 1, "b": 2}, "x": NOW}
        payload_b = {"evidence": {"b": 2, "a": 1}, "x": NOW}
        assert _canonical_content_hash(payload_a) == _canonical_content_hash(payload_b)

    def test_different_content_different_hash(self):
        payload_a = {"outcome": "true", "x": NOW}
        payload_b = {"outcome": "false", "x": NOW}
        assert _canonical_content_hash(payload_a) != _canonical_content_hash(payload_b)

    def test_normalise_hash_value_naive_datetime_assumed_utc(self):
        naive = datetime(2026, 1, 1, 0, 0, 0)
        aware = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        assert _normalise_hash_value(naive) == _normalise_hash_value(aware)
