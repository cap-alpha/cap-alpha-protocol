"""
Tests for pipeline/src/promote_claims.py

Uses in-memory DuckDB seeded with minimal silver_v2_claims schema.
No BigQuery, no LLM, no external services.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone

import duckdb
import pandas as pd
import pytest

# Patch environment to DuckDB backend before importing promote_claims
os.environ.setdefault("DB_BACKEND", "duckdb")

from src.promote_claims import (
    _compute_this_hash,
    _derive_claim_id,
    _infer_predicate,
    promote_utterances_to_claims,
)


# ---------------------------------------------------------------------------
# In-memory DuckDB fixture
# ---------------------------------------------------------------------------

_DDL = """
CREATE SCHEMA IF NOT EXISTS silver_v2_claims;

CREATE TABLE IF NOT EXISTS silver_v2_claims.raw_utterance (
    utterance_id            VARCHAR NOT NULL,
    source_doc_id           VARCHAR NOT NULL,
    speaker_entity_id       VARCHAR NOT NULL,
    uttered_at              TIMESTAMP NOT NULL,
    text                    VARCHAR NOT NULL,
    speech_act_type         VARCHAR NOT NULL,
    testability_score       DOUBLE NOT NULL,
    resolution_horizon      TIMESTAMP,
    domain                  VARCHAR NOT NULL,
    extraction_confidence   DOUBLE NOT NULL,
    target_entity           JSON,
    created_at              TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS silver_v2_claims.claim (
    claim_id                VARCHAR NOT NULL,
    utterance_id            VARCHAR NOT NULL,
    speaker_entity_id       VARCHAR NOT NULL,
    domain                  VARCHAR NOT NULL,
    claim_subject_type      VARCHAR NOT NULL,
    subject_entity_ids      VARCHAR[],
    subject_metric          VARCHAR,
    predicate               VARCHAR NOT NULL,
    predicate_args          JSON NOT NULL,
    resolution_window_start TIMESTAMP NOT NULL,
    resolution_window_end   TIMESTAMP NOT NULL,
    resolution_method_id    VARCHAR NOT NULL,
    asserted_at             TIMESTAMP NOT NULL,
    ledger_locked_at        TIMESTAMP NOT NULL,
    prior_claim_id          VARCHAR,
    prev_hash               VARCHAR NOT NULL,
    this_hash               VARCHAR NOT NULL,
    created_at              TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS silver_v2_claims.resolution_method (
    resolution_method_id    VARCHAR NOT NULL,
    domain                  VARCHAR NOT NULL,
    name                    VARCHAR NOT NULL,
    adapter_path            VARCHAR NOT NULL,
    data_source             VARCHAR NOT NULL,
    config                  JSON
);
"""


class _InMemoryDB:
    """
    Minimal DB adapter that wraps an in-memory DuckDB connection and satisfies
    the interface expected by promote_utterances_to_claims().
    """

    def __init__(self, conn):
        self._conn = conn

    def fetch_df(self, query: str, **kwargs) -> pd.DataFrame:
        return self._conn.execute(query).df()

    def append_dataframe_to_table(self, df: pd.DataFrame, table_name: str) -> None:
        # Normalise: "schema.table" → schema.table
        parts = table_name.split(".")
        if len(parts) == 2:
            ref = f"{parts[0]}.{parts[1]}"
        else:
            ref = table_name

        cols = ", ".join(f'"{c}"' for c in df.columns)
        view = f"__tmp_{uuid.uuid4().hex[:6]}"
        self._conn.register(view, df)
        try:
            self._conn.execute(f"INSERT INTO {ref} ({cols}) SELECT {cols} FROM {view}")
        finally:
            self._conn.unregister(view)


@pytest.fixture
def db():
    """Create a fresh in-memory DuckDB with the silver_v2_claims schema."""
    conn = duckdb.connect(":memory:")
    for stmt in _DDL.split(";"):
        stmt = stmt.strip()
        if stmt:
            conn.execute(stmt)
    yield _InMemoryDB(conn)
    conn.close()


@pytest.fixture
def db_with_method(db):
    """Extend db fixture with a single resolution_method row for sports.nfl."""
    db._conn.execute(
        """
        INSERT INTO silver_v2_claims.resolution_method
            (resolution_method_id, domain, name, adapter_path, data_source, config)
        VALUES
            ('nfl_game_outcome_scores', 'sports.nfl', 'NFL Game Outcomes',
             'pipeline.resolvers.nfl:resolve', 'sportradar.nfl', NULL)
        """
    )
    return db


def _seed_utterance(
    db,
    utterance_id: str,
    text: str,
    speech_act_type: str = "assertion",
    testability_score: float = 0.9,
    domain: str = "sports.nfl",
    target_entity: dict | None = None,
    resolution_horizon=None,
):
    """Insert one row into raw_utterance."""
    target_entity_json = json.dumps(target_entity) if target_entity else None
    db._conn.execute(
        """
        INSERT INTO silver_v2_claims.raw_utterance
            (utterance_id, source_doc_id, speaker_entity_id, uttered_at,
             text, speech_act_type, testability_score, resolution_horizon,
             domain, extraction_confidence, target_entity, created_at)
        VALUES (?, 'doc_1', 'pundit_adam_schefter', '2025-01-15 12:00:00',
                ?, ?, ?, ?, ?, 0.95, ?, CURRENT_TIMESTAMP)
        """,
        [
            utterance_id,
            text,
            speech_act_type,
            testability_score,
            resolution_horizon,
            domain,
            target_entity_json,
        ],
    )


# ---------------------------------------------------------------------------
# Tests: predicate heuristics
# ---------------------------------------------------------------------------


def test_predicate_will_win():
    assert _infer_predicate("Mahomes will win MVP this season") == "will_win"


def test_predicate_will_retire():
    assert _infer_predicate("Brady will retire after this year") == "will_retire"


def test_predicate_will_be_drafted():
    assert (
        _infer_predicate("He will be drafted in the first round") == "will_be_drafted"
    )


def test_predicate_will_sign():
    assert (
        _infer_predicate("The team will sign a wide receiver next week") == "will_sign"
    )


def test_predicate_will_exceed():
    assert _infer_predicate("He will exceed 1000 rushing yards") == "will_exceed"


def test_predicate_will_lose():
    assert _infer_predicate("They will lose the Super Bowl") == "will_lose"


def test_predicate_unknown_defaults_to_will_occur():
    assert _infer_predicate("No pattern matches this utterance at all.") == "will_occur"


def test_predicate_will_catch_all():
    """A text containing 'will' but no specific verb falls through to will_occur."""
    assert _infer_predicate("Things will happen in the NFL this year") == "will_occur"


# ---------------------------------------------------------------------------
# Tests: this_hash determinism
# ---------------------------------------------------------------------------


def test_this_hash_deterministic():
    """Same row dict always produces the same hash."""
    now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
    row = {
        "claim_id": "abc123",
        "utterance_id": "utt-1",
        "speaker_entity_id": "pundit_x",
        "domain": "sports.nfl",
        "claim_subject_type": "entity",
        "subject_entity_ids": ["entity_abc"],
        "predicate": "will_win",
        "predicate_args": '{"raw_text": "he will win"}',
        "resolution_window_start": now,
        "resolution_window_end": now,
        "resolution_method_id": "nfl_game_outcome_scores",
        "asserted_at": now,
        "ledger_locked_at": now,
        "prev_hash": "",
    }
    h1 = _compute_this_hash(row)
    h2 = _compute_this_hash(row)
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex


def test_this_hash_changes_with_different_input():
    """Different inputs produce different hashes."""
    now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
    base = {
        "claim_id": "abc123",
        "utterance_id": "utt-1",
        "speaker_entity_id": "pundit_x",
        "domain": "sports.nfl",
        "predicate": "will_win",
        "asserted_at": now,
        "prev_hash": "",
    }
    row_a = {**base, "predicate": "will_win"}
    row_b = {**base, "predicate": "will_lose"}
    assert _compute_this_hash(row_a) != _compute_this_hash(row_b)


# ---------------------------------------------------------------------------
# Tests: claim_id derivation
# ---------------------------------------------------------------------------


def test_derive_claim_id_is_uuidv5():
    uid = _derive_claim_id("utterance-xyz")
    parsed = uuid.UUID(uid)
    assert parsed.version == 5


def test_derive_claim_id_deterministic():
    cid1 = _derive_claim_id("utterance-abc")
    cid2 = _derive_claim_id("utterance-abc")
    assert cid1 == cid2


def test_derive_claim_id_different_inputs():
    assert _derive_claim_id("utterance-1") != _derive_claim_id("utterance-2")


# ---------------------------------------------------------------------------
# Tests: qualifying / non-qualifying promotion
# ---------------------------------------------------------------------------


def test_qualifying_utterance_gets_promoted(db_with_method):
    """An assertion with testability >= 0.6 should produce one claim row."""
    uid = str(uuid.uuid4())
    _seed_utterance(db_with_method, uid, "Mahomes will win MVP this season")

    count = promote_utterances_to_claims(db=db_with_method)
    assert count == 1

    rows = db_with_method._conn.execute(
        "SELECT * FROM silver_v2_claims.claim"
    ).fetchall()
    assert len(rows) == 1


def test_promotion_is_idempotent(db_with_method):
    """Running promote twice does not create duplicate claim rows."""
    uid = str(uuid.uuid4())
    _seed_utterance(db_with_method, uid, "Chiefs will win the Super Bowl")

    n1 = promote_utterances_to_claims(db=db_with_method)
    n2 = promote_utterances_to_claims(db=db_with_method)

    assert n1 == 1
    assert n2 == 0  # Already promoted — skipped

    rows = db_with_method._conn.execute(
        "SELECT * FROM silver_v2_claims.claim"
    ).fetchall()
    assert len(rows) == 1


def test_non_qualifying_commentary_not_promoted(db_with_method):
    """Commentary speech_act_type does not get promoted."""
    uid = str(uuid.uuid4())
    _seed_utterance(
        db_with_method,
        uid,
        "The game was exciting today",
        speech_act_type="commentary",
        testability_score=0.8,
    )

    count = promote_utterances_to_claims(db=db_with_method)
    assert count == 0


def test_non_qualifying_opinion_not_promoted(db_with_method):
    """Opinion speech_act_type does not get promoted."""
    uid = str(uuid.uuid4())
    _seed_utterance(
        db_with_method,
        uid,
        "I think this was a great draft class",
        speech_act_type="opinion",
        testability_score=0.9,
    )
    count = promote_utterances_to_claims(db=db_with_method)
    assert count == 0


def test_low_testability_not_promoted(db_with_method):
    """Utterance with testability_score < 0.6 does not get promoted."""
    uid = str(uuid.uuid4())
    _seed_utterance(
        db_with_method,
        uid,
        "Something might happen sometime",
        speech_act_type="assertion",
        testability_score=0.3,
    )
    count = promote_utterances_to_claims(db=db_with_method)
    assert count == 0


def test_recall_speech_act_qualifies(db_with_method):
    """recall speech_act_type with testability >= 0.6 qualifies."""
    uid = str(uuid.uuid4())
    _seed_utterance(
        db_with_method,
        uid,
        "I said that team would win last year",
        speech_act_type="recall",
        testability_score=0.75,
    )
    count = promote_utterances_to_claims(db=db_with_method)
    assert count == 1


def test_conditional_speech_act_qualifies(db_with_method):
    """conditional speech_act_type with testability >= 0.6 qualifies."""
    uid = str(uuid.uuid4())
    _seed_utterance(
        db_with_method,
        uid,
        "If they stay healthy they will win",
        speech_act_type="conditional",
        testability_score=0.8,
    )
    count = promote_utterances_to_claims(db=db_with_method)
    assert count == 1


# ---------------------------------------------------------------------------
# Tests: claim row content correctness
# ---------------------------------------------------------------------------


def test_claim_row_fields_populated_correctly(db_with_method):
    """Check key fields of the promoted claim row."""
    uid = str(uuid.uuid4())
    _seed_utterance(
        db_with_method,
        uid,
        "Mahomes will win MVP this season",
        domain="sports.nfl",
        target_entity={"entity_id": "player_mahomes_abc123"},
    )

    promote_utterances_to_claims(db=db_with_method)

    row = (
        db_with_method._conn.execute("SELECT * FROM silver_v2_claims.claim LIMIT 1")
        .df()
        .iloc[0]
    )

    # claim_id should be deterministic UUIDv5 from utterance_id
    assert row["claim_id"] == _derive_claim_id(uid)
    assert row["utterance_id"] == uid
    assert row["speaker_entity_id"] == "pundit_adam_schefter"
    assert row["domain"] == "sports.nfl"
    assert row["claim_subject_type"] == "entity"  # has entity_id in target_entity
    assert row["predicate"] == "will_win"
    assert row["prev_hash"] == ""
    assert len(row["this_hash"]) == 64


def test_claim_row_aggregate_when_no_entity(db_with_method):
    """claim_subject_type is 'aggregate' when target_entity has no entity_id."""
    uid = str(uuid.uuid4())
    _seed_utterance(
        db_with_method,
        uid,
        "The league will have 17 games per team",
        domain="sports.nfl",
        target_entity=None,
    )

    promote_utterances_to_claims(db=db_with_method)

    row = db_with_method._conn.execute(
        "SELECT claim_subject_type FROM silver_v2_claims.claim LIMIT 1"
    ).fetchone()
    assert row[0] == "aggregate"


def test_resolution_window_end_uses_horizon_when_provided(db_with_method):
    """resolution_window_end = resolution_horizon when provided."""
    uid = str(uuid.uuid4())
    horizon = "2025-12-31 23:59:59"
    _seed_utterance(
        db_with_method,
        uid,
        "Chiefs will win this season",
        resolution_horizon=horizon,
    )

    promote_utterances_to_claims(db=db_with_method)

    row = db_with_method._conn.execute(
        "SELECT resolution_window_end FROM silver_v2_claims.claim LIMIT 1"
    ).fetchone()
    assert row[0].year == 2025
    assert row[0].month == 12
    assert row[0].day == 31


def test_resolution_window_end_defaults_to_365_days(db_with_method):
    """resolution_window_end = uttered_at + 365 days when horizon is NULL."""
    uid = str(uuid.uuid4())
    _seed_utterance(
        db_with_method, uid, "Team will win next year", resolution_horizon=None
    )

    promote_utterances_to_claims(db=db_with_method)

    row = db_with_method._conn.execute(
        "SELECT resolution_window_start, resolution_window_end FROM silver_v2_claims.claim LIMIT 1"
    ).fetchone()
    start, end = row
    delta = end - start
    # 365 days tolerance within 1 day (leap year etc.)
    assert abs(delta.days - 365) <= 1


def test_multiple_utterances_promotes_all(db_with_method):
    """All qualifying utterances get promoted in a single call."""
    uids = [str(uuid.uuid4()) for _ in range(5)]
    for uid in uids:
        _seed_utterance(db_with_method, uid, f"Team will win {uid[:6]}")

    count = promote_utterances_to_claims(db=db_with_method)
    assert count == 5

    total = db_with_method._conn.execute(
        "SELECT count(*) FROM silver_v2_claims.claim"
    ).fetchone()[0]
    assert total == 5


def test_partial_existing_claims_skipped(db_with_method):
    """Only the new utterances (not already promoted) get inserted."""
    uid1 = str(uuid.uuid4())
    uid2 = str(uuid.uuid4())
    _seed_utterance(db_with_method, uid1, "Chiefs will win MVP race")
    _seed_utterance(db_with_method, uid2, "Ravens will win the North division")

    n1 = promote_utterances_to_claims(db=db_with_method)
    assert n1 == 2

    # Add a third utterance and re-run — only the new one should be promoted
    uid3 = str(uuid.uuid4())
    _seed_utterance(db_with_method, uid3, "Eagles will sign a QB")
    n2 = promote_utterances_to_claims(db=db_with_method)
    assert n2 == 1

    total = db_with_method._conn.execute(
        "SELECT count(*) FROM silver_v2_claims.claim"
    ).fetchone()[0]
    assert total == 3


def test_utterance_ids_filter(db_with_method):
    """When utterance_ids is provided, only those IDs are candidates."""
    uid1 = str(uuid.uuid4())
    uid2 = str(uuid.uuid4())
    _seed_utterance(db_with_method, uid1, "Chiefs will win the Super Bowl")
    _seed_utterance(db_with_method, uid2, "Eagles will sign a QB")

    # Only promote uid1
    count = promote_utterances_to_claims(utterance_ids=[uid1], db=db_with_method)
    assert count == 1

    rows = db_with_method._conn.execute(
        "SELECT utterance_id FROM silver_v2_claims.claim"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == uid1


def test_empty_table_returns_zero(db_with_method):
    """Empty raw_utterance table returns 0 without error."""
    count = promote_utterances_to_claims(db=db_with_method)
    assert count == 0


def test_fallback_resolution_method_when_none_available(db):
    """When no resolution_method rows exist, fallback ID is still written."""
    uid = str(uuid.uuid4())
    _seed_utterance(db, uid, "Chiefs will win the Super Bowl")

    count = promote_utterances_to_claims(db=db)
    assert count == 1

    row = db._conn.execute(
        "SELECT resolution_method_id FROM silver_v2_claims.claim LIMIT 1"
    ).fetchone()
    # Should use the hardcoded fallback
    assert row[0] == "nfl_game_outcome_scores"
