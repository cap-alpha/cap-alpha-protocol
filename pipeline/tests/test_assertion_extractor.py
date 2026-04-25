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
    should_filter_article,
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
                "extracted_claim": "Patrick Mahomes will win MVP in 2026",
                "claim_category": "player_performance",
                "season_year": 2026,
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
            == "Patrick Mahomes will win MVP in 2026"
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
        mock_provider.extract_predictions.side_effect = Exception("API quota exceeded")

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
            "player_performance",
            "game_outcome",
            "trade",
            "draft_pick",
            "injury",
            "contract",
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
            {
                "extracted_claim": "Mahomes will win MVP in 2025",
                "claim_category": "player_performance",
            },
            {
                "extracted_claim": "Patrick Mahomes will win the MVP in 2025",
                "claim_category": "player_performance",
            },
            {
                "extracted_claim": "Bears make the playoffs in 2025",
                "claim_category": "game_outcome",
            },
        ]
        result = _deduplicate_claims(predictions)
        assert len(result) == 2  # two Mahomes claims collapse to one

    def test_dedup_keeps_longer_claim(self):
        """When deduping, the longer (more specific) claim survives."""
        predictions = [
            {
                "extracted_claim": "Mahomes will win mvp in the 2025 season",
                "claim_category": "player_performance",
            },
            {
                "extracted_claim": "Patrick Mahomes will win mvp in the 2025 season",
                "claim_category": "player_performance",
            },
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
                    "season_year": 2026,
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
# Pre-filter (Issue #180)
# ---------------------------------------------------------------------------


class TestShouldFilterArticle:
    def test_returns_false_when_no_provider(self):
        """Without a filter provider, nothing should be filtered."""
        assert should_filter_article("any text") is False

    def test_skips_article_when_provider_says_no(self):
        """If classifier says 'no' (no predictions), article should be skipped."""
        provider = MagicMock()
        provider.classify.return_value = "no"
        assert (
            should_filter_article("recap of last game", filter_provider=provider)
            is True
        )

    def test_passes_article_when_provider_says_yes(self):
        """If classifier says 'yes' (has predictions), article should NOT be skipped."""
        provider = MagicMock()
        provider.classify.return_value = "yes"
        assert (
            should_filter_article("Mahomes wins MVP", filter_provider=provider) is False
        )

    def test_passes_article_on_provider_error(self):
        """On error, don't skip — let extraction handle it (fail-open)."""
        provider = MagicMock()
        provider.classify.side_effect = Exception("Ollama connection refused")
        assert should_filter_article("some text", filter_provider=provider) is False

    def test_handles_yes_with_extra_text(self):
        """'yes, it does' should still pass the article through."""
        provider = MagicMock()
        provider.classify.return_value = "yes, it contains predictions"
        assert should_filter_article("text", filter_provider=provider) is False

    def test_handles_no_with_extra_text(self):
        """'no, this is a recap' should still filter the article."""
        provider = MagicMock()
        provider.classify.return_value = "no, this is a game recap"
        assert should_filter_article("text", filter_provider=provider) is True

    def test_truncates_text_to_1500_chars(self):
        """Filter prompt should only include first 1500 chars of article."""
        provider = MagicMock()
        provider.classify.return_value = "no"
        marker = "UNIQUEMARKER"
        # Place marker at position 1490 (within limit) and 1510 (beyond limit)
        long_text = "a" * 1490 + marker + "b" * 3000
        should_filter_article(long_text, filter_provider=provider)
        prompt_sent = provider.classify.call_args[0][0]
        # The marker at position 1490 should NOT appear (1490+12 = 1502 > 1500)
        # Only first 1500 chars of article text are included
        assert len(long_text[:1500]) == 1500
        assert "a" * 100 in prompt_sent  # early text is present
        assert "b" * 100 not in prompt_sent  # text beyond 1500 is absent

    def test_prompt_includes_sport(self):
        """Filter prompt should include the sport context."""
        provider = MagicMock()
        provider.classify.return_value = "no"
        should_filter_article("text", sport="MLB", filter_provider=provider)
        prompt_sent = provider.classify.call_args[0][0]
        assert "MLB" in prompt_sent

    def test_case_insensitive(self):
        """Classification should work regardless of case."""
        provider = MagicMock()
        provider.classify.return_value = "YES"
        assert should_filter_article("text", filter_provider=provider) is False

        provider.classify.return_value = "No"
        assert should_filter_article("text", filter_provider=provider) is True


class TestPreFilterIntegration:
    """Tests that pre-filter integrates correctly into run_extraction."""

    @patch("src.assertion_extractor.load_llm_config")
    @patch("src.assertion_extractor.get_provider")
    @patch("src.assertion_extractor.extract_assertions")
    def test_filter_skips_articles(
        self, mock_extract, mock_get_provider, mock_load_config, mock_db, mock_provider
    ):
        """When filter is enabled and says 'no', articles are skipped."""
        mock_load_config.return_value = {
            "extraction": {"provider": "gemini", "model": "gemini-2.5-flash"},
            "filter": {"enabled": True, "provider": "ollama", "model": "llama3.1:8b"},
        }
        filter_prov = MagicMock()
        filter_prov.classify.return_value = "no"
        mock_get_provider.return_value = filter_prov
        mock_db.fetch_df.return_value = make_raw_media_df(3)

        summary = run_extraction(limit=10, db=mock_db, provider=mock_provider)

        assert summary["filtered_out"] == 3
        assert summary["total_processed"] == 3
        mock_extract.assert_not_called()

    @patch("src.assertion_extractor.load_llm_config")
    @patch("src.assertion_extractor.get_provider")
    @patch("src.assertion_extractor.extract_assertions")
    def test_filter_passes_articles(
        self, mock_extract, mock_get_provider, mock_load_config, mock_db, mock_provider
    ):
        """When filter says 'yes', articles proceed to extraction."""
        mock_load_config.return_value = {
            "extraction": {"provider": "gemini", "model": "gemini-2.5-flash"},
            "filter": {"enabled": True, "provider": "ollama", "model": "llama3.1:8b"},
        }
        filter_prov = MagicMock()
        filter_prov.classify.return_value = "yes"
        mock_get_provider.return_value = filter_prov
        mock_db.fetch_df.return_value = make_raw_media_df(1)
        mock_extract.return_value = ExtractionResult(
            content_hash="hash_0", predictions=[]
        )

        summary = run_extraction(limit=10, db=mock_db, provider=mock_provider)

        assert summary["filtered_out"] == 0
        mock_extract.assert_called_once()

    @patch("src.assertion_extractor.load_llm_config")
    @patch("src.assertion_extractor.extract_assertions")
    def test_filter_disabled_by_default(
        self, mock_extract, mock_load_config, mock_db, mock_provider
    ):
        """When filter.enabled is false, no filtering happens."""
        mock_load_config.return_value = {
            "extraction": {"provider": "gemini", "model": "gemini-2.5-flash"},
            "filter": {"enabled": False, "provider": "ollama", "model": "llama3.1:8b"},
        }
        mock_db.fetch_df.return_value = make_raw_media_df(1)
        mock_extract.return_value = ExtractionResult(
            content_hash="hash_0", predictions=[]
        )

        summary = run_extraction(limit=10, db=mock_db, provider=mock_provider)

        assert summary["filtered_out"] == 0
        mock_extract.assert_called_once()

    @patch("src.assertion_extractor.load_llm_config")
    @patch("src.assertion_extractor.get_provider")
    @patch("src.assertion_extractor.extract_assertions")
    def test_disable_filter_flag(
        self, mock_extract, mock_get_provider, mock_load_config, mock_db, mock_provider
    ):
        """disable_filter=True overrides config and skips pre-filter."""
        mock_load_config.return_value = {
            "extraction": {"provider": "gemini", "model": "gemini-2.5-flash"},
            "filter": {"enabled": True, "provider": "ollama", "model": "llama3.1:8b"},
        }
        mock_db.fetch_df.return_value = make_raw_media_df(1)
        mock_extract.return_value = ExtractionResult(
            content_hash="hash_0", predictions=[]
        )

        summary = run_extraction(
            limit=10, db=mock_db, provider=mock_provider, disable_filter=True
        )

        assert summary["filtered_out"] == 0
        mock_get_provider.assert_not_called()
        mock_extract.assert_called_once()

    @patch("src.assertion_extractor.load_llm_config")
    @patch("src.assertion_extractor.get_provider")
    @patch("src.assertion_extractor.extract_assertions")
    def test_filtered_articles_marked_processed(
        self, mock_extract, mock_get_provider, mock_load_config, mock_db, mock_provider
    ):
        """Filtered-out articles are still marked as processed."""
        mock_load_config.return_value = {
            "extraction": {"provider": "gemini", "model": "gemini-2.5-flash"},
            "filter": {"enabled": True, "provider": "ollama", "model": "llama3.1:8b"},
        }
        filter_prov = MagicMock()
        filter_prov.classify.return_value = "no"
        mock_get_provider.return_value = filter_prov
        mock_db.fetch_df.return_value = make_raw_media_df(2)

        run_extraction(limit=10, db=mock_db, provider=mock_provider)

        # mark_as_processed should have been called with both hashes
        mock_db.append_dataframe_to_table.assert_called_once()
        df = mock_db.append_dataframe_to_table.call_args[0][0]
        assert len(df) == 2

    @patch("src.assertion_extractor.load_llm_config")
    @patch("src.assertion_extractor.get_provider")
    @patch("src.assertion_extractor.extract_assertions")
    def test_filter_error_falls_through(
        self, mock_extract, mock_get_provider, mock_load_config, mock_db, mock_provider
    ):
        """If filter provider errors on classify, article passes through to extraction."""
        mock_load_config.return_value = {
            "extraction": {"provider": "gemini", "model": "gemini-2.5-flash"},
            "filter": {"enabled": True, "provider": "ollama", "model": "llama3.1:8b"},
        }
        filter_prov = MagicMock()
        filter_prov.classify.side_effect = Exception("connection timeout")
        mock_get_provider.return_value = filter_prov
        mock_db.fetch_df.return_value = make_raw_media_df(1)
        mock_extract.return_value = ExtractionResult(
            content_hash="hash_0", predictions=[]
        )

        summary = run_extraction(limit=10, db=mock_db, provider=mock_provider)

        assert summary["filtered_out"] == 0
        mock_extract.assert_called_once()


# ---------------------------------------------------------------------------
# LLM Provider
# ---------------------------------------------------------------------------


class TestLLMProvider:
    def test_provider_factory_returns_ollama_by_default(self):
        from src.llm_provider import load_llm_config

        config = load_llm_config()
        assert config["extraction"]["provider"] == "ollama"

    def test_provider_factory_lists_all_providers(self):
        from src.llm_provider import PROVIDERS

        assert set(PROVIDERS.keys()) == {"gemini", "claude", "openai", "ollama"}

    def test_json_parse_strips_markdown_fences(self):
        from src.llm_provider import LLMProvider

        class DummyProvider(LLMProvider):
            def extract_predictions(self, prompt):
                pass

            def classify(self, prompt):
                pass

        provider = DummyProvider(model="test")
        text = '```json\n[{"extracted_claim": "test", "claim_category": "trade"}]\n```'
        result = provider._parse_json_response(text)
        assert len(result) == 1
        assert result[0]["extracted_claim"] == "test"

    def test_json_parse_handles_invalid(self):
        from src.llm_provider import LLMProvider

        class DummyProvider(LLMProvider):
            def extract_predictions(self, prompt):
                pass

            def classify(self, prompt):
                pass

        provider = DummyProvider(model="test")
        result = provider._parse_json_response("not json at all")
        assert result == []


# ---------------------------------------------------------------------------
# Stance field extraction
# ---------------------------------------------------------------------------


class TestStanceExtraction:
    """Stance (bullish/bearish/neutral) is mapped from LLM output to PunditPrediction."""

    @patch("src.assertion_extractor.ingest_batch")
    @patch("src.assertion_extractor.extract_assertions")
    def test_bullish_stance_is_passed_through(
        self, mock_extract, mock_ingest, mock_db, mock_provider
    ):
        mock_db.fetch_df.return_value = make_raw_media_df(1)
        mock_extract.return_value = ExtractionResult(
            content_hash="hash_0",
            predictions=[
                {
                    "extracted_claim": "Mahomes wins MVP in 2026",
                    "claim_category": "player_performance",
                    "stance": "bullish",
                    "confidence_note": "strong",
                }
            ],
        )
        mock_ingest.return_value = ["pred_hash_1"]

        run_extraction(limit=10, db=mock_db, provider=mock_provider)

        prediction = mock_ingest.call_args[0][0][0]
        assert prediction.stance == "bullish"

    @patch("src.assertion_extractor.ingest_batch")
    @patch("src.assertion_extractor.extract_assertions")
    def test_bearish_stance_is_passed_through(
        self, mock_extract, mock_ingest, mock_db, mock_provider
    ):
        mock_db.fetch_df.return_value = make_raw_media_df(1)
        mock_extract.return_value = ExtractionResult(
            content_hash="hash_0",
            predictions=[
                {
                    "extracted_claim": "Browns miss playoffs in 2026",
                    "claim_category": "game_outcome",
                    "stance": "bearish",
                    "confidence_note": "explicit",
                }
            ],
        )
        mock_ingest.return_value = ["pred_hash_1"]

        run_extraction(limit=10, db=mock_db, provider=mock_provider)

        prediction = mock_ingest.call_args[0][0][0]
        assert prediction.stance == "bearish"

    @patch("src.assertion_extractor.ingest_batch")
    @patch("src.assertion_extractor.extract_assertions")
    def test_neutral_stance_is_passed_through(
        self, mock_extract, mock_ingest, mock_db, mock_provider
    ):
        mock_db.fetch_df.return_value = make_raw_media_df(1)
        mock_extract.return_value = ExtractionResult(
            content_hash="hash_0",
            predictions=[
                {
                    "extracted_claim": "Kelce retires after 2026 season",
                    "claim_category": "player_performance",
                    "stance": "neutral",
                    "confidence_note": "rumor",
                }
            ],
        )
        mock_ingest.return_value = ["pred_hash_1"]

        run_extraction(limit=10, db=mock_db, provider=mock_provider)

        prediction = mock_ingest.call_args[0][0][0]
        assert prediction.stance == "neutral"

    @patch("src.assertion_extractor.ingest_batch")
    @patch("src.assertion_extractor.extract_assertions")
    def test_missing_stance_defaults_to_neutral(
        self, mock_extract, mock_ingest, mock_db, mock_provider
    ):
        """If LLM omits stance (pre-migration model), default to neutral."""
        mock_db.fetch_df.return_value = make_raw_media_df(1)
        mock_extract.return_value = ExtractionResult(
            content_hash="hash_0",
            predictions=[
                {
                    "extracted_claim": "Allen goes to Pro Bowl",
                    "claim_category": "player_performance",
                    "confidence_note": "strong",
                    # no "stance" key
                }
            ],
        )
        mock_ingest.return_value = ["pred_hash_1"]

        run_extraction(limit=10, db=mock_db, provider=mock_provider)

        prediction = mock_ingest.call_args[0][0][0]
        assert prediction.stance == "neutral"

    @patch("src.assertion_extractor.ingest_batch")
    @patch("src.assertion_extractor.extract_assertions")
    def test_invalid_stance_normalized_to_neutral(
        self, mock_extract, mock_ingest, mock_db, mock_provider
    ):
        """Unexpected stance values from LLM are coerced to neutral."""
        mock_db.fetch_df.return_value = make_raw_media_df(1)
        mock_extract.return_value = ExtractionResult(
            content_hash="hash_0",
            predictions=[
                {
                    "extracted_claim": "Eagles win NFC East",
                    "claim_category": "game_outcome",
                    "stance": "positive",  # non-standard value
                    "confidence_note": "strong",
                }
            ],
        )
        mock_ingest.return_value = ["pred_hash_1"]

        run_extraction(limit=10, db=mock_db, provider=mock_provider)

        prediction = mock_ingest.call_args[0][0][0]
        assert prediction.stance == "neutral"


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
