"""
Unit tests for pipeline/scripts/backfill_provider_attribution.py

Fixture: in-memory DuckDB with:
  - gold_layer.prediction_ledger  (mix of attributed + NULL rows)
  - nfl_dead_money.raw_pundit_media
  - silver_v2_claims.raw_utterance
  - silver_v2_claims.extraction_run

Tests:
  1. Rows with a unique extraction_run match get the run's provider/model.
  2. NULL rows with no matching extraction_run are labeled legacy_pre_attribution.
  3. Re-running the backfill on already-attributed rows is a no-op (idempotent).
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import duckdb
import pandas as pd
import pytest

# Allow importing from pipeline/scripts without installation
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from backfill_provider_attribution import (
    LEGACY_MODEL,
    LEGACY_PROVIDER,
    _apply_updates,
    _fetch_null_rows,
    _find_attributed_rows,
    run_backfill,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS gold_layer;
CREATE SCHEMA IF NOT EXISTS nfl_dead_money;
CREATE SCHEMA IF NOT EXISTS silver_v2_claims;

CREATE TABLE IF NOT EXISTS gold_layer.prediction_ledger (
    prediction_hash     VARCHAR,
    chain_hash          VARCHAR,
    ingestion_timestamp TIMESTAMP,
    source_url          VARCHAR,
    pundit_id           VARCHAR,
    pundit_name         VARCHAR,
    raw_assertion_text  VARCHAR,
    llm_provider        VARCHAR,
    llm_model           VARCHAR,
    prompt_version      VARCHAR
);

CREATE TABLE IF NOT EXISTS nfl_dead_money.raw_pundit_media (
    content_hash  VARCHAR,
    source_url    VARCHAR,
    ingested_at   TIMESTAMP
);

CREATE TABLE IF NOT EXISTS silver_v2_claims.raw_utterance (
    utterance_id          VARCHAR,
    source_doc_id         VARCHAR,
    speaker_entity_id     VARCHAR,
    uttered_at            TIMESTAMP,
    text                  VARCHAR,
    speech_act_type       VARCHAR,
    testability_score     DOUBLE,
    resolution_horizon    TIMESTAMP,
    domain                VARCHAR,
    extraction_confidence DOUBLE,
    created_at            TIMESTAMP
);

CREATE TABLE IF NOT EXISTS silver_v2_claims.extraction_run (
    run_id                    VARCHAR,
    started_at                TIMESTAMP,
    finished_at               TIMESTAMP,
    provider                  VARCHAR,
    model                     VARCHAR,
    prompt_version            VARCHAR,
    articles_processed        BIGINT,
    utterances_written        BIGINT,
    claims_promoted           BIGINT,
    suppressed                BIGINT,
    errors                    BIGINT,
    mean_testability_score    DOUBLE,
    metadata_completeness_pct DOUBLE,
    git_sha                   VARCHAR,
    workflow_run_url          VARCHAR
);
"""


def _seed_data(conn: duckdb.DuckDBPyConnection):
    """Insert test data into the in-memory DuckDB."""

    # ── prediction_ledger ──────────────────────────────────────────────────
    conn.execute("""
        INSERT INTO gold_layer.prediction_ledger VALUES
        -- Already attributed row (should NOT be touched)
        ('hash_attributed', 'chainhash_attr', '2026-04-10 10:00:00',
         'https://example.com/article-attr', 'pundit1', 'Pundit One',
         'Some assertion', 'ollama', 'llama3.1:8b', 'v1'),

        -- NULL row whose article was processed by an extraction_run (should join)
        ('hash_joinable', 'chainhash_join', '2026-05-03 14:30:00',
         'https://example.com/article-run', 'pundit2', 'Pundit Two',
         'Some joinable assertion', NULL, NULL, NULL),

        -- NULL row with no matching extraction_run (should get legacy label)
        ('hash_legacy_1', 'chainhash_leg1', '2026-04-05 08:00:00',
         'https://example.com/article-old1', 'pundit3', 'Pundit Three',
         'Old assertion 1', NULL, NULL, NULL),

        -- Another NULL row with no matching extraction_run
        ('hash_legacy_2', 'chainhash_leg2', '2026-04-15 09:00:00',
         'https://example.com/article-old2', 'pundit4', 'Pundit Four',
         'Old assertion 2', NULL, NULL, NULL)
    """)

    # ── raw_pundit_media ───────────────────────────────────────────────────
    conn.execute("""
        INSERT INTO nfl_dead_money.raw_pundit_media VALUES
        ('contenthash_run', 'https://example.com/article-run', '2026-05-03 12:00:00'),
        ('contenthash_old1', 'https://example.com/article-old1', '2026-04-05 07:00:00'),
        ('contenthash_old2', 'https://example.com/article-old2', '2026-04-15 08:00:00')
    """)

    # ── raw_utterance ──────────────────────────────────────────────────────
    conn.execute("""
        INSERT INTO silver_v2_claims.raw_utterance
        (utterance_id, source_doc_id, speaker_entity_id, uttered_at, text,
         speech_act_type, testability_score, resolution_horizon, domain,
         extraction_confidence, created_at)
        VALUES
        -- utterance from the joinable article, created INSIDE the extraction_run window
        ('utt_run_1', 'contenthash_run', 'speaker_1', '2026-05-03 12:00:00',
         'Joinable claim text', 'prediction', 0.8, NULL, 'SPORTS', 0.8,
         '2026-05-03 14:00:00')
    """)

    # ── extraction_run ─────────────────────────────────────────────────────
    conn.execute("""
        INSERT INTO silver_v2_claims.extraction_run VALUES
        ('run_abc123', '2026-05-03 13:00:00', '2026-05-03 15:00:00',
         'ollama', 'qwen2.5:32b', 'v2',
         10, 5, 5, 0, 0, 0.75, 0.9, 'abc123', NULL)
    """)


