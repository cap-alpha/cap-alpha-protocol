"""
Tests for Phase 0 exact-match claim deduplication (Issue #808).

Covers:
  - compute_claim_norm_key: deterministic hashing, NULL-field handling
  - check_claim_is_duplicate: BQ query, found/not-found paths, fail-open on error
  - log_duplicate_claim: BQ write path, fail-open on error
  - run_extraction integration:
    * new unique claim passes through to prediction_ledger
    * exact duplicate is logged to claim_dedup_log, NOT re-inserted
    * near-duplicate with different entity is NOT flagged (different norm_key)
"""

import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.assertion_extractor import (
    ExtractionResult,
    check_claim_is_duplicate,
    compute_claim_norm_key,
    log_duplicate_claim,
    run_extraction,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.fetch_df.return_value = pd.DataFrame()
    return db


@pytest.fixture
def mock_provider():
    provider = MagicMock()
    provider.model = "mock-model"
    provider.extract_predictions.return_value = []
    return provider


@pytest.fixture(autouse=True)
def set_gcp_project(monkeypatch):
    """All tests in this module need GCP_PROJECT_ID set."""
    monkeypatch.setenv("GCP_PROJECT_ID", "test-project")


# ---------------------------------------------------------------------------
# Sample predictions
# ---------------------------------------------------------------------------

MAHOMES_PRED = {
    "extracted_claim": "Patrick Mahomes will win MVP in 2026",
    "claim_category": "award_prediction",
    "season_year": 2026,
    "target_player": "Patrick Mahomes",
    "target_team": "KC",
    "stance": "bullish",
}

ALLEN_PRED = {
    "extracted_claim": "Josh Allen will win MVP in 2026",
    "claim_category": "award_prediction",
    "season_year": 2026,
    "target_player": "Josh Allen",
    "target_team": "BUF",
    "stance": "bullish",
}


def make_raw_media_df(n=1):
    rows = []
    for i in range(n):
        rows.append(
            {
                "content_hash": f"hash_{i}",
                "source_id": "espn_nfl",
                "title": f"Article {i}",
                "raw_text": (
                    "Patrick Mahomes will almost certainly win the NFL MVP award "
                    "this season based on his outstanding performance throughout "
                    "the year. The Kansas City Chiefs quarterback has posted "
                    "remarkable numbers week after week, and league analysts "
                    "widely agree that no other player comes close to matching "
                    "his production and leadership on the field this campaign."
                ),
                "source_url": f"https://espn.com/article/{i}",
                "author": "Adam Schefter",
                "matched_pundit_id": "adam_schefter",
                "matched_pundit_name": "Adam Schefter",
                "published_at": datetime(2026, 9, 1, tzinfo=timezone.utc),
                "sport": "NFL",
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# compute_claim_norm_key
# ---------------------------------------------------------------------------


class TestComputeClaimNormKey:
    def test_returns_64_char_hex_string(self):
        key = compute_claim_norm_key(
            "player_performance", "Patrick Mahomes", "KC", 2026
        )
        assert len(key) == 64
        assert all(c in "0123456789abcdef" for c in key)

    def test_deterministic(self):
        """Same inputs always produce the same key."""
        key1 = compute_claim_norm_key(
            "player_performance", "Patrick Mahomes", "KC", 2026
        )
        key2 = compute_claim_norm_key(
            "player_performance", "Patrick Mahomes", "KC", 2026
        )
        assert key1 == key2

    def test_none_fields_treated_as_empty_string(self):
        """NULL player / team / season produce a valid, deterministic key."""
        key = compute_claim_norm_key("game_outcome", None, None, None)
        assert len(key) == 64

    def test_none_fields_consistent(self):
        key1 = compute_claim_norm_key("trade", None, None, None)
        key2 = compute_claim_norm_key("trade", None, None, None)
        assert key1 == key2

    def test_different_team_produces_different_key(self):
        key_kc = compute_claim_norm_key(
            "player_performance", "Patrick Mahomes", "KC", 2026
        )
        key_sf = compute_claim_norm_key(
            "player_performance", "Patrick Mahomes", "SF", 2026
        )
        assert key_kc != key_sf

    def test_different_player_produces_different_key(self):
        key_mahomes = compute_claim_norm_key(
            "award_prediction", "Patrick Mahomes", "KC", 2026
        )
        key_allen = compute_claim_norm_key(
            "award_prediction", "Josh Allen", "BUF", 2026
        )
        assert key_mahomes != key_allen

    def test_different_season_produces_different_key(self):
        key_2026 = compute_claim_norm_key(
            "player_performance", "Patrick Mahomes", "KC", 2026
        )
        key_2027 = compute_claim_norm_key(
            "player_performance", "Patrick Mahomes", "KC", 2027
        )
        assert key_2026 != key_2027

    def test_different_category_produces_different_key(self):
        key_perf = compute_claim_norm_key("player_performance", "Kelce", "KC", 2026)
        key_trade = compute_claim_norm_key("trade", "Kelce", "KC", 2026)
        assert key_perf != key_trade

    def test_case_insensitive(self):
        """Keys are lowercased before hashing, so case variants collide."""
        key_lower = compute_claim_norm_key(
            "player_performance", "patrick mahomes", "kc", 2026
        )
        key_mixed = compute_claim_norm_key(
            "player_performance", "Patrick Mahomes", "KC", 2026
        )
        # After lower() both collapse to the same string
        assert key_lower == key_mixed

    def test_season_year_int_and_none_differ(self):
        key_with_year = compute_claim_norm_key("trade", "Player X", "TM", 2026)
        key_no_year = compute_claim_norm_key("trade", "Player X", "TM", None)
        assert key_with_year != key_no_year


# ---------------------------------------------------------------------------
# check_claim_is_duplicate
# ---------------------------------------------------------------------------


class TestCheckClaimIsDuplicate:
    def test_returns_none_when_no_match(self, mock_db):
        mock_db.fetch_df.return_value = pd.DataFrame()
        result = check_claim_is_duplicate("abc123", mock_db)
        assert result is None

    def test_returns_canonical_hash_when_match_found(self, mock_db):
        mock_db.fetch_df.return_value = pd.DataFrame(
            [{"prediction_hash": "canonical_hash_hex"}]
        )
        result = check_claim_is_duplicate("abc123", mock_db)
        assert result == "canonical_hash_hex"

    def test_queries_prediction_ledger(self, mock_db):
        mock_db.fetch_df.return_value = pd.DataFrame()
        check_claim_is_duplicate("norm_key_value", mock_db)
        query_used = mock_db.fetch_df.call_args[0][0]
        assert "prediction_ledger" in query_used
        assert "claim_norm_key" in query_used

    def test_uses_parameterised_query(self, mock_db):
        """Norm key must be a bound parameter, not interpolated into SQL."""
        mock_db.fetch_df.return_value = pd.DataFrame()
        check_claim_is_duplicate("my_norm_key", mock_db)
        query_used = mock_db.fetch_df.call_args[0][0]
        assert "@norm_key" in query_used
        assert "my_norm_key" not in query_used

    def test_fail_open_on_exception(self, mock_db):
        """If BQ throws, treat as non-duplicate (fail-open) so ingestion proceeds."""
        mock_db.fetch_df.side_effect = Exception("BQ connection error")
        result = check_claim_is_duplicate("abc123", mock_db)
        assert result is None

    def test_returns_none_when_gcp_project_id_missing(self, mock_db, monkeypatch):
        """Without GCP_PROJECT_ID, return None (fail-open) rather than erroring."""
        monkeypatch.delenv("GCP_PROJECT_ID", raising=False)
        result = check_claim_is_duplicate("abc123", mock_db)
        assert result is None
        mock_db.fetch_df.assert_not_called()


# ---------------------------------------------------------------------------
# log_duplicate_claim
# ---------------------------------------------------------------------------


class TestLogDuplicateClaim:
    def test_writes_to_dedup_log_table(self, mock_db):
        """log_duplicate_claim should call load_table_from_dataframe on the BQ client."""
        mock_job = MagicMock()
        mock_db.client.load_table_from_dataframe.return_value = mock_job

        log_duplicate_claim(
            dupe_hash="dupe123",
            canonical_hash="canon456",
            norm_key="norm789",
            pundit_id="adam_schefter",
            db=mock_db,
        )

        mock_db.client.load_table_from_dataframe.assert_called_once()
        call_args = mock_db.client.load_table_from_dataframe.call_args
        df_written = call_args[0][0]
        table_ref = call_args[0][1]

        assert "claim_dedup_log" in table_ref
        assert len(df_written) == 1
        row = df_written.iloc[0]
        assert row["dupe_hash"] == "dupe123"
        assert row["canonical_hash"] == "canon456"
        assert row["norm_key"] == "norm789"
        assert row["pundit_id"] == "adam_schefter"
        assert row["match_type"] == "exact"

    def test_fail_open_on_bq_error(self, mock_db):
        """BQ write failure must NOT propagate — just log a warning."""
        mock_db.client.load_table_from_dataframe.side_effect = Exception("BQ error")
        # Should not raise
        log_duplicate_claim("d", "c", "n", "pundit_x", db=mock_db)

    def test_ingested_at_is_utc(self, mock_db):
        mock_job = MagicMock()
        mock_db.client.load_table_from_dataframe.return_value = mock_job

        log_duplicate_claim("d", "c", "n", "p", db=mock_db)

        df_written = mock_db.client.load_table_from_dataframe.call_args[0][0]
        ingested_at = df_written.iloc[0]["ingested_at"]
        assert ingested_at.tzinfo is not None  # timezone-aware


# ---------------------------------------------------------------------------
# run_extraction integration tests for dedup gate
# ---------------------------------------------------------------------------


class TestRunExtractionDedupGate:
    """Integration tests verifying the dedup gate inside run_extraction."""

    @patch("src.assertion_extractor.check_claim_is_duplicate")
    @patch("src.assertion_extractor.ingest_batch")
    @patch("src.assertion_extractor.extract_assertions")
    def test_unique_claim_passes_through(
        self, mock_extract, mock_ingest, mock_check_dup, mock_db, mock_provider
    ):
        """A claim with no existing duplicate is ingested into prediction_ledger."""
        mock_db.fetch_df.return_value = make_raw_media_df(1)
        mock_extract.return_value = ExtractionResult(
            content_hash="hash_0",
            predictions=[MAHOMES_PRED],
        )
        mock_ingest.return_value = ["pred_hash_1"]
        mock_check_dup.return_value = None  # no duplicate found

        summary = run_extraction(limit=10, db=mock_db, provider=mock_provider)

        assert summary["predictions_ingested"] == 1
        assert summary["duplicates_suppressed"] == 0
        mock_ingest.assert_called_once()
        # The prediction passed to ingest_batch should have claim_norm_key set
        passed_prediction = mock_ingest.call_args[0][0][0]
        assert passed_prediction.claim_norm_key is not None

    @patch("src.assertion_extractor.log_duplicate_claim")
    @patch("src.assertion_extractor.check_claim_is_duplicate")
    @patch("src.assertion_extractor.ingest_batch")
    @patch("src.assertion_extractor.extract_assertions")
    def test_exact_duplicate_is_logged_not_inserted(
        self,
        mock_extract,
        mock_ingest,
        mock_check_dup,
        mock_log_dup,
        mock_db,
        mock_provider,
    ):
        """An exact-match duplicate is written to claim_dedup_log and NOT to prediction_ledger."""
        mock_db.fetch_df.return_value = make_raw_media_df(1)
        mock_extract.return_value = ExtractionResult(
            content_hash="hash_0",
            predictions=[MAHOMES_PRED],
        )
        # Simulate that the claim already exists in the ledger
        mock_check_dup.return_value = "existing_canonical_hash_abc123"

        summary = run_extraction(limit=10, db=mock_db, provider=mock_provider)

        # Duplicate must be suppressed from the ledger
        assert summary["duplicates_suppressed"] == 1
        assert summary["predictions_ingested"] == 0
        mock_ingest.assert_not_called()

        # Must be logged to claim_dedup_log
        mock_log_dup.assert_called_once()
        log_kwargs = mock_log_dup.call_args[1]  # keyword args
        assert log_kwargs["canonical_hash"] == "existing_canonical_hash_abc123"
        assert log_kwargs["pundit_id"] == "adam_schefter"

    @patch("src.assertion_extractor.log_duplicate_claim")
    @patch("src.assertion_extractor.check_claim_is_duplicate")
    @patch("src.assertion_extractor.ingest_batch")
    @patch("src.assertion_extractor.extract_assertions")
    def test_near_duplicate_with_different_entity_not_flagged(
        self,
        mock_extract,
        mock_ingest,
        mock_check_dup,
        mock_log_dup,
        mock_db,
        mock_provider,
    ):
        """
        Two claims with different entities (Mahomes vs Allen) must produce different
        norm_keys and therefore NOT suppress each other, even if their claim_category
        and season_year are the same.
        """
        # Both predictions in a single article
        mock_db.fetch_df.return_value = make_raw_media_df(1)
        mock_extract.return_value = ExtractionResult(
            content_hash="hash_0",
            predictions=[MAHOMES_PRED, ALLEN_PRED],
        )
        mock_ingest.return_value = ["pred_hash_x"]
        mock_check_dup.return_value = None  # neither is in the ledger

        summary = run_extraction(limit=10, db=mock_db, provider=mock_provider)

        # Both should be ingested, none suppressed
        assert summary["duplicates_suppressed"] == 0
        mock_ingest.assert_called_once()
        mock_log_dup.assert_not_called()

        # Verify two distinct norm_keys were checked (Mahomes and Allen differ)
        checked_keys = [c[0][0] for c in mock_check_dup.call_args_list]
        assert len(checked_keys) == 2
        assert len(set(checked_keys)) == 2, (
            "Mahomes and Allen must produce distinct norm_keys"
        )

    @patch("src.assertion_extractor.check_claim_is_duplicate")
    @patch("src.assertion_extractor.ingest_batch")
    @patch("src.assertion_extractor.extract_assertions")
    def test_dedup_check_fail_open_allows_ingestion(
        self, mock_extract, mock_ingest, mock_check_dup, mock_db, mock_provider
    ):
        """If the dedup BQ check returns None (fail-open), the claim still proceeds."""
        mock_db.fetch_df.return_value = make_raw_media_df(1)
        mock_extract.return_value = ExtractionResult(
            content_hash="hash_0",
            predictions=[MAHOMES_PRED],
        )
        mock_ingest.return_value = ["pred_hash_1"]
        mock_check_dup.return_value = None  # fail-open

        summary = run_extraction(limit=10, db=mock_db, provider=mock_provider)

        assert summary["predictions_ingested"] == 1
        assert summary["duplicates_suppressed"] == 0

    @patch("src.assertion_extractor.log_duplicate_claim")
    @patch("src.assertion_extractor.check_claim_is_duplicate")
    @patch("src.assertion_extractor.ingest_batch")
    @patch("src.assertion_extractor.extract_assertions")
    def test_mixed_batch_one_dup_one_unique(
        self,
        mock_extract,
        mock_ingest,
        mock_check_dup,
        mock_log_dup,
        mock_db,
        mock_provider,
    ):
        """When one claim is unique and one is a dup, only the unique one goes to the ledger."""
        mock_db.fetch_df.return_value = make_raw_media_df(1)
        mock_extract.return_value = ExtractionResult(
            content_hash="hash_0",
            predictions=[MAHOMES_PRED, ALLEN_PRED],
        )
        mock_ingest.return_value = ["pred_hash_1"]

        # Mahomes is a dup; Allen is unique
        mahomes_key = compute_claim_norm_key(
            "award_prediction", "Patrick Mahomes", "KC", 2026
        )

        def side_effect(norm_key, db, source_url=None, pundit_id=None):
            if norm_key == mahomes_key:
                return "canonical_mahomes_hash"
            return None

        mock_check_dup.side_effect = side_effect

        summary = run_extraction(limit=10, db=mock_db, provider=mock_provider)

        assert summary["duplicates_suppressed"] == 1
        assert summary["predictions_ingested"] == 1
        mock_log_dup.assert_called_once()
        mock_ingest.assert_called_once()

        # The ingested prediction should be Allen, not Mahomes
        passed_predictions = mock_ingest.call_args[0][0]
        assert len(passed_predictions) == 1
        assert passed_predictions[0].target_player_name == "Josh Allen"

    @patch("src.assertion_extractor.check_claim_is_duplicate")
    @patch("src.assertion_extractor.extract_assertions")
    def test_duplicates_suppressed_in_summary(
        self, mock_extract, mock_check_dup, mock_db, mock_provider
    ):
        """summary dict always has duplicates_suppressed key, even when zero."""
        mock_db.fetch_df.return_value = make_raw_media_df(1)
        mock_extract.return_value = ExtractionResult(
            content_hash="hash_0", predictions=[]
        )
        mock_check_dup.return_value = None

        summary = run_extraction(limit=10, db=mock_db, provider=mock_provider)

        assert "duplicates_suppressed" in summary
        assert summary["duplicates_suppressed"] == 0

    @patch("src.assertion_extractor.log_duplicate_claim")
    @patch("src.assertion_extractor.check_claim_is_duplicate")
    @patch("src.assertion_extractor.ingest_batch")
    @patch("src.assertion_extractor.extract_assertions")
    def test_claim_norm_key_set_on_ingested_predictions(
        self,
        mock_extract,
        mock_ingest,
        mock_check_dup,
        mock_log_dup,
        mock_db,
        mock_provider,
    ):
        """Predictions written to the ledger must carry their claim_norm_key."""
        mock_db.fetch_df.return_value = make_raw_media_df(1)
        mock_extract.return_value = ExtractionResult(
            content_hash="hash_0",
            predictions=[MAHOMES_PRED],
        )
        mock_ingest.return_value = ["pred_hash_1"]
        mock_check_dup.return_value = None

        run_extraction(limit=10, db=mock_db, provider=mock_provider)

        passed = mock_ingest.call_args[0][0][0]
        expected_key = compute_claim_norm_key(
            "award_prediction", "Patrick Mahomes", "KC", 2026
        )
        assert passed.claim_norm_key == expected_key
