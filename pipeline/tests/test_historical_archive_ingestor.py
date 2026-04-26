"""
Tests for the Historical Archive Ingestor (historical backfill pipeline).
Unit tests — no network, no BigQuery, no LLM required.
"""

import hashlib
import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.historical_archive_ingestor import (
    NFL_TEAMS,
    ArchiveArticle,
    build_article_catalog,
    check_yield,
    compute_content_hash,
    fetch_and_ingest_article,
    run_historical_ingestion,
)


# ---------------------------------------------------------------------------
# build_article_catalog
# ---------------------------------------------------------------------------


class TestBuildArticleCatalog:
    def test_returns_list_of_archive_articles(self):
        catalog = build_article_catalog(seasons=[2023])
        assert len(catalog) > 0
        assert all(isinstance(a, ArchiveArticle) for a in catalog)

    def test_all_seasons_covered(self):
        catalog = build_article_catalog(seasons=[2020, 2021, 2022, 2023, 2024])
        years_in_catalog = {a.season_year for a in catalog}
        assert years_in_catalog == {2020, 2021, 2022, 2023, 2024}

    def test_no_duplicate_urls(self):
        catalog = build_article_catalog(seasons=[2022, 2023])
        urls = [a.original_url for a in catalog]
        assert len(urls) == len(set(urls)), "Duplicate URLs in catalog"

    def test_article_types_present(self):
        catalog = build_article_catalog(seasons=[2022])
        types = {a.article_type for a in catalog}
        # Should have at least bold_predictions, season_preview, award_prediction
        assert "bold_predictions" in types
        assert "season_preview" in types
        assert "award_prediction" in types

    def test_valid_source_ids(self):
        catalog = build_article_catalog(seasons=[2022])
        for a in catalog:
            assert a.source_id.endswith("_archive") or a.source_id in (
                "bleacher_report_archive",
                "cbs_nfl_archive",
                "espn_nfl_archive",
                "theringer_nfl_archive",
                "si_nfl_archive",
                "pft_nbc_archive",
                "yahoo_nfl_archive",
                "pff_archive",
            ), f"Unexpected source_id: {a.source_id}"

    def test_single_season_filter(self):
        catalog_2020 = build_article_catalog(seasons=[2020])
        catalog_2023 = build_article_catalog(seasons=[2023])
        # Sizes should be similar (same patterns per year)
        assert len(catalog_2020) == len(catalog_2023)

    def test_wayback_dates_match_seasons(self):
        """Wayback dates should correspond to the season year."""
        catalog = build_article_catalog(seasons=[2022])
        for a in catalog:
            assert a.wayback_date.startswith(str(a.season_year)), (
                f"Wayback date {a.wayback_date} doesn't match season {a.season_year}"
            )

    def test_high_density_types_first(self):
        """Bold predictions should be in the catalog (highest density)."""
        catalog = build_article_catalog(seasons=[2021])
        bold_preds = [a for a in catalog if a.article_type == "bold_predictions"]
        assert len(bold_preds) > 0

    def test_bleacher_report_included(self):
        catalog = build_article_catalog(seasons=[2022])
        br_articles = [a for a in catalog if "bleacher" in a.source_id.lower()]
        assert len(br_articles) > 0


# ---------------------------------------------------------------------------
# compute_content_hash
# ---------------------------------------------------------------------------


class TestComputeContentHash:
    def test_deterministic(self):
        h1 = compute_content_hash("https://example.com/article", "My Title")
        h2 = compute_content_hash("https://example.com/article", "My Title")
        assert h1 == h2

    def test_different_urls_different_hashes(self):
        h1 = compute_content_hash("https://example.com/a", "title")
        h2 = compute_content_hash("https://example.com/b", "title")
        assert h1 != h2

    def test_empty_title_ok(self):
        h = compute_content_hash("https://example.com/a")
        assert isinstance(h, str) and len(h) == 64  # sha256 hex = 64 chars

    def test_matches_media_ingestor_logic(self):
        """Hash must be identical to the media_ingestor's compute_content_hash."""
        url = "https://example.com/test"
        title = "Test Title"
        expected = hashlib.sha256(f"{url}|{title}".encode("utf-8")).hexdigest()
        assert compute_content_hash(url, title) == expected


