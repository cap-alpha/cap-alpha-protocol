"""
Tests for Cross-Article Deduplication (Issue #210).
Unit tests only — no BigQuery required.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, call, patch

import pandas as pd
import pytest

from src.cross_article_dedup import (
    SIMILARITY_THRESHOLD,
    _find_duplicates_in_group,
    _get_pending_predictions,
    cross_article_dedup,
)

FAKE_HASH_1 = "a" * 64
FAKE_HASH_2 = "b" * 64
FAKE_HASH_3 = "c" * 64

BASE_TS = datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.fetch_df.return_value = pd.DataFrame()
    return db


def _make_prediction_row(
    prediction_hash: str,
    pundit_id: str,
    extracted_claim: str,
    claim_category: str = "player_performance",
    target_player_name: str = "Patrick Mahomes",
    ingestion_timestamp: datetime = None,
):
    return {
        "prediction_hash": prediction_hash,
        "pundit_id": pundit_id,
        "extracted_claim": extracted_claim,
        "claim_category": claim_category,
        "target_player_name": target_player_name,
        "ingestion_timestamp": ingestion_timestamp or BASE_TS,
    }


# ---------------------------------------------------------------------------
# _find_duplicates_in_group
# ---------------------------------------------------------------------------


class TestFindDuplicatesInGroup:
    def test_single_entry_returns_empty(self):
        df = pd.DataFrame(
            [
                _make_prediction_row(
                    FAKE_HASH_1,
                    "adam_schefter",
                    "Mahomes will win MVP in 2025",
                )
            ]
        )
        assert _find_duplicates_in_group(df) == []

    def test_empty_group_returns_empty(self):
        df = pd.DataFrame(
            columns=[
                "prediction_hash",
                "pundit_id",
                "extracted_claim",
                "claim_category",
                "target_player_name",
                "ingestion_timestamp",
            ]
        )
        assert _find_duplicates_in_group(df) == []

    def test_two_similar_claims_voids_later_one(self):
        """Two articles from different sources, same pundit, same claim."""
        df = pd.DataFrame(
            [
                _make_prediction_row(
                    FAKE_HASH_1,
                    "adam_schefter",
                    "Patrick Mahomes will win MVP in the 2025 season",
                    ingestion_timestamp=BASE_TS,
                ),
                _make_prediction_row(
                    FAKE_HASH_2,
                    "adam_schefter",
                    "Mahomes will win the MVP in 2025",
                    ingestion_timestamp=BASE_TS + timedelta(hours=2),
                ),
            ]
        )
        to_void = _find_duplicates_in_group(df)
        assert len(to_void) == 1
        assert FAKE_HASH_2 in to_void  # later one gets voided

    def test_two_different_claims_both_kept(self):
        """Two articles, same pundit, different claims -- both kept."""
        df = pd.DataFrame(
            [
                _make_prediction_row(
                    FAKE_HASH_1,
                    "adam_schefter",
                    "Patrick Mahomes will win MVP in 2025",
                    ingestion_timestamp=BASE_TS,
                ),
                _make_prediction_row(
                    FAKE_HASH_2,
                    "adam_schefter",
                    "The Chiefs will trade Kelce before the deadline",
                    ingestion_timestamp=BASE_TS + timedelta(hours=2),
                ),
            ]
        )
        to_void = _find_duplicates_in_group(df)
        assert len(to_void) == 0

    def test_three_articles_two_similar_one_different(self):
        """Three articles: two have similar claims, one is different.
        One should be voided, two should remain."""
        df = pd.DataFrame(
            [
                _make_prediction_row(
                    FAKE_HASH_1,
                    "adam_schefter",
                    "Patrick Mahomes will win MVP in the 2025 season",
                    ingestion_timestamp=BASE_TS,
                ),
                _make_prediction_row(
                    FAKE_HASH_2,
                    "adam_schefter",
                    "The Bears will make the playoffs in 2025",
                    ingestion_timestamp=BASE_TS + timedelta(hours=1),
                ),
                _make_prediction_row(
                    FAKE_HASH_3,
                    "adam_schefter",
                    "Mahomes will win the 2025 MVP award",
                    ingestion_timestamp=BASE_TS + timedelta(hours=3),
                ),
            ]
        )
        to_void = _find_duplicates_in_group(df)
        assert len(to_void) == 1
        assert FAKE_HASH_3 in to_void  # third is duplicate of first
        assert FAKE_HASH_1 not in to_void  # earliest kept
        assert FAKE_HASH_2 not in to_void  # different claim kept

    def test_keeps_earliest_by_timestamp(self):
        """Even if the later entry was ingested first in the list,
        sorting by ingestion_timestamp keeps the earliest."""
        df = pd.DataFrame(
            [
                _make_prediction_row(
                    FAKE_HASH_2,
                    "adam_schefter",
                    "Mahomes will win the MVP in 2025",
                    ingestion_timestamp=BASE_TS + timedelta(hours=5),
                ),
                _make_prediction_row(
                    FAKE_HASH_1,
                    "adam_schefter",
                    "Patrick Mahomes will win MVP in 2025 season",
                    ingestion_timestamp=BASE_TS,
                ),
            ]
        )
        to_void = _find_duplicates_in_group(df)
        assert len(to_void) == 1
        assert FAKE_HASH_2 in to_void  # later timestamp gets voided


# ---------------------------------------------------------------------------
# cross_article_dedup (integration)
# ---------------------------------------------------------------------------


class TestCrossArticleDedup:
    @patch("src.cross_article_dedup.void_prediction")
    def test_voids_duplicates(self, mock_void, mock_db):
        """End-to-end: two similar claims from same pundit get one voided."""
        mock_db.fetch_df.return_value = pd.DataFrame(
            [
                _make_prediction_row(
                    FAKE_HASH_1,
                    "adam_schefter",
                    "Patrick Mahomes will win MVP in 2025",
                    ingestion_timestamp=BASE_TS,
                ),
                _make_prediction_row(
                    FAKE_HASH_2,
                    "adam_schefter",
                    "Mahomes will win the MVP in the 2025 season",
                    ingestion_timestamp=BASE_TS + timedelta(hours=3),
                ),
            ]
        )

        result = cross_article_dedup(db=mock_db, dry_run=False)

        assert result["duplicates_found"] == 1
        assert result["duplicates_voided"] == 1
        mock_void.assert_called_once_with(
            prediction_hash=FAKE_HASH_2,
            reason="cross_article_duplicate",
            db=mock_db,
        )

    @patch("src.cross_article_dedup.void_prediction")
    def test_dry_run_does_not_void(self, mock_void, mock_db):
        """Dry run finds duplicates but does not void them."""
        mock_db.fetch_df.return_value = pd.DataFrame(
            [
                _make_prediction_row(
                    FAKE_HASH_1,
                    "adam_schefter",
                    "Patrick Mahomes will win MVP in 2025",
                    ingestion_timestamp=BASE_TS,
                ),
                _make_prediction_row(
                    FAKE_HASH_2,
                    "adam_schefter",
                    "Mahomes will win the MVP in the 2025 season",
                    ingestion_timestamp=BASE_TS + timedelta(hours=3),
                ),
            ]
        )

        result = cross_article_dedup(db=mock_db, dry_run=True)

        assert result["duplicates_found"] == 1
        assert result["duplicates_voided"] == 0
        mock_void.assert_not_called()

    @patch("src.cross_article_dedup.void_prediction")
    def test_different_pundits_not_deduped(self, mock_void, mock_db):
        """Same claim from different pundits should NOT be deduplicated."""
        mock_db.fetch_df.return_value = pd.DataFrame(
            [
                _make_prediction_row(
                    FAKE_HASH_1,
                    "adam_schefter",
                    "Patrick Mahomes will win MVP in 2025",
                    ingestion_timestamp=BASE_TS,
                ),
                _make_prediction_row(
                    FAKE_HASH_2,
                    "pat_mcafee",
                    "Patrick Mahomes will win MVP in 2025",
                    ingestion_timestamp=BASE_TS + timedelta(hours=3),
                ),
            ]
        )

        result = cross_article_dedup(db=mock_db, dry_run=False)

        assert result["duplicates_found"] == 0
        mock_void.assert_not_called()

    @patch("src.cross_article_dedup.void_prediction")
    def test_different_categories_not_deduped(self, mock_void, mock_db):
        """Same pundit, similar claim text but different category -- kept."""
        mock_db.fetch_df.return_value = pd.DataFrame(
            [
                _make_prediction_row(
                    FAKE_HASH_1,
                    "adam_schefter",
                    "Mahomes will have a great 2025",
                    claim_category="player_performance",
                    ingestion_timestamp=BASE_TS,
                ),
                _make_prediction_row(
                    FAKE_HASH_2,
                    "adam_schefter",
                    "Mahomes will have a great 2025",
                    claim_category="game_outcome",
                    ingestion_timestamp=BASE_TS + timedelta(hours=3),
                ),
            ]
        )

        result = cross_article_dedup(db=mock_db, dry_run=False)

        assert result["duplicates_found"] == 0
        mock_void.assert_not_called()

    @patch("src.cross_article_dedup.void_prediction")
    def test_no_pending_predictions(self, mock_void, mock_db):
        """No pending predictions means nothing to do."""
        mock_db.fetch_df.return_value = pd.DataFrame()

        result = cross_article_dedup(db=mock_db)

        assert result["total_pending"] == 0
        assert result["duplicates_found"] == 0
        mock_void.assert_not_called()

    @patch("src.cross_article_dedup.void_prediction")
    def test_null_player_name_grouped_together(self, mock_void, mock_db):
        """Predictions with None target_player_name are grouped together."""
        mock_db.fetch_df.return_value = pd.DataFrame(
            [
                _make_prediction_row(
                    FAKE_HASH_1,
                    "adam_schefter",
                    "The Bears will make the playoffs in 2025",
                    target_player_name=None,
                    ingestion_timestamp=BASE_TS,
                ),
                _make_prediction_row(
                    FAKE_HASH_2,
                    "adam_schefter",
                    "Bears will make the 2025 playoffs",
                    target_player_name=None,
                    ingestion_timestamp=BASE_TS + timedelta(hours=2),
                ),
            ]
        )

        result = cross_article_dedup(db=mock_db, dry_run=False)

        assert result["duplicates_found"] == 1
        assert result["duplicates_voided"] == 1


class TestGetPendingPredictions:
    def test_queries_both_tables(self, mock_db):
        _get_pending_predictions(mock_db)
        query = mock_db.fetch_df.call_args[0][0]
        assert "prediction_ledger" in query
        assert "prediction_resolutions" in query

    def test_filters_for_pending(self, mock_db):
        _get_pending_predictions(mock_db)
        query = mock_db.fetch_df.call_args[0][0]
        assert "PENDING" in query
