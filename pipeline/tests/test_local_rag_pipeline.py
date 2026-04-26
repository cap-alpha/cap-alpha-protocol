"""
Tests for local_rag_pipeline.py (Issue #182)

Covers:
  - _row_to_article: row conversion to ArticleRecord
  - _build_pundit_predictions: LLM dict → PunditPrediction
  - run_batched_extraction: batching, temporal filter, dedup, dry-run
  - run_extraction_with_config: routes to batched vs per-article based on config
"""

from unittest.mock import MagicMock, call, patch

import pandas as pd
import pytest
from src.local_rag_pipeline import (
    _build_pundit_predictions,
    _row_to_article,
    run_batched_extraction,
    run_extraction_with_config,
)
from src.team_batcher import ArticleRecord

# ---------------------------------------------------------------------------
# _row_to_article
# ---------------------------------------------------------------------------


class TestRowToArticle:
    def _make_row(self, **kwargs):
        defaults = {
            "content_hash": "abc123",
            "raw_text": "Some article text",
            "title": "Test Article",
            "matched_pundit_name": "Adam Schefter",
            "author": "Adam Schefter",
            "source_id": "espn",
            "published_at": "2025-08-15",
        }
        defaults.update(kwargs)
        return pd.Series(defaults)

    def test_basic_conversion(self):
        row = self._make_row()
        art = _row_to_article(row)
        assert art.content_hash == "abc123"
        assert art.raw_text == "Some article text"
        assert art.title == "Test Article"
        assert art.pundit_name == "Adam Schefter"
        assert art.source_name == "espn"
        assert art.published_date == "2025-08-15"

    def test_falls_back_to_author_when_no_pundit_name(self):
        row = self._make_row(matched_pundit_name=None)
        art = _row_to_article(row)
        assert art.pundit_name == "Adam Schefter"

    def test_empty_pundit_when_neither_set(self):
        row = self._make_row(matched_pundit_name=None, author=None)
        art = _row_to_article(row)
        assert art.pundit_name == ""

    def test_published_at_none_gives_empty_string(self):
        row = self._make_row(published_at=None)
        art = _row_to_article(row)
        assert art.published_date == ""

    def test_invalid_published_at_gives_empty_string(self):
        row = self._make_row(published_at="not-a-date-at-all!!!")
        art = _row_to_article(row)
        # Should not raise; gives empty string on parse failure
        assert art.published_date == ""

    def test_returns_article_record_type(self):
        row = self._make_row()
        art = _row_to_article(row)
        assert isinstance(art, ArticleRecord)


# ---------------------------------------------------------------------------
# _build_pundit_predictions
# ---------------------------------------------------------------------------


class TestBuildPunditPredictions:
    def _make_article(self, pundit_name="Ian Rapoport"):
        return ArticleRecord(
            content_hash="hash1",
            raw_text="A" * 3000,  # longer than 2000 chars
            title="Test",
            pundit_name=pundit_name,
            source_name="nfl_network",
            published_date="2025-09-01",
        )

    def test_basic_prediction(self):
        art = self._make_article()
        preds = _build_pundit_predictions(
            [
                {
                    "extracted_claim": "Patrick Mahomes will win MVP",
                    "claim_category": "player_performance",
                    "season_year": 2025,
                    "target_player": "Patrick Mahomes",
                    "target_team": "KC",
                }
            ],
            art,
            pundit_id="rapoport-1",
            source_url="https://example.com",
        )
        assert len(preds) == 1
        p = preds[0]
        assert p.extracted_claim == "Patrick Mahomes will win MVP"
        assert p.claim_category == "player_performance"
        assert p.season_year == 2025
        assert p.target_player_name == "Patrick Mahomes"
        assert p.target_team == "KC"
        assert p.pundit_id == "rapoport-1"
        assert p.source_url == "https://example.com"

    def test_raw_assertion_text_truncated_to_2000_chars(self):
        art = self._make_article()
        assert len(art.raw_text) > 2000
        preds = _build_pundit_predictions(
            [{"extracted_claim": "Test claim", "claim_category": "draft_pick"}],
            art,
            pundit_id="p1",
            source_url="",
        )
        assert len(preds[0].raw_assertion_text) == 2000

    def test_skips_empty_claim(self):
        art = self._make_article()
        preds = _build_pundit_predictions(
            [{"extracted_claim": "  ", "claim_category": "trade"}],
            art,
            pundit_id="p1",
            source_url="",
        )
        assert preds == []

    def test_multi_player_becomes_MULTI(self):
        art = self._make_article()
        preds = _build_pundit_predictions(
            [
                {
                    "extracted_claim": "Trade incoming",
                    "claim_category": "trade",
                    "target_player": "Player A, Player B",
                }
            ],
            art,
            pundit_id="p1",
            source_url="",
        )
        assert preds[0].target_player_name == "MULTI"

    def test_single_player_preserved(self):
        art = self._make_article()
        preds = _build_pundit_predictions(
            [
                {
                    "extracted_claim": "Player X wins award",
                    "claim_category": "player_performance",
                    "target_player": "Player X",
                }
            ],
            art,
            pundit_id="p1",
            source_url="",
        )
        assert preds[0].target_player_name == "Player X"

    def test_no_target_player_is_none(self):
        art = self._make_article()
        preds = _build_pundit_predictions(
            [
                {
                    "extracted_claim": "Chiefs win Super Bowl",
                    "claim_category": "game_outcome",
                }
            ],
            art,
            pundit_id="p1",
            source_url="",
        )
        assert preds[0].target_player_name is None

    def test_sport_is_NFL(self):
        art = self._make_article()
        preds = _build_pundit_predictions(
            [{"extracted_claim": "Some claim", "claim_category": "injury"}],
            art,
            pundit_id="p1",
            source_url="",
        )
        assert preds[0].sport == "NFL"

    def test_returns_multiple(self):
        art = self._make_article()
        raw = [
            {"extracted_claim": "Claim 1", "claim_category": "draft_pick"},
            {"extracted_claim": "Claim 2", "claim_category": "trade"},
        ]
        preds = _build_pundit_predictions(raw, art, pundit_id="p1", source_url="")
        assert len(preds) == 2