# ---------------------------------------------------------------------------
# fetch_and_ingest_article
# ---------------------------------------------------------------------------


class TestFetchAndIngestArticle:
    def _make_article(self, season_year=2022):
        return ArchiveArticle(
            original_url="https://bleacherreport.com/articles/bold-predictions-2022",
            source_id="bleacher_report_archive",
            pundit_name="BR Staff",
            pundit_id="br_nfl_staff",
            season_year=season_year,
            article_type="bold_predictions",
            wayback_date="20220810",
        )

    @patch("src.historical_archive_ingestor.get_wayback_url")
    def test_returns_none_when_no_snapshot(self, mock_wb):
        mock_wb.return_value = None
        article = self._make_article()
        result = fetch_and_ingest_article(article, set(), db=None, dry_run=True)
        assert result is None

    @patch("src.historical_archive_ingestor.fetch_wayback_text")
    @patch("src.historical_archive_ingestor.get_wayback_url")
    def test_returns_none_when_text_extraction_fails(self, mock_wb, mock_text):
        mock_wb.return_value = (
            "https://web.archive.org/web/20220810000000/https://br.com/article"
        )
        mock_text.return_value = None
        article = self._make_article()
        result = fetch_and_ingest_article(article, set(), db=None, dry_run=True)
        assert result is None

    @patch("src.historical_archive_ingestor.fetch_wayback_text")
    @patch("src.historical_archive_ingestor.get_wayback_url")
    def test_returns_row_on_success_dry_run(self, mock_wb, mock_text):
        wayback_url = (
            "https://web.archive.org/web/20220810000000/https://br.com/article"
        )
        mock_wb.return_value = wayback_url
        mock_text.return_value = (
            "10 Bold Predictions for 2022 NFL Season",
            "Patrick Mahomes will win MVP. The Chiefs will win the Super Bowl. " * 50,
            "BR Staff",
        )
        article = self._make_article()
        result = fetch_and_ingest_article(article, set(), db=None, dry_run=True)
        assert result is not None
        assert result["source_id"] == "bleacher_report_archive"
        assert result["sport"] == "NFL"
        assert result["fetch_source_type"] == "wayback_machine"
        assert result["matched_pundit_id"] == "br_nfl_staff"

    @patch("src.historical_archive_ingestor.fetch_wayback_text")
    @patch("src.historical_archive_ingestor.get_wayback_url")
    def test_skips_already_ingested_hash(self, mock_wb, mock_text):
        wayback_url = (
            "https://web.archive.org/web/20220810000000/https://br.com/article"
        )
        mock_wb.return_value = wayback_url
        title = "10 Bold Predictions"
        mock_text.return_value = (title, "article text " * 50, "BR Staff")
        article = self._make_article()
        # Pre-populate existing_hashes with the hash that would be computed
        existing = {compute_content_hash(wayback_url, title)}
        result = fetch_and_ingest_article(article, existing, db=None, dry_run=True)
        assert result is None

    @patch("src.historical_archive_ingestor.fetch_wayback_text")
    @patch("src.historical_archive_ingestor.get_wayback_url")
    def test_metadata_includes_is_historical(self, mock_wb, mock_text):
        wayback_url = (
            "https://web.archive.org/web/20220810000000/https://br.com/article"
        )
        mock_wb.return_value = wayback_url
        mock_text.return_value = (
            "Bold Predictions 2022",
            "article text " * 50,
            None,
        )
        article = self._make_article()
        result = fetch_and_ingest_article(article, set(), db=None, dry_run=True)
        assert result is not None
        metadata = json.loads(result["raw_metadata"])
        assert metadata["is_historical"] is True
        assert metadata["season_year"] == 2022

    @patch("src.historical_archive_ingestor.fetch_wayback_text")
    @patch("src.historical_archive_ingestor.get_wayback_url")
    def test_writes_to_db_when_not_dry_run(self, mock_wb, mock_text):
        wayback_url = (
            "https://web.archive.org/web/20220810000000/https://br.com/article"
        )
        mock_wb.return_value = wayback_url
        mock_text.return_value = ("Title", "text content " * 50, "Author")
        article = self._make_article()
        mock_db = MagicMock()
        result = fetch_and_ingest_article(article, set(), db=mock_db, dry_run=False)
        assert result is not None
        mock_db.append_dataframe_to_table.assert_called_once()

    @patch("src.historical_archive_ingestor.fetch_wayback_text")
    @patch("src.historical_archive_ingestor.get_wayback_url")
    def test_does_not_write_to_db_in_dry_run(self, mock_wb, mock_text):
        wayback_url = (
            "https://web.archive.org/web/20220810000000/https://br.com/article"
        )
        mock_wb.return_value = wayback_url
        mock_text.return_value = ("Title", "text content " * 50, "Author")
        article = self._make_article()
        mock_db = MagicMock()
        fetch_and_ingest_article(article, set(), db=mock_db, dry_run=True)
        mock_db.append_dataframe_to_table.assert_not_called()


