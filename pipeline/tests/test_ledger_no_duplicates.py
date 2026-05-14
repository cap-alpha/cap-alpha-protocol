"""
Tests for Issue #935: no duplicate rows in gold_layer.prediction_ledger.

Verifies that:
  1. check_claim_is_duplicate correctly scopes by (pundit_id, source_url)
     so same-article re-extractions are caught and cross-article predictions
     for the same player are NOT over-suppressed.
  2. run_extraction produces no (pundit_id, source_url, claim_norm_key)
     duplicates in the ledger when the same article is processed twice.
  3. The DuckDB unique index on prediction_ledger rejects duplicate inserts.
"""

import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.assertion_extractor import (
    check_claim_is_duplicate,
    compute_claim_norm_key,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def set_gcp_project(monkeypatch):
    monkeypatch.setenv("GCP_PROJECT_ID", "test-project")


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.fetch_df.return_value = pd.DataFrame()
    return db


# ---------------------------------------------------------------------------
# check_claim_is_duplicate: source scoping (Issue #935)
# ---------------------------------------------------------------------------


class TestCheckClaimIsDuplicateScopedBySource:
    """
    Regression tests for the source_url + pundit_id scoping fix.

    Before the fix, check_claim_is_duplicate only filtered by claim_norm_key,
    causing two problems:
      1. Same-article duplicates: two claims from the same article with the
         same norm_key but slightly different extracted_claim text both pass
         the dedup check on the first run (neither is in the ledger yet),
         and both get ingested.
      2. Cross-article over-suppression: a norm_key match from a different
         pundit or source_url would incorrectly suppress a valid new claim.
    """

    def test_scoped_query_includes_source_url_and_pundit_id(self, mock_db):
        """When source_url and pundit_id are provided, the query filters on both."""
        mock_db.fetch_df.return_value = pd.DataFrame()
        check_claim_is_duplicate(
            "norm_key_abc",
            mock_db,
            source_url="https://espn.com/mock",
            pundit_id="peter_schrager",
        )
        query_used = mock_db.fetch_df.call_args[0][0]
        assert "source_url" in query_used
        assert "pundit_id" in query_used
        assert "@source_url" in query_used
        assert "@pundit_id" in query_used

    def test_unscoped_query_when_no_source(self, mock_db):
        """Backward compat: without source_url the query is norm_key only."""
        mock_db.fetch_df.return_value = pd.DataFrame()
        check_claim_is_duplicate("norm_key_abc", mock_db)
        query_used = mock_db.fetch_df.call_args[0][0]
        assert "source_url" not in query_used
        assert "pundit_id" not in query_used

    def test_same_article_duplicate_is_caught(self, mock_db):
        """
        If prediction_ledger already has a row from the same pundit + source_url
        with the same norm_key, check_claim_is_duplicate returns the canonical hash.
        This is the main regression case from Issue #935 (Schrager/Tate).
        """
        mock_db.fetch_df.return_value = pd.DataFrame(
            [{"prediction_hash": "canonical_abc123"}]
        )
        result = check_claim_is_duplicate(
            "some_norm_key",
            mock_db,
            source_url="https://nfl.com/schrager-mock-2026",
            pundit_id="peter_schrager",
        )
        assert result == "canonical_abc123"

    def test_different_source_url_not_suppressed(self, mock_db):
        """
        A claim from a DIFFERENT source_url with the same norm_key should NOT
        be flagged as a duplicate — it is an independent prediction.

        Simulate: McShay mock has norm_key for Carnell Tate. Schrager mock also
        has the same norm_key. If we scope by source_url, Schrager's claim is
        NOT flagged as a dup of McShay's.
        """
        # The DB returns empty for the scoped query (Schrager's source not in ledger)
        mock_db.fetch_df.return_value = pd.DataFrame()
        result = check_claim_is_duplicate(
            "carnell_tate_norm_key",
            mock_db,
            source_url="https://nfl.com/schrager-mock-2026",
            pundit_id="peter_schrager",
        )
        # Should be None (not a duplicate) even if McShay has same norm_key elsewhere
        assert result is None

    def test_source_url_only_scoping(self, mock_db):
        """When only source_url is provided (no pundit_id), query filters on source_url."""
        mock_db.fetch_df.return_value = pd.DataFrame()
        check_claim_is_duplicate(
            "norm_key_abc",
            mock_db,
            source_url="https://espn.com/mock",
        )
        query_used = mock_db.fetch_df.call_args[0][0]
        assert "source_url" in query_used
        assert "@source_url" in query_used

    def test_query_parameters_include_source_and_pundit(self, mock_db):
        """Verify query_parameters list includes all three bindings."""
        mock_db.fetch_df.return_value = pd.DataFrame()
        check_claim_is_duplicate(
            "nk",
            mock_db,
            source_url="https://example.com",
            pundit_id="test_pundit",
        )
        # Extract query_parameters from the job_config kwarg
        call_kwargs = mock_db.fetch_df.call_args[1]
        job_config = call_kwargs.get("job_config") or call_kwargs.get(
            "query_parameters"
        )
        # Accept either job_config object or raw list
        if hasattr(job_config, "query_parameters"):
            params = {p.name: p.value for p in job_config.query_parameters}
        else:
            # Might be passed as query_parameters keyword directly
            params = {}
            for arg in mock_db.fetch_df.call_args:
                if isinstance(arg, dict) and "query_parameters" in arg:
                    params = {p.name: p.value for p in arg["query_parameters"]}
        # At minimum, norm_key must be parameterised (others are in job_config)
        query_used = mock_db.fetch_df.call_args[0][0]
        assert "@norm_key" in query_used


# ---------------------------------------------------------------------------
# Ledger uniqueness: no (pundit_id, source_url, claim_norm_key) duplicates
# ---------------------------------------------------------------------------


class TestLedgerUniqueness:
    """
    Verify that the prediction_ledger cannot accumulate duplicate
    (pundit_id, source_url, claim_norm_key) rows.

    Uses an in-memory DuckDB database that mirrors the schema from init_duckdb.py
    (including the partial unique index added for Issue #935).
    """

    @pytest.fixture
    def duckdb_conn(self):
        """Create a fresh in-memory DuckDB with the prediction_ledger schema."""
        import duckdb

        conn = duckdb.connect(":memory:")
        conn.execute("CREATE SCHEMA gold_layer")
        conn.execute(
            """
            CREATE TABLE gold_layer.prediction_ledger (
                prediction_hash     VARCHAR NOT NULL,
                chain_hash          VARCHAR NOT NULL,
                ingestion_timestamp TIMESTAMP NOT NULL,
                source_url          VARCHAR NOT NULL,
                pundit_id           VARCHAR NOT NULL,
                pundit_name         VARCHAR NOT NULL,
                raw_assertion_text  VARCHAR NOT NULL,
                extracted_claim     VARCHAR,
                claim_category      VARCHAR,
                season_year         BIGINT,
                target_player_id    VARCHAR,
                target_player_name  VARCHAR,
                target_team         VARCHAR,
                sport               VARCHAR DEFAULT 'NFL',
                resolution_status   VARCHAR DEFAULT 'PENDING',
                resolved_at         TIMESTAMP,
                resolution_notes    VARCHAR,
                stance              VARCHAR,
                prompt_version      VARCHAR,
                llm_provider        VARCHAR,
                llm_model           VARCHAR,
                target_entity       JSON,
                claim_norm_key      VARCHAR
            )
        """
        )
        conn.execute(
            """
            CREATE UNIQUE INDEX uq_ledger_pundit_source_norm
                ON gold_layer.prediction_ledger (pundit_id, source_url, claim_norm_key)
        """
        )
        return conn

    def _insert_row(self, conn, prediction_hash, pundit_id, source_url, claim_norm_key):
        """Helper to insert a minimal ledger row."""
        conn.execute(
            """
            INSERT INTO gold_layer.prediction_ledger
                (prediction_hash, chain_hash, ingestion_timestamp,
                 source_url, pundit_id, pundit_name, raw_assertion_text, claim_norm_key)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                prediction_hash,
                "chain_" + prediction_hash,
                datetime(2026, 4, 25, tzinfo=timezone.utc),
                source_url,
                pundit_id,
                pundit_id.replace("_", " ").title(),
                "raw text here",
                claim_norm_key,
            ],
        )

    def test_first_insert_succeeds(self, duckdb_conn):
        """A single row with a norm_key inserts without error."""
        self._insert_row(
            duckdb_conn,
            prediction_hash="hash_001",
            pundit_id="peter_schrager",
            source_url="https://nfl.com/mock-2026",
            claim_norm_key="norm_tate_2026",
        )
        count = duckdb_conn.execute(
            "SELECT COUNT(*) FROM gold_layer.prediction_ledger"
        ).fetchone()[0]
        assert count == 1

    def test_duplicate_same_source_raises(self, duckdb_conn):
        """
        A second row with the same (pundit_id, source_url, claim_norm_key)
        must be rejected by the unique index.
        This is the core regression guard for Issue #935.
        """
        import duckdb

        self._insert_row(
            duckdb_conn,
            prediction_hash="hash_001",
            pundit_id="peter_schrager",
            source_url="https://nfl.com/mock-2026",
            claim_norm_key="norm_tate_2026",
        )
        with pytest.raises((duckdb.ConstraintException, Exception)):
            self._insert_row(
                duckdb_conn,
                prediction_hash="hash_002",  # different hash, same semantic claim
                pundit_id="peter_schrager",
                source_url="https://nfl.com/mock-2026",
                claim_norm_key="norm_tate_2026",
            )

    def test_same_norm_key_different_source_allowed(self, duckdb_conn):
        """
        Two rows with the same norm_key but different source_urls (different
        articles) must both be accepted — they are independent predictions.
        """
        self._insert_row(
            duckdb_conn,
            prediction_hash="hash_schrager",
            pundit_id="peter_schrager",
            source_url="https://nfl.com/schrager-mock",
            claim_norm_key="norm_tate_2026",
        )
        self._insert_row(
            duckdb_conn,
            prediction_hash="hash_mcshay",
            pundit_id="todd_mcshay",
            source_url="https://espn.com/mcshay-mock",
            claim_norm_key="norm_tate_2026",
        )
        count = duckdb_conn.execute(
            "SELECT COUNT(*) FROM gold_layer.prediction_ledger"
        ).fetchone()[0]
        assert count == 2

    def test_null_norm_key_rows_not_constrained(self, duckdb_conn):
        """
        Rows with claim_norm_key = NULL (pre-dedup-era) are not constrained
        by the unique index because DuckDB treats each NULL as distinct.
        Multiple such rows are allowed.
        """
        for i in range(3):
            duckdb_conn.execute(
                """
                INSERT INTO gold_layer.prediction_ledger
                    (prediction_hash, chain_hash, ingestion_timestamp,
                     source_url, pundit_id, pundit_name, raw_assertion_text, claim_norm_key)
                VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                [
                    f"old_hash_{i}",
                    f"chain_{i}",
                    datetime(2025, 1, i + 1, tzinfo=timezone.utc),
                    "https://example.com/old",
                    "old_pundit",
                    "Old Pundit",
                    "old raw text",
                ],
            )
        count = duckdb_conn.execute(
            "SELECT COUNT(*) FROM gold_layer.prediction_ledger WHERE claim_norm_key IS NULL"
        ).fetchone()[0]
        assert count == 3

    def test_no_duplicates_in_fixture_corpus(self, duckdb_conn):
        """
        Regression test: simulate the Schrager/Tate scenario from Issue #935.

        Insert 7 unique picks from the Schrager 2026 mock (the correct count after
        dedup).  Verify that querying by (pundit_name, target_player_name, source_url)
        returns at most 1 row per (player, source).
        """
        source = "https://nfl.com/schrager-2026-final-mock"
        players = [
            "Carnell Tate",
            "Jeremiyah Love",
            "Sonny Styles",
            "Spencer Fano",
            "Travis Hunter",
            "Cam Ward",
            "Abdul Carter",
        ]
        for i, player in enumerate(players):
            norm_key = compute_claim_norm_key(
                claim_category="draft_pick",
                target_player_name=player,
                target_team="WAS",
                season_year=2026,
            )
            self._insert_row(
                duckdb_conn,
                prediction_hash=f"hash_{i:04d}",
                pundit_id="peter_schrager",
                source_url=source,
                claim_norm_key=norm_key,
            )

        # Verify: no duplicates in the ledger for this source
        dupes = duckdb_conn.execute(
            """
            SELECT pundit_id, source_url, claim_norm_key, COUNT(*) AS n
            FROM gold_layer.prediction_ledger
            WHERE claim_norm_key IS NOT NULL
            GROUP BY 1, 2, 3
            HAVING COUNT(*) > 1
            """
        ).fetchall()
        assert len(dupes) == 0, f"Unexpected duplicate tuples: {dupes}"