# ---------------------------------------------------------------------------
# run_batched_extraction — dry-run (no LLM calls, no DB writes)
# ---------------------------------------------------------------------------


def _make_media_df(n=3):
    """Build a minimal DataFrame mimicking get_unprocessed_media output."""
    rows = []
    for i in range(n):
        rows.append(
            {
                "content_hash": f"hash{i}",
                "raw_text": f"The Kansas City Chiefs will win the Super Bowl this season. Article {i}.",
                "title": f"Article {i}",
                "matched_pundit_name": f"Pundit {i}",
                "author": f"Author {i}",
                "source_id": "espn",
                "source_url": f"https://example.com/{i}",
                "matched_pundit_id": f"pid{i}",
                "published_at": "2025-08-01",
            }
        )
    return pd.DataFrame(rows)


class TestRunBatchedExtractionDryRun:
    def test_dry_run_returns_summary_without_db_writes(self):
        mock_db = MagicMock()
        with (
            patch(
                "src.local_rag_pipeline.get_unprocessed_media",
                return_value=_make_media_df(3),
            ),
            patch("src.local_rag_pipeline.mark_as_processed") as mock_mark,
            patch(
                "src.local_rag_pipeline.load_llm_config",
                return_value={"batching": {"max_articles_per_batch": 5}},
            ),
        ):
            summary = run_batched_extraction(limit=3, dry_run=True, db=mock_db)

        assert summary["total_articles"] == 3
        assert summary["mode"] == "batched"
        mock_mark.assert_not_called()

    def test_dry_run_no_provider_needed(self):
        """dry_run=True should not require a provider."""
        mock_db = MagicMock()
        with (
            patch(
                "src.local_rag_pipeline.get_unprocessed_media",
                return_value=_make_media_df(2),
            ),
            patch("src.local_rag_pipeline.load_llm_config", return_value={}),
            patch("src.local_rag_pipeline.get_provider_with_fallback") as mock_get_prov,
        ):
            run_batched_extraction(limit=2, dry_run=True, db=mock_db)

        mock_get_prov.assert_not_called()

    def test_empty_media_returns_early(self):
        mock_db = MagicMock()
        with (
            patch(
                "src.local_rag_pipeline.get_unprocessed_media",
                return_value=pd.DataFrame(),
            ),
            patch("src.local_rag_pipeline.load_llm_config", return_value={}),
        ):
            summary = run_batched_extraction(limit=10, dry_run=True, db=mock_db)

        assert summary["total_articles"] == 0
        assert summary["predictions_extracted"] == 0


# ---------------------------------------------------------------------------
# run_batched_extraction — live mock (provider injected)
# ---------------------------------------------------------------------------