# ---------------------------------------------------------------------------
# check_yield
# ---------------------------------------------------------------------------


class TestCheckYield:
    def test_acceptable_yield(self):
        ingestion = {"articles_ingested": 20}
        extraction = {"predictions_extracted": 60}
        assert check_yield(ingestion, extraction) is True

    def test_low_yield_returns_false(self):
        ingestion = {"articles_ingested": 50}
        extraction = {"predictions_extracted": 10}  # 0.2/article < 1.0 threshold
        assert check_yield(ingestion, extraction) is False

    def test_too_few_articles_always_ok(self):
        """Under 10 articles, don't trigger yield warning."""
        ingestion = {"articles_ingested": 5}
        extraction = {"predictions_extracted": 0}
        assert check_yield(ingestion, extraction) is True

    def test_exactly_at_threshold(self):
        ingestion = {"articles_ingested": 10}
        extraction = {"predictions_extracted": 10}  # 1.0/article = exactly threshold
        assert check_yield(ingestion, extraction) is True


# ---------------------------------------------------------------------------
# run_historical_ingestion (integration-style with mocking)
# ---------------------------------------------------------------------------


class TestRunHistoricalIngestion:
    @patch("src.historical_archive_ingestor.fetch_and_ingest_article")
    @patch("src.historical_archive_ingestor.get_existing_hashes_all")
    def test_respects_batch_size(self, mock_hashes, mock_fetch):
        mock_hashes.return_value = set()
        mock_fetch.return_value = {"content_hash": "abc", "title": "test"}
        mock_db = MagicMock()

        result = run_historical_ingestion(
            seasons=[2022],
            batch_size=5,
            dry_run=False,
            db=mock_db,
        )
        assert result["articles_attempted"] == 5
        assert mock_fetch.call_count == 5

    @patch("src.historical_archive_ingestor.fetch_and_ingest_article")
    @patch("src.historical_archive_ingestor.get_existing_hashes_all")
    def test_counts_ingested_and_failed(self, mock_hashes, mock_fetch):
        mock_hashes.return_value = set()
        # Alternate success / failure
        mock_fetch.side_effect = [
            {"content_hash": "abc", "title": "ok"},
            None,
            {"content_hash": "def", "title": "ok2"},
            None,
        ]
        mock_db = MagicMock()

        result = run_historical_ingestion(
            seasons=[2022],
            batch_size=4,
            dry_run=False,
            db=mock_db,
        )
        assert result["articles_ingested"] == 2
        assert result["articles_failed"] == 2

    @patch("src.historical_archive_ingestor.fetch_and_ingest_article")
    @patch("src.historical_archive_ingestor.get_existing_hashes_all")
    def test_dry_run_skips_hash_loading(self, mock_hashes, mock_fetch):
        mock_fetch.return_value = None
        mock_db = MagicMock()

        run_historical_ingestion(
            seasons=[2022],
            batch_size=2,
            dry_run=True,
            db=mock_db,
        )
        # get_existing_hashes_all should NOT be called in dry_run mode
        mock_hashes.assert_not_called()

    @patch("src.historical_archive_ingestor.fetch_and_ingest_article")
    @patch("src.historical_archive_ingestor.get_existing_hashes_all")
    def test_article_type_filter(self, mock_hashes, mock_fetch):
        mock_hashes.return_value = set()
        mock_fetch.return_value = None
        mock_db = MagicMock()

        run_historical_ingestion(
            seasons=[2022],
            batch_size=100,
            dry_run=False,
            db=mock_db,
            article_types=["bold_predictions"],
        )
        # All calls should be for bold_predictions articles only
        for call in mock_fetch.call_args_list:
            article_arg = call[0][0]
            assert article_arg.article_type == "bold_predictions"