class _MockDB:
    """
    Minimal DB adapter wrapping an in-memory DuckDB connection so that
    _fetch_null_rows, _find_attributed_rows, and _apply_updates can call
    db.fetch_df() and db.execute() against our fixture data.
    """

    def __init__(self, conn: duckdb.DuckDBPyConnection):
        self._conn = conn

    def fetch_df(self, query: str, params=None, query_parameters=None) -> pd.DataFrame:
        return self._conn.execute(query).df()

    def execute(self, query: str, params=None, query_parameters=None):
        self._conn.execute(query)
        return MagicMock()

    def close(self):
        pass


@pytest.fixture()
def db_fixture():
    """Create an in-memory DuckDB with test data and return a _MockDB."""
    conn = duckdb.connect(":memory:")
    conn.execute(_SCHEMA_SQL)
    _seed_data(conn)
    yield _MockDB(conn)
    conn.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFetchNullRows:
    def test_returns_only_null_rows(self, db_fixture):
        df = _fetch_null_rows(db_fixture, limit=100)
        assert len(df) == 3  # hash_joinable, hash_legacy_1, hash_legacy_2
        assert set(df["prediction_hash"]) == {
            "hash_joinable",
            "hash_legacy_1",
            "hash_legacy_2",
        }

    def test_respects_limit(self, db_fixture):
        df = _fetch_null_rows(db_fixture, limit=2)
        assert len(df) == 2

    def test_already_attributed_row_not_returned(self, db_fixture):
        df = _fetch_null_rows(db_fixture, limit=100)
        assert "hash_attributed" not in df["prediction_hash"].values


class TestFindAttributedRows:
    def test_joinable_row_gets_correct_provider(self, db_fixture):
        attrs = _find_attributed_rows(db_fixture, ["hash_joinable"])
        assert "hash_joinable" in attrs
        provider, model = attrs["hash_joinable"]
        assert provider == "ollama"
        assert model == "qwen2.5:32b"

    def test_old_rows_not_attributed(self, db_fixture):
        attrs = _find_attributed_rows(db_fixture, ["hash_legacy_1", "hash_legacy_2"])
        assert "hash_legacy_1" not in attrs
        assert "hash_legacy_2" not in attrs

    def test_empty_input_returns_empty(self, db_fixture):
        attrs = _find_attributed_rows(db_fixture, [])
        assert attrs == {}


