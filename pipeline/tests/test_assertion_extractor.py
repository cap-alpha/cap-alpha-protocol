"""
Tests for the NLP Assertion Extraction Pipeline (Issue #79, #178).
Unit tests — no LLM API or BigQuery required.
"""

import json
import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from google.api_core.exceptions import NotFound

from src.assertion_extractor import (
    VALID_CATEGORIES,
    ExtractionResult,
    _deduplicate_claims,
    extract_assertions,
    get_unprocessed_media,
    mark_as_processed,
    reset_processed_hashes,
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
    """Mock LLM provider that returns predictions via extract_predictions."""
    provider = MagicMock()
    provider.model = "mock-model"
    provider.extract_predictions.return_value = []
    return provider


def set_provider_predictions(mock_provider, predictions: list):
    """Configure mock provider to return specific predictions."""
    mock_provider.extract_predictions.return_value = predictions


def make_raw_media_df(n=1):
    rows = []
    for i in range(n):
        rows.append(
            {
                "content_hash": f"hash_{i}",
                "source_id": "espn_nfl",
                "title": f"Article {i}",
                "raw_text": "I think Patrick Mahomes will definitely win MVP this season. "
                "He's been the best QB by far and nobody is close.",
                "source_url": f"https://espn.com/article/{i}",
                "author": "Adam Schefter",
                "matched_pundit_id": "adam_schefter",
                "matched_pundit_name": "Adam Schefter",
                "published_at": datetime(2025, 9, 1, tzinfo=timezone.utc),
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# extract_assertions
# ---------------------------------------------------------------------------


class TestExtractAssertions:
    def test_returns_parsed_predictions(self, mock_provider):
        predictions = [
            {
                "extracted_claim": "Patrick Mahomes will win MVP in 2025",
                "claim_category": "player_performance",
                "season_year": 2025,
                "target_player": "Patrick Mahomes",
                "target_team": "KC",
                "confidence_note": "strong assertion",
            }
        ]
        set_provider_predictions(mock_provider, predictions)

        result = extract_assertions(
            content_hash="abc123",
            text="Mahomes will win MVP this year",
            provider=mock_provider,
        )

        assert len(result.predictions) == 1
        assert (
            result.predictions[0]["extracted_claim"]
            == "Patrick Mahomes will win MVP in 2025"
        )
        assert result.predictions[0]["claim_category"] == "player_performance"
        assert result.error is None

    def test_handles_empty_array_response(self, mock_provider):
        set_provider_predictions(mock_provider, [])

        result = extract_assertions(
            content_hash="abc123",
            text="Just a recap of last week's games",
            provider=mock_provider,
        )

        assert len(result.predictions) == 0
        assert result.error is None

    def test_handles_valid_predictions(self, mock_provider):
        """Provider returns clean predictions directly."""
        predictions = [
            {
                "extracted_claim": "Josh Allen wins Super Bowl",
                "claim_category": "game_outcome",
                "confidence_note": "strong",
            }
        ]
        set_provider_predictions(mock_provider, predictions)

        result = extract_assertions(
            content_hash="abc123",
            text="Allen is going all the way",
            provider=mock_provider,
        )

        assert len(result.predictions) == 1
        assert result.predictions[0]["extracted_claim"] == "Josh Allen wins Super Bowl"

    def test_handles_provider_error(self, mock_provider):
        mock_provider.extract_predictions.side_effect = Exception(
            "API quota exceeded"
        )

        result = extract_assertions(
            content_hash="abc123",
            text="Some text",
            provider=mock_provider,
        )

        assert len(result.predictions) == 0
        assert "API quota exceeded" in result.error

    def test_valid_categories_are_complete(self):
        """All expected categories are defined."""
        expected = {
            "player_performance", "game_outcome", "trade",
            "draft_pick", "injury", "contract",
        }
        assert VALID_CATEGORIES == expected

    def test_skips_predictions_without_claim(self, mock_provider):
        predictions = [
            {"extracted_claim": "", "claim_category": "trade"},
            {
                "extracted_claim": "Valid claim here",
                "claim_category": "trade",
            },
        ]
        set_provider_predictions(mock_provider, predictions)

        result = extract_assertions(
            content_hash="abc123",
            text="Some text",
            provider=mock_provider,
        )

        assert len(result.predictions) == 1

    def test_truncates_long_text(self, mock_provider):
        set_provider_predictions(mock_provider, [])

        long_text = "x" * 10000
        extract_assertions(
            content_hash="abc123",
            text=long_text,
            provider=mock_provider,
        )

        call_args = mock_provider.extract_predictions.call_args
        prompt_text = call_args[0][0]  # first positional arg
        # Text should be truncated to 4000 chars
        assert len(prompt_text) < len(long_text) + 1000

    def test_deduplicates_near_identical_claims(self):
        """Semantic dedup removes near-duplicate claims."""
        predictions = [
            {"extracted_claim": "Mahomes will win MVP in 2025", "claim_category": "player_performance"},
            {"extracted_claim": "Patrick Mahomes will win the MVP in 2025", "claim_category": "player_performance"},
            {"extracted_claim": "Bears make the playoffs in 2025", "claim_category": "game_outcome"},
        ]
        result = _deduplicate_claims(predictions)
        assert len(result) == 2  # two Mahomes claims collapse to one

    def test_dedup_keeps_longer_claim(self):
        """When deduping, the longer (more specific) claim survives."""
        predictions = [
            {"extracted_claim": "Mahomes will win mvp in the 2025 season", "claim_category": "player_performance"},
            {"extracted_claim": "Patrick Mahomes will win mvp in the 2025 season", "claim_category": "player_performance"},
        ]
        result = _deduplicate_claims(predictions)
        assert len(result) == 1
        assert "Patrick Mahomes" in result[0]["extracted_claim"]


# ---------------------------------------------------------------------------
# get_unprocessed_media
# ---------------------------------------------------------------------------


class TestGetUnprocessedMedia:
    def test_returns_dataframe(self, mock_db):
        mock_db.fetch_df.return_value = make_raw_media_df(3)
        df = get_unprocessed_media(mock_db, limit=10)
        assert len(df) == 3

    def test_queries_with_left_join(self, mock_db):
        mock_db.fetch_df.return_value = pd.DataFrame()
        get_unprocessed_media(mock_db)
        query = mock_db.fetch_df.call_args[0][0]
        assert "LEFT JOIN" in query
        assert "processed_media_hashes" in query

    def test_filters_unmatched_pundits_by_default(self, mock_db):
        """Default query should require matched_pundit_id IS NOT NULL."""
        mock_db.fetch_df.return_value = pd.DataFrame()
        get_unprocessed_media(mock_db)
        query = mock_db.fetch_df.call_args[0][0]
        assert "matched_pundit_id IS NOT NULL" in query

    def test_include_unmatched_skips_pundit_filter(self, mock_db):
        """With include_unmatched=True, query should NOT filter on pundit."""
        mock_db.fetch_df.return_value = pd.DataFrame()
        get_unprocessed_media(mock_db, include_unmatched=True)
        query = mock_db.fetch_df.call_args[0][0]
        assert "matched_pundit_id IS NOT NULL" not in query

    def test_falls_back_on_missing_tracking_table(self, mock_db):
        mock_db.fetch_df.side_effect = [
            NotFound("processed_media_hashes"),
            make_raw_media_df(2),
        ]
        df = get_unprocessed_media(mock_db)
        assert len(df) == 2
        assert mock_db.fetch_df.call_count == 2

    def test_default_filters_to_matched_pundit(self, mock_db):
        """Default query requires matched_pundit_id IS NOT NULL."""
        mock_db.fetch_df.return_value = pd.DataFrame()
        get_unprocessed_media(mock_db)
        query = mock_db.fetch_df.call_args[0][0]
        assert "matched_pundit_id IS NOT NULL" in query

    def test_include_unmatched_skips_pundit_filter(self, mock_db):
        """When include_unmatched=True, the matched_pundit_id filter is absent."""
        mock_db.fetch_df.return_value = pd.DataFrame()
        get_unprocessed_media(mock_db, include_unmatched=True)
        query = mock_db.fetch_df.call_args[0][0]
        assert "matched_pundit_id IS NOT NULL" not in query

    def test_fallback_query_also_filters_matched_pundit(self, mock_db):
        """Fallback query (no tracking table) also requires matched_pundit_id."""
        mock_db.fetch_df.side_effect = [
            NotFound("processed_media_hashes"),
            pd.DataFrame(),
        ]
        get_unprocessed_media(mock_db)
        fallback_query = mock_db.fetch_df.call_args_list[1][0][0]
        assert "matched_pundit_id IS NOT NULL" in fallback_query

    def test_fallback_query_include_unmatched(self, mock_db):
        """Fallback query skips pundit filter when include_unmatched=True."""
        mock_db.fetch_df.side_effect = [
            NotFound("processed_media_hashes"),
            pd.DataFrame(),
        ]
        get_unprocessed_media(mock_db, include_unmatched=True)
        fallback_query = mock_db.fetch_df.call_args_list[1][0][0]
        assert "matched_pundit_id IS NOT NULL" not in fallback_query


# ---------------------------------------------------------------------------
# mark_as_processed
# ---------------------------------------------------------------------------


class TestMarkAsProcessed:
    def test_writes_hashes(self, mock_db):
        mark_as_processed(["hash_1", "hash_2"], mock_db)
        mock_db.append_dataframe_to_table.assert_called_once()
        call_args = mock_db.append_dataframe_to_table.call_args
        df = call_args[0][0]
        assert len(df) == 2
        assert "content_hash" in df.columns
        assert "processed_at" in df.columns

    def test_no_op_on_empty_list(self, mock_db):
        mark_as_processed([], mock_db)
        mock_db.append_dataframe_to_table.assert_not_called()


# ---------------------------------------------------------------------------
# reset_processed_hashes
# ---------------------------------------------------------------------------


class TestResetProcessedHashes:
    def test_full_reset_executes_delete_all(self, mock_db):
        mock_result = MagicMock()
        mock_result.job.num_dml_affected_rows = 5
        mock_db.execute.return_value = mock_result

        deleted = reset_processed_hashes(mock_db)

        assert deleted == 5
        query = mock_db.execute.call_args[0][0]
        assert "DELETE FROM" in query
        assert "WHERE TRUE" in query

    def test_source_reset_filters_by_source_id(self, mock_db):
        mock_result = MagicMock()
        mock_result.job.num_dml_affected_rows = 3
        mock_db.execute.return_value = mock_result

        deleted = reset_processed_hashes(mock_db, source_id="espn_nfl")

        assert deleted == 3
        query = mock_db.execute.call_args[0][0]
        assert "source_id = 'espn_nfl'" in query

    def test_handles_zero_rows(self, mock_db):
        mock_result = MagicMock()
        mock_result.job.num_dml_affected_rows = None
        mock_db.execute.return_value = mock_result

        assert reset_processed_hashes(mock_db) == 0


# ---------------------------------------------------------------------------
# run_extraction (integration of all components)
# ---------------------------------------------------------------------------


class TestRunExtraction:
    @patch("src.assertion_extractor.ingest_batch")
    @patch("src.assertion_extractor.extract_assertions")
    def test_full_pipeline(self, mock_extract, mock_ingest, mock_db, mock_provider):
        mock_db.fetch_df.return_value = make_raw_media_df(1)
        mock_extract.return_value = ExtractionResult(
            content_hash="hash_0",
            predictions=[
                {
                    "extracted_claim": "Mahomes wins MVP",
                    "claim_category": "player_performance",
                    "season_year": 2025,
                    "target_player": "Patrick Mahomes",
                    "target_team": "KC",
                    "confidence_note": "strong",
                }
            ],
        )
        mock_ingest.return_value = ["pred_hash_1"]

        summary = run_extraction(limit=10, db=mock_db, provider=mock_provider)

        assert summary["total_processed"] == 1
        assert summary["predictions_extracted"] == 1
        assert summary["predictions_ingested"] == 1
        assert summary["errors"] == 0

    @patch("src.assertion_extractor.extract_assertions")
    def test_handles_extraction_errors(self, mock_extract, mock_db, mock_provider):
        mock_db.fetch_df.return_value = make_raw_media_df(1)
        mock_extract.return_value = ExtractionResult(
            content_hash="hash_0",
            predictions=[],
            error="LLM quota exceeded",
        )

        summary = run_extraction(limit=10, db=mock_db, provider=mock_provider)

        assert summary["errors"] == 1
        assert summary["predictions_extracted"] == 0

    @patch("src.assertion_extractor.extract_assertions")
    def test_counts_no_predictions(self, mock_extract, mock_db, mock_provider):
        mock_db.fetch_df.return_value = make_raw_media_df(1)
        mock_extract.return_value = ExtractionResult(
            content_hash="hash_0",
            predictions=[],
        )

        summary = run_extraction(limit=10, db=mock_db, provider=mock_provider)

        assert summary["skipped_no_predictions"] == 1

    def test_dry_run_skips_llm(self, mock_db):
        mock_db.fetch_df.return_value = make_raw_media_df(2)

        summary = run_extraction(limit=10, dry_run=True, db=mock_db)

        assert summary["total_processed"] == 2
        assert summary["predictions_extracted"] == 0
        mock_db.append_dataframe_to_table.assert_not_called()

    def test_no_work_when_empty(self, mock_db, mock_provider):
        mock_db.fetch_df.return_value = pd.DataFrame()

        summary = run_extraction(limit=10, db=mock_db, provider=mock_provider)

        assert summary["total_processed"] == 0

    @patch("src.assertion_extractor.get_unprocessed_media")
    def test_passes_include_unmatched_flag(self, mock_get, mock_db, mock_provider):
        """include_unmatched flag should be forwarded to get_unprocessed_media."""
        mock_get.return_value = pd.DataFrame()

        run_extraction(
            limit=5, db=mock_db, provider=mock_provider, include_unmatched=True
        )

        mock_get.assert_called_once_with(mock_db, limit=5, include_unmatched=True)

    @patch("src.assertion_extractor.get_unprocessed_media")
    def test_default_excludes_unmatched(self, mock_get, mock_db, mock_provider):
        """By default, include_unmatched should be False."""
        mock_get.return_value = pd.DataFrame()

        run_extraction(limit=5, db=mock_db, provider=mock_provider)

        mock_get.assert_called_once_with(mock_db, limit=5, include_unmatched=False)


# ---------------------------------------------------------------------------
# LLM Provider
# ---------------------------------------------------------------------------


class TestLLMProvider:
    def test_provider_factory_returns_gemini_by_default(self):
        from src.llm_provider import load_llm_config
        config = load_llm_config()
        assert config["extraction"]["provider"] == "gemini"

    def test_provider_factory_lists_all_providers(self):
        from src.llm_provider import PROVIDERS
        assert set(PROVIDERS.keys()) == {"gemini", "claude", "openai", "ollama"}

    def test_json_parse_strips_markdown_fences(self):
        from src.llm_provider import LLMProvider

        class DummyProvider(LLMProvider):
            def extract_predictions(self, prompt): pass
            def classify(self, prompt): pass

        provider = DummyProvider(model="test")
        text = '```json\n[{"extracted_claim": "test", "claim_category": "trade"}]\n```'
        result = provider._parse_json_response(text)
        assert len(result) == 1
        assert result[0]["extracted_claim"] == "test"

    def test_json_parse_handles_invalid(self):
        from src.llm_provider import LLMProvider

        class DummyProvider(LLMProvider):
            def extract_predictions(self, prompt): pass
            def classify(self, prompt): pass

        provider = DummyProvider(model="test")
        result = provider._parse_json_response("not json at all")
        assert result == []


# ---------------------------------------------------------------------------
# Constants validation (legacy — kept for backward compat)
# ---------------------------------------------------------------------------


class TestConstants:
    def test_valid_categories_are_complete(self):
        expected = {
            "player_performance",
            "game_outcome",
            "trade",
            "draft_pick",
            "injury",
            "contract",
        }
        assert VALID_CATEGORIES == expected