# ---------------------------------------------------------------------------
# assertion_extractor allow_historical integration
# ---------------------------------------------------------------------------


class TestAssertionExtractorAllowHistorical:
    """
    Verify the allow_historical flag correctly bypasses temporal filtering.
    These tests import assertion_extractor directly (no BQ/LLM).
    """

    def test_historical_predictions_pass_when_flag_set(self):
        from unittest.mock import MagicMock

        from src.assertion_extractor import extract_assertions

        mock_provider = MagicMock()
        mock_provider.extract_predictions.return_value = [
            {
                "extracted_claim": "Patrick Mahomes will win MVP in 2022",
                "claim_category": "player_performance",
                "season_year": 2022,
                "target_player": "Patrick Mahomes",
                "stance": "bullish",
                "target_team": "Kansas City Chiefs",
            }
        ]

        result = extract_assertions(
            content_hash="abc123",
            text="Patrick Mahomes will win MVP in 2022",
            provider=mock_provider,
            allow_historical=True,
        )
        # Should NOT filter out the 2022 prediction
        assert len(result.predictions) == 1
        assert result.predictions[0]["season_year"] == 2022

    def test_historical_predictions_filtered_without_flag(self):
        from unittest.mock import MagicMock

        from src.assertion_extractor import extract_assertions

        mock_provider = MagicMock()
        mock_provider.extract_predictions.return_value = [
            {
                "extracted_claim": "Patrick Mahomes will win MVP in 2022",
                "claim_category": "player_performance",
                "season_year": 2022,
                "target_player": "Patrick Mahomes",
                "stance": "bullish",
                "target_team": "Kansas City Chiefs",
            }
        ]

        result = extract_assertions(
            content_hash="abc123",
            text="Patrick Mahomes will win MVP in 2022",
            provider=mock_provider,
            allow_historical=False,  # default behavior
        )
        # Should filter out 2022 prediction (current year is 2026)
        assert len(result.predictions) == 0

    def test_future_predictions_always_pass(self):
        from unittest.mock import MagicMock

        from src.assertion_extractor import extract_assertions

        mock_provider = MagicMock()
        mock_provider.extract_predictions.return_value = [
            {
                "extracted_claim": "The Chiefs will win Super Bowl LXI",
                "claim_category": "game_outcome",
                "season_year": 2027,
                "target_player": None,
                "stance": "bullish",
                "target_team": "Kansas City Chiefs",
            }
        ]

        result = extract_assertions(
            content_hash="abc123",
            text="The Chiefs will win Super Bowl LXI",
            provider=mock_provider,
            allow_historical=False,
        )
        assert len(result.predictions) == 1