class TestApplyUpdates:
    def test_dry_run_returns_zero_updates(self, db_fixture):
        updates = [
            {
                "prediction_hash": "hash_legacy_1",
                "llm_provider": LEGACY_PROVIDER,
                "llm_model": LEGACY_MODEL,
            },
        ]
        n = _apply_updates(db_fixture, updates, dry_run=True)
        assert n == 0

    def test_dry_run_does_not_write(self, db_fixture):
        updates = [
            {
                "prediction_hash": "hash_legacy_1",
                "llm_provider": LEGACY_PROVIDER,
                "llm_model": LEGACY_MODEL,
            },
        ]
        _apply_updates(db_fixture, updates, dry_run=True)
        # Row should still be NULL after dry-run
        conn = db_fixture._conn
        row = conn.execute(
            "SELECT llm_provider FROM gold_layer.prediction_ledger "
            "WHERE prediction_hash = 'hash_legacy_1'"
        ).fetchone()
        assert row[0] is None

    def test_live_run_writes_provider(self, db_fixture):
        updates = [
            {
                "prediction_hash": "hash_legacy_1",
                "llm_provider": LEGACY_PROVIDER,
                "llm_model": LEGACY_MODEL,
            },
        ]
        _apply_updates(db_fixture, updates, dry_run=False)
        conn = db_fixture._conn
        row = conn.execute(
            "SELECT llm_provider, llm_model FROM gold_layer.prediction_ledger "
            "WHERE prediction_hash = 'hash_legacy_1'"
        ).fetchone()
        assert row[0] == LEGACY_PROVIDER
        assert row[1] == LEGACY_MODEL

    def test_empty_updates_returns_zero(self, db_fixture):
        n = _apply_updates(db_fixture, [], dry_run=False)
        assert n == 0


class TestRunBackfillIdempotence:
    """Re-running the full backfill on already-attributed rows is a no-op."""

    def test_second_run_finds_no_null_rows(self, db_fixture):
        """After a live run, all NULL rows are filled; a second run finds none."""
        with patch(
            "backfill_provider_attribution.get_db_manager", return_value=db_fixture
        ):
            result1 = run_backfill(limit=1000, dry_run=False)
            # First run should find 3 NULL rows and update them
            assert result1["null_rows_found"] == 3
            assert result1["rows_updated"] == 3

            result2 = run_backfill(limit=1000, dry_run=False)
            # Second run: no NULL rows left → no updates
            assert result2["null_rows_found"] == 0
            assert result2["rows_updated"] == 0

    def test_attributed_row_unchanged_after_run(self, db_fixture):
        """Row already attributed (ollama/llama3.1:8b) must not be overwritten."""
        with patch(
            "backfill_provider_attribution.get_db_manager", return_value=db_fixture
        ):
            run_backfill(limit=1000, dry_run=False)

        conn = db_fixture._conn
        row = conn.execute(
            "SELECT llm_provider, llm_model FROM gold_layer.prediction_ledger "
            "WHERE prediction_hash = 'hash_attributed'"
        ).fetchone()
        assert row[0] == "ollama"
        assert row[1] == "llama3.1:8b"


class TestRunBackfillJoinAttribution:
    """The joinable row should receive the extraction_run's provider, not the legacy sentinel."""

    def test_joinable_row_gets_extraction_run_provider(self, db_fixture):
        with patch(
            "backfill_provider_attribution.get_db_manager", return_value=db_fixture
        ):
            result = run_backfill(limit=1000, dry_run=False)

        assert result["attributed_via_join"] == 1

        conn = db_fixture._conn
        row = conn.execute(
            "SELECT llm_provider, llm_model FROM gold_layer.prediction_ledger "
            "WHERE prediction_hash = 'hash_joinable'"
        ).fetchone()
        assert row[0] == "ollama"
        assert row[1] == "qwen2.5:32b"

    def test_legacy_rows_get_sentinel_values(self, db_fixture):
        with patch(
            "backfill_provider_attribution.get_db_manager", return_value=db_fixture
        ):
            result = run_backfill(limit=1000, dry_run=False)

        assert result["labeled_legacy"] == 2

        conn = db_fixture._conn
        for h in ("hash_legacy_1", "hash_legacy_2"):
            row = conn.execute(
                f"SELECT llm_provider, llm_model FROM gold_layer.prediction_ledger "
                f"WHERE prediction_hash = '{h}'"
            ).fetchone()
            assert row[0] == LEGACY_PROVIDER, (
                f"{h}: expected {LEGACY_PROVIDER}, got {row[0]}"
            )
            assert row[1] == LEGACY_MODEL, f"{h}: expected {LEGACY_MODEL}, got {row[1]}"

    def test_dry_run_reports_counts_without_writing(self, db_fixture):
        with patch(
            "backfill_provider_attribution.get_db_manager", return_value=db_fixture
        ):
            result = run_backfill(limit=1000, dry_run=True)

        assert result["dry_run"] is True
        assert result["null_rows_found"] == 3
        assert result["rows_updated"] == 0

        # Verify nothing was written
        conn = db_fixture._conn
        still_null = conn.execute(
            "SELECT COUNT(*) FROM gold_layer.prediction_ledger WHERE llm_provider IS NULL"
        ).fetchone()[0]
        assert still_null == 3