class TestRunBatchedExtractionWithProvider:
    def _make_mock_provider(self, return_value=None):
        provider = MagicMock()
        provider.model = "test-model"
        provider.extract_predictions.return_value = return_value or []
        return provider

    def test_predictions_extracted_and_ingested(self):
        mock_db = MagicMock()
        provider = self._make_mock_provider(
            [
                {
                    "extracted_claim": "KC will win AFC",
                    "claim_category": "game_outcome",
                    "season_year": 2026,
                    "target_team": "KC",
                    "pundit_name": "Pundit 0",
                },
            ]
        )
        with (
            patch(
                "src.local_rag_pipeline.get_unprocessed_media",
                return_value=_make_media_df(1),
            ),
            patch(
                "src.local_rag_pipeline.load_llm_config",
                return_value={"batching": {"max_articles_per_batch": 5}},
            ),
            patch("src.local_rag_pipeline.mark_as_processed") as mock_mark,
            patch(
                "src.local_rag_pipeline.ingest_batch", return_value=["hash-a"]
            ) as mock_ingest,
        ):
            summary = run_batched_extraction(
                limit=1, dry_run=False, db=mock_db, provider=provider
            )

        assert summary["predictions_extracted"] >= 1
        assert summary["predictions_ingested"] == 1
        mock_mark.assert_called_once()

    def test_temporal_filter_rejects_past_season(self):
        """Predictions with season_year < current year should be filtered out."""
        mock_db = MagicMock()
        provider = self._make_mock_provider(
            [
                # past year — should be filtered
                {
                    "extracted_claim": "KC won AFC 2020",
                    "claim_category": "game_outcome",
                    "season_year": 2020,
                    "target_team": "KC",
                },
            ]
        )
        with (
            patch(
                "src.local_rag_pipeline.get_unprocessed_media",
                return_value=_make_media_df(1),
            ),
            patch("src.local_rag_pipeline.load_llm_config", return_value={}),
            patch("src.local_rag_pipeline.mark_as_processed"),
            patch("src.local_rag_pipeline.ingest_batch", return_value=[]),
        ):
            summary = run_batched_extraction(
                limit=1, dry_run=False, db=mock_db, provider=provider
            )

        assert summary["predictions_extracted"] == 0

    def test_extraction_error_increments_error_count(self):
        mock_db = MagicMock()
        provider = self._make_mock_provider()
        provider.extract_predictions.side_effect = RuntimeError("LLM offline")

        with (
            patch(
                "src.local_rag_pipeline.get_unprocessed_media",
                return_value=_make_media_df(1),
            ),
            patch("src.local_rag_pipeline.load_llm_config", return_value={}),
            patch("src.local_rag_pipeline.mark_as_processed"),
        ):
            summary = run_batched_extraction(
                limit=1, dry_run=False, db=mock_db, provider=provider
            )

        assert summary["errors"] >= 1

    def test_no_predictions_increments_skipped(self):
        mock_db = MagicMock()
        provider = self._make_mock_provider([])  # empty predictions

        with (
            patch(
                "src.local_rag_pipeline.get_unprocessed_media",
                return_value=_make_media_df(1),
            ),
            patch("src.local_rag_pipeline.load_llm_config", return_value={}),
            patch("src.local_rag_pipeline.mark_as_processed"),
        ):
            summary = run_batched_extraction(
                limit=1, dry_run=False, db=mock_db, provider=provider
            )

        assert summary["skipped_no_predictions"] >= 1
        assert summary["predictions_extracted"] == 0

    def test_provider_model_name_in_summary(self):
        mock_db = MagicMock()
        provider = self._make_mock_provider()

        with (
            patch(
                "src.local_rag_pipeline.get_unprocessed_media",
                return_value=pd.DataFrame(),
            ),
            patch("src.local_rag_pipeline.load_llm_config", return_value={}),
        ):
            summary = run_batched_extraction(
                limit=0, dry_run=False, db=mock_db, provider=provider
            )

        assert summary["provider"] == "test-model"


# ---------------------------------------------------------------------------
# run_extraction_with_config — routing
# ---------------------------------------------------------------------------


class TestRunExtractionWithConfig:
    def test_routes_to_batched_when_enabled(self):
        with (
            patch(
                "src.local_rag_pipeline.load_llm_config",
                return_value={"batching": {"enabled": True}},
            ),
            patch("src.local_rag_pipeline.run_batched_extraction") as mock_batched,
        ):
            mock_batched.return_value = {"mode": "batched"}
            result = run_extraction_with_config(limit=10, dry_run=True)

        mock_batched.assert_called_once()
        assert result["mode"] == "batched"

    def test_routes_to_per_article_when_disabled(self):
        with (
            patch(
                "src.local_rag_pipeline.load_llm_config",
                return_value={"batching": {"enabled": False}},
            ),
            patch("src.assertion_extractor.run_extraction") as mock_per_art,
        ):
            mock_per_art.return_value = {"mode": "per-article"}
            result = run_extraction_with_config(limit=10, dry_run=True)

        mock_per_art.assert_called_once()

    def test_routes_to_per_article_when_no_batching_key(self):
        with (
            patch("src.local_rag_pipeline.load_llm_config", return_value={}),
            patch("src.assertion_extractor.run_extraction") as mock_per_art,
        ):
            mock_per_art.return_value = {}
            run_extraction_with_config(limit=5)

        mock_per_art.assert_called_once()

    def test_passes_kwargs_to_batched(self):
        with (
            patch(
                "src.local_rag_pipeline.load_llm_config",
                return_value={"batching": {"enabled": True}},
            ),
            patch("src.local_rag_pipeline.run_batched_extraction") as mock_batched,
        ):
            mock_batched.return_value = {}
            run_extraction_with_config(limit=99, dry_run=True, sport="NFL")

        call_kwargs = mock_batched.call_args
        assert call_kwargs.kwargs.get("limit") == 99 or call_kwargs.args[0] == 99
