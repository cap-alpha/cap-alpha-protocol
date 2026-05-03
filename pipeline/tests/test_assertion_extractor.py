"""
Tests for the NLP Assertion Extraction Pipeline (Issue #79, #178).
Unit tests — no LLM API or BigQuery required.
"""

import json
import os
from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from google.api_core.exceptions import NotFound
from src.assertion_extractor import (
    DEFAULT_PRIORITY_TIER,
    VALID_CATEGORIES,
    ExtractionResult,
    _apply_priority_sort,
    _deduplicate_claims,
    _validate_source_id,
    extract_assertions,
    get_source_priority_tier,
    get_unprocessed_media,
    is_skip_extraction,
    load_source_config,
    mark_as_processed,
    reset_processed_hashes,
    run_extraction,
    should_filter_article,
    write_raw_utterances,
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

    def test_retries_on_transient_errors_then_succeeds(self, mock_provider):
        """2 transient connection failures followed by success — tenacity retries."""
        from src.assertion_extractor import _is_transient_llm_error

        success_predictions = [
            {
                "extracted_claim": "Mahomes wins MVP in 2026",
                "claim_category": "player_performance",
                "season_year": 2026,
                "target_player": "Patrick Mahomes",
                "target_team": "KC",
                "confidence_note": "strong",
            }
        ]

        call_count = {"n": 0}

        def flaky_extract(prompt):
            call_count["n"] += 1
            if call_count["n"] < 3:
                raise ConnectionError("connection refused")
            return success_predictions

        mock_provider.extract_predictions.side_effect = flaky_extract

        result = extract_assertions(
            content_hash="abc123",
            text="Mahomes is going all the way",
            provider=mock_provider,
        )

        # Verify the call was retried and ultimately succeeded
        assert call_count["n"] == 3
        assert result.error is None
        assert len(result.predictions) == 1
        assert result.predictions[0]["extracted_claim"] == "Mahomes wins MVP in 2026"

    def test_does_not_retry_on_permanent_errors(self, mock_provider):
        """Auth/quota errors are permanent — tenacity should NOT retry them."""
        call_count = {"n": 0}

        def auth_fail(prompt):
            call_count["n"] += 1
            raise Exception("401 unauthorized invalid api key")

        mock_provider.extract_predictions.side_effect = auth_fail

        result = extract_assertions(
            content_hash="abc123",
            text="Some text",
            provider=mock_provider,
        )

        # Should have been called only once (no retries on permanent errors)
        assert call_count["n"] == 1
        assert result.error is not None

    def test_is_transient_llm_error_classifies_correctly(self):
        """Unit test for the transient-error classifier."""
        from src.assertion_extractor import _is_transient_llm_error

        # Transient errors
        assert _is_transient_llm_error(Exception("connection refused")) is True
        assert _is_transient_llm_error(Exception("read timeout occurred")) is True
        assert (
            _is_transient_llm_error(Exception("HTTP error 503 service unavailable"))
            is True
        )
        assert _is_transient_llm_error(ConnectionError("reset by peer")) is True

        # Permanent errors — must NOT be retried
        assert _is_transient_llm_error(Exception("401 unauthorized")) is False
        assert _is_transient_llm_error(Exception("invalid api key")) is False
        assert _is_transient_llm_error(Exception("quota exceeded")) is False
        assert _is_transient_llm_error(Exception("403 forbidden")) is False

    def test_valid_categories_are_complete(self):
        """All expected categories are defined."""
        expected = {
            "player_performance",
            "game_outcome",
            "trade",
            "draft_pick",
            "injury",
            "contract",
            "award_prediction",
            "fa_signing",
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

    def test_source_reset_uses_named_parameter(self, mock_db):
        """Fix for #553: source_id must be passed as @source_id named param, not interpolated."""
        mock_result = MagicMock()
        mock_result.job.num_dml_affected_rows = 3
        mock_db.execute.return_value = mock_result

        deleted = reset_processed_hashes(mock_db, source_id="espn_nfl")

        assert deleted == 3
        call_args = mock_db.execute.call_args
        # call_args.args holds positional args, call_args.kwargs holds keyword args
        query = call_args.args[0]
        # Query must use @source_id placeholder — NOT the literal value interpolated
        assert "@source_id" in query
        assert "espn_nfl" not in query  # value must not appear in SQL text
        # query_parameters kwarg must be set with the correct value
        query_params = call_args.kwargs.get("query_parameters")
        assert query_params is not None
        assert len(query_params) == 1
        assert query_params[0].name == "source_id"
        assert query_params[0].value == "espn_nfl"

    def test_handles_zero_rows(self, mock_db):
        mock_result = MagicMock()
        mock_result.job.num_dml_affected_rows = None
        mock_db.execute.return_value = mock_result

        assert reset_processed_hashes(mock_db) == 0


# ---------------------------------------------------------------------------
# Security: SQL injection regression tests (#553)
# ---------------------------------------------------------------------------


class TestValidateSourceId:
    """Unit tests for the _validate_source_id allowlist guard."""

    def test_valid_alphanum_id(self):
        assert _validate_source_id("espn_nfl") == "espn_nfl"

    def test_valid_id_with_hyphens(self):
        assert _validate_source_id("pat-mcafee-show") == "pat-mcafee-show"

    def test_valid_id_with_numbers(self):
        assert _validate_source_id("source123") == "source123"

    def test_rejects_single_quote(self):
        """A bare single quote would break a naively interpolated SQL string."""
        with pytest.raises(ValueError, match="Invalid source_id"):
            _validate_source_id("foo'bar")

    def test_rejects_classic_sqli_payload(self):
        """Classic SQLi payload must be rejected before reaching any query."""
        with pytest.raises(ValueError, match="Invalid source_id"):
            _validate_source_id("foo' OR '1'='1")

    def test_rejects_comment_payload(self):
        """SQL comment sequence should be rejected."""
        with pytest.raises(ValueError, match="Invalid source_id"):
            _validate_source_id("foo; -- DROP TABLE")

    def test_rejects_space(self):
        with pytest.raises(ValueError, match="Invalid source_id"):
            _validate_source_id("has space")

    def test_rejects_empty_string(self):
        with pytest.raises(ValueError, match="Invalid source_id"):
            _validate_source_id("")

    def test_rejects_oversized_id(self):
        """IDs longer than 128 chars should fail."""
        with pytest.raises(ValueError, match="Invalid source_id"):
            _validate_source_id("a" * 129)


class TestResetProcessedHashesSecurity:
    """Regression tests for the SQLi fix in reset_processed_hashes (#553)."""

    def test_malicious_source_id_raises_before_query(self, mock_db):
        """A SQLi payload must raise ValueError — db.execute must never be called."""
        with pytest.raises(ValueError, match="Invalid source_id"):
            reset_processed_hashes(mock_db, source_id="foo' OR '1'='1")

        mock_db.execute.assert_not_called()

    def test_semicolon_payload_raises(self, mock_db):
        with pytest.raises(ValueError, match="Invalid source_id"):
            reset_processed_hashes(
                mock_db,
                source_id="x; DELETE FROM processed_media_hashes WHERE TRUE; --",
            )

        mock_db.execute.assert_not_called()

    def test_valid_source_id_still_works(self, mock_db):
        """A legitimate source_id must still execute successfully."""
        mock_result = MagicMock()
        mock_result.job.num_dml_affected_rows = 2
        mock_db.execute.return_value = mock_result

        deleted = reset_processed_hashes(mock_db, source_id="the_athletic_nfl")
        assert deleted == 2
        mock_db.execute.assert_called_once()


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
    def test_error_does_not_mark_as_processed(
        self, mock_extract, mock_db, mock_provider
    ):
        """Transient LLM errors must NOT mark the hash processed so next run retries."""
        mock_db.fetch_df.return_value = make_raw_media_df(1)
        mock_extract.return_value = ExtractionResult(
            content_hash="hash_0",
            predictions=[],
            error="connection timeout",
        )

        run_extraction(limit=10, db=mock_db, provider=mock_provider)

        # mark_as_processed (append_dataframe_to_table) must NOT be called for
        # errored articles — they should remain unprocessed for the next run.
        mock_db.append_dataframe_to_table.assert_not_called()

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

        assert (
            set(PROVIDERS.keys())
            == {
                "gemini",
                "gemini-flash",  # gemini-flash is an alias for GeminiProvider (burst mode for historical backfill)
                "claude",
                "openai",
                "ollama",
            }
        )

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
            "award_prediction",
            "fa_signing",
        }
        assert VALID_CATEGORIES == expected


# ---------------------------------------------------------------------------
# Source priority tiers (Issue #381)
# ---------------------------------------------------------------------------


def make_media_df_with_tiers():
    """DataFrame with mixed sources across three tiers and varying publish dates."""
    from datetime import datetime, timezone

    return pd.DataFrame(
        [
            {
                "content_hash": "hash_tier3_old",
                "source_id": "low_yield_source",
                "title": "Low yield old",
                "raw_text": "content",
                "source_url": "https://example.com/1",
                "author": "Author",
                "matched_pundit_id": "p1",
                "matched_pundit_name": "P1",
                "published_at": datetime(2025, 1, 1, tzinfo=timezone.utc),
                "sport": "NFL",
            },
            {
                "content_hash": "hash_tier1_new",
                "source_id": "espn_nfl",
                "title": "High yield new",
                "raw_text": "content",
                "source_url": "https://example.com/2",
                "author": "Author",
                "matched_pundit_id": "p2",
                "matched_pundit_name": "P2",
                "published_at": datetime(2025, 9, 1, tzinfo=timezone.utc),
                "sport": "NFL",
            },
            {
                "content_hash": "hash_tier2_mid",
                "source_id": "theathletic_nfl",
                "title": "Medium yield mid",
                "raw_text": "content",
                "source_url": "https://example.com/3",
                "author": "Author",
                "matched_pundit_id": "p3",
                "matched_pundit_name": "P3",
                "published_at": datetime(2025, 5, 1, tzinfo=timezone.utc),
                "sport": "NFL",
            },
            {
                "content_hash": "hash_tier1_old",
                "source_id": "pat_mcafee_show",
                "title": "High yield old",
                "raw_text": "content",
                "source_url": "https://example.com/4",
                "author": "Author",
                "matched_pundit_id": "p4",
                "matched_pundit_name": "P4",
                "published_at": datetime(2025, 3, 1, tzinfo=timezone.utc),
                "sport": "NFL",
            },
        ]
    )


class TestApplyPrioritySort:
    """Unit tests for _apply_priority_sort."""

    def test_tier1_before_tier2_before_tier3(self):
        """Tier 1 sources should appear before tier 2 and 3."""
        priority_map = {
            "espn_nfl": 1,
            "pat_mcafee_show": 1,
            "theathletic_nfl": 2,
            "low_yield_source": 3,
        }
        df = make_media_df_with_tiers()
        result = _apply_priority_sort(df, priority_map, limit=10)
        tiers = [
            priority_map.get(sid, DEFAULT_PRIORITY_TIER) for sid in result["source_id"]
        ]
        # Tiers should be non-decreasing
        assert tiers == sorted(tiers)

    def test_within_same_tier_newest_first(self):
        """Within the same tier, newer articles should come first."""
        priority_map = {
            "espn_nfl": 1,
            "pat_mcafee_show": 1,
            "theathletic_nfl": 2,
            "low_yield_source": 3,
        }
        df = make_media_df_with_tiers()
        result = _apply_priority_sort(df, priority_map, limit=10)
        tier1_rows = result[result["source_id"].isin(["espn_nfl", "pat_mcafee_show"])]
        dates = list(tier1_rows["published_at"])
        assert dates == sorted(dates, reverse=True)

    def test_limit_respected(self):
        """Result should not exceed the given limit."""
        priority_map = {"espn_nfl": 1, "theathletic_nfl": 2}
        df = make_media_df_with_tiers()
        result = _apply_priority_sort(df, priority_map, limit=2)
        assert len(result) == 2

    def test_limit_fills_from_tier1_first(self):
        """With limit=2 and two tier-1 sources, both slots go to tier 1."""
        priority_map = {
            "espn_nfl": 1,
            "pat_mcafee_show": 1,
            "theathletic_nfl": 2,
            "low_yield_source": 3,
        }
        df = make_media_df_with_tiers()
        result = _apply_priority_sort(df, priority_map, limit=2)
        for sid in result["source_id"]:
            assert priority_map.get(sid, DEFAULT_PRIORITY_TIER) == 1

    def test_unknown_source_gets_default_tier(self):
        """Sources missing from priority_map get DEFAULT_PRIORITY_TIER (2)."""
        priority_map = {"espn_nfl": 1}  # theathletic_nfl and others not mapped
        df = make_media_df_with_tiers()
        result = _apply_priority_sort(df, priority_map, limit=10)
        # espn_nfl (tier 1) should be first
        assert result.iloc[0]["source_id"] == "espn_nfl"

    def test_empty_dataframe_passthrough(self):
        """Empty DataFrame should return empty without error."""
        result = _apply_priority_sort(pd.DataFrame(), {}, limit=10)
        assert result.empty


class TestSourceConfig:
    """Unit tests for source config helpers."""

    def test_load_source_config_returns_dict(self):
        """load_source_config should return a non-empty dict."""
        import src.assertion_extractor as ae

        # Clear cache so we read from disk
        ae._SOURCE_CONFIG_CACHE = None
        cfg = load_source_config()
        assert isinstance(cfg, dict)
        assert len(cfg) > 0

    def test_known_tier1_sources_have_correct_tier(self):
        """pat_mcafee_show and espn_nfl should be tier 1 per media_sources.yaml."""
        import src.assertion_extractor as ae

        ae._SOURCE_CONFIG_CACHE = None
        assert get_source_priority_tier("pat_mcafee_show") == 1
        assert get_source_priority_tier("espn_nfl") == 1

    def test_skip_extraction_sources(self):
        """club_shay_shay and nfl_official should have skip_extraction=True."""
        import src.assertion_extractor as ae

        ae._SOURCE_CONFIG_CACHE = None
        assert is_skip_extraction("club_shay_shay") is True
        assert is_skip_extraction("nfl_official") is True

    def test_non_skip_source(self):
        """pat_mcafee_show should NOT be skip_extraction."""
        import src.assertion_extractor as ae

        ae._SOURCE_CONFIG_CACHE = None
        assert is_skip_extraction("pat_mcafee_show") is False

    def test_unknown_source_defaults(self):
        """Unknown source gets tier=2 and skip_extraction=False."""
        assert (
            get_source_priority_tier("nonexistent_source_xyz") == DEFAULT_PRIORITY_TIER
        )
        assert is_skip_extraction("nonexistent_source_xyz") is False


class TestPriorityInGetUnprocessedMedia:
    """Integration tests for priority sorting in get_unprocessed_media."""

    def test_skip_sources_excluded_from_query(self, mock_db):
        """Sources with skip_extraction=True should appear in the NOT IN filter."""
        import src.assertion_extractor as ae

        ae._SOURCE_CONFIG_CACHE = None
        mock_db.fetch_df.return_value = pd.DataFrame()
        get_unprocessed_media(mock_db)
        query = mock_db.fetch_df.call_args[0][0]
        # club_shay_shay is skip_extraction=True — should be excluded
        assert "club_shay_shay" in query
        assert "NOT IN" in query

    def test_priority_sort_applied_to_results(self, mock_db):
        """Results returned from DB should be re-sorted by tier before returning."""
        import src.assertion_extractor as ae

        ae._SOURCE_CONFIG_CACHE = None
        # Return rows with tier-3 source first, tier-1 source second
        from datetime import datetime, timezone

        raw = pd.DataFrame(
            [
                {
                    "content_hash": "hash_tier3",
                    "source_id": "rotoballer_nfl",  # tier 3
                    "title": "Low yield",
                    "raw_text": "text",
                    "source_url": "https://example.com/a",
                    "author": "A",
                    "matched_pundit_id": "p1",
                    "matched_pundit_name": "P1",
                    "published_at": datetime(2025, 9, 1, tzinfo=timezone.utc),
                    "sport": "NFL",
                },
                {
                    "content_hash": "hash_tier1",
                    "source_id": "espn_nfl",  # tier 1
                    "title": "High yield",
                    "raw_text": "text",
                    "source_url": "https://example.com/b",
                    "author": "B",
                    "matched_pundit_id": "p2",
                    "matched_pundit_name": "P2",
                    "published_at": datetime(2025, 8, 1, tzinfo=timezone.utc),
                    "sport": "NFL",
                },
            ]
        )
        mock_db.fetch_df.return_value = raw
        result = get_unprocessed_media(mock_db, limit=10)
        # espn_nfl (tier 1) should come before rotoballer_nfl (tier 3)
        assert result.iloc[0]["source_id"] == "espn_nfl"
        assert result.iloc[1]["source_id"] == "rotoballer_nfl"

    def test_run_extraction_skips_low_yield_source(self, mock_db, mock_provider):
        """Articles from skip_extraction sources are marked processed without LLM call."""
        import src.assertion_extractor as ae

        ae._SOURCE_CONFIG_CACHE = None
        from datetime import datetime, timezone
        from unittest.mock import patch

        skip_df = pd.DataFrame(
            [
                {
                    "content_hash": "skip_hash_1",
                    "source_id": "club_shay_shay",  # skip_extraction=True
                    "title": "Interview show",
                    "raw_text": "some text content here",
                    "source_url": "https://youtube.com/v/1",
                    "author": "Shannon Sharpe",
                    "matched_pundit_id": "shannon_sharpe",
                    "matched_pundit_name": "Shannon Sharpe",
                    "published_at": datetime(2025, 9, 1, tzinfo=timezone.utc),
                    "sport": "NFL",
                }
            ]
        )
        mock_db.fetch_df.return_value = skip_df

        with patch("src.assertion_extractor.extract_assertions") as mock_extract:
            summary = run_extraction(limit=10, db=mock_db, provider=mock_provider)

        assert summary["skipped_low_yield"] == 1
        assert summary["total_processed"] == 1
        mock_extract.assert_not_called()
        # Should still be marked processed
        mock_db.append_dataframe_to_table.assert_called_once()


# ---------------------------------------------------------------------------
# extraction_run table write
# ---------------------------------------------------------------------------


class TestExtractionRunWrite:
    """_write_extraction_run() is called by run_extraction() in try/finally."""

    @patch("src.assertion_extractor._write_extraction_run")
    @patch("src.assertion_extractor.extract_assertions")
    def test_writes_run_row_on_success(
        self, mock_extract, mock_write_run, mock_db, mock_provider
    ):
        """run_extraction() writes an extraction_run row after a successful run."""
        mock_db.fetch_df.return_value = make_raw_media_df(1)
        mock_extract.return_value = ExtractionResult(
            content_hash="hash_0", predictions=[]
        )

        run_extraction(limit=10, db=mock_db, provider=mock_provider)

        mock_write_run.assert_called_once()
        kwargs = mock_write_run.call_args.kwargs
        assert kwargs["articles_processed"] == 1
        assert kwargs["errors"] == 0
        assert kwargs["provider"] != ""
        assert kwargs["model"] != ""

    @patch("src.assertion_extractor._write_extraction_run")
    @patch("src.assertion_extractor.extract_assertions")
    def test_writes_run_row_on_partial_error(
        self, mock_extract, mock_write_run, mock_db, mock_provider
    ):
        """run_extraction() writes an extraction_run row even when extraction errors occur."""
        mock_db.fetch_df.return_value = make_raw_media_df(1)
        mock_extract.return_value = ExtractionResult(
            content_hash="hash_0",
            predictions=[],
            error="LLM quota exceeded",
        )

        run_extraction(limit=10, db=mock_db, provider=mock_provider)

        mock_write_run.assert_called_once()
        kwargs = mock_write_run.call_args.kwargs
        assert kwargs["errors"] == 1

    @patch("src.assertion_extractor._write_extraction_run")
    def test_skips_run_row_in_dry_run(self, mock_write_run, mock_db):
        """run_extraction(dry_run=True) must NOT write an extraction_run row."""
        mock_db.fetch_df.return_value = make_raw_media_df(2)

        run_extraction(limit=10, dry_run=True, db=mock_db)

        mock_write_run.assert_not_called()

    @patch("src.assertion_extractor._write_extraction_run")
    def test_writes_run_row_when_no_media(self, mock_write_run, mock_db, mock_provider):
        """run_extraction() writes a zero-row extraction_run entry even when there is nothing to extract."""
        mock_db.fetch_df.return_value = pd.DataFrame()

        run_extraction(limit=10, db=mock_db, provider=mock_provider)

        mock_write_run.assert_called_once()
        kwargs = mock_write_run.call_args.kwargs
        assert kwargs["articles_processed"] == 0
        assert kwargs["utterances_written"] == 0

    @patch("src.assertion_extractor._write_extraction_run")
    @patch("src.assertion_extractor.extract_assertions")
    def test_tracks_utterance_metrics(
        self, mock_extract, mock_write_run, mock_db, mock_provider
    ):
        """mean_testability_score and metadata_completeness_pct are computed from utterances."""
        mock_db.fetch_df.return_value = make_raw_media_df(1)
        mock_extract.return_value = ExtractionResult(
            content_hash="hash_0",
            predictions=[],
            utterances=[
                {
                    "text": "Mahomes wins MVP",
                    "speech_act_type": "assertion",
                    "testability_score": 0.8,
                    "extraction_confidence": 0.9,
                },
                {
                    "text": "The season will be interesting",
                    "speech_act_type": "opinion",
                    "testability_score": 0.2,
                    "extraction_confidence": 0.7,
                },
            ],
        )

        run_extraction(limit=10, db=mock_db, provider=mock_provider)

        mock_write_run.assert_called_once()
        kwargs = mock_write_run.call_args.kwargs
        assert kwargs["mean_testability_score"] == pytest.approx(0.5, abs=1e-6)
        assert kwargs["metadata_completeness_pct"] == pytest.approx(100.0, abs=1e-6)


# ---------------------------------------------------------------------------
# write_raw_utterances — resolution_horizon serialization (#555)
# ---------------------------------------------------------------------------


def _capture_load_args(mock_db):
    """Return the rows list passed to db.client.load_table_from_dataframe."""
    call_args = mock_db.client.load_table_from_dataframe.call_args
    df = call_args[0][0]  # first positional arg is the DataFrame
    return df.to_dict(orient="records")


def _make_mock_db_for_bq_write():
    """Build a mock DBManager whose BQ load path succeeds."""
    db = MagicMock()
    mock_job = MagicMock()
    mock_job.result.return_value = None
    db.client.load_table_from_dataframe.return_value = mock_job
    return db


class TestWriteRawUtterancesResolutionHorizon:
    """
    Regression tests for the resolution_horizon TIMESTAMP serialization.

    silver_v2_claims.raw_utterance defines resolution_horizon as TIMESTAMP
    (nullable).  The column must be written as datetime64[ns, UTC] so pyarrow
    can serialize it correctly.  Passing an "object" dtype column (strings/None)
    caused the "Array, ListArray, or StructArray" pyarrow error and silently
    dropped every row.  The fix applies pd.to_datetime(utc=True, errors="coerce")
    to the column before calling load_table_from_dataframe.
    """

    _BASE_UTTERANCE = {
        "text": "Mahomes will win MVP",
        "speech_act_type": "assertion",
        "testability_score": 0.9,
        "extraction_confidence": 0.9,
    }

    def _write_one(self, resolution_horizon_value):
        """Helper: write a single utterance with the given resolution_horizon."""
        import os

        os.environ.setdefault("GCP_PROJECT_ID", "test-project")
        db = _make_mock_db_for_bq_write()
        utterance = {
            **self._BASE_UTTERANCE,
            "resolution_horizon": resolution_horizon_value,
        }
        n = write_raw_utterances(
            utterances=[utterance],
            source_doc_id="doc_abc",
            speaker_entity_id="entity_xyz",
            uttered_at=datetime(2025, 9, 1, tzinfo=timezone.utc),
            domain="nfl",
            db=db,
        )
        assert n == 1, "Expected 1 row written"
        rows = _capture_load_args(db)
        assert len(rows) == 1
        return rows[0]["resolution_horizon"]

    def _is_utc_timestamp(self, val):
        import pandas as pd

        return isinstance(val, pd.Timestamp) and val.tzinfo is not None

    def test_datetime_becomes_utc_timestamp(self):
        """datetime object → UTC pd.Timestamp in the written DataFrame."""
        dt = datetime(2025, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
        result = self._write_one(dt)
        assert self._is_utc_timestamp(result)
        assert result.year == 2025 and result.month == 12 and result.day == 31

    def test_date_becomes_utc_timestamp(self):
        """date object → UTC pd.Timestamp (midnight UTC)."""
        d = date(2025, 12, 31)
        result = self._write_one(d)
        assert self._is_utc_timestamp(result)
        assert result.year == 2025 and result.month == 12 and result.day == 31

    def test_pd_timestamp_stays_utc_timestamp(self):
        """pd.Timestamp → UTC pd.Timestamp."""
        import pandas as pd

        ts = pd.Timestamp("2025-12-31T23:59:59Z")
        result = self._write_one(ts)
        assert self._is_utc_timestamp(result)
        assert result.year == 2025

    def test_dict_becomes_nat(self):
        """dict cannot represent a datetime → NaT (NULL in BQ)."""
        import pandas as pd

        result = self._write_one({"year": 2025, "quarter": "Q4"})
        assert result is pd.NaT

    def test_list_becomes_nat(self):
        """list cannot represent a datetime → NaT (NULL in BQ)."""
        import pandas as pd

        result = self._write_one(["2025-Q4", "end of season"])
        assert result is pd.NaT

    def test_iso_string_becomes_utc_timestamp(self):
        """ISO-8601 string → UTC pd.Timestamp."""
        result = self._write_one("2025-12-31T23:59:59Z")
        assert self._is_utc_timestamp(result)
        assert result.year == 2025

    def test_unparseable_string_becomes_nat(self):
        """Non-date string (e.g. 'end of season') → NaT (NULL in BQ)."""
        import pandas as pd

        result = self._write_one("end of the 2025 NFL season")
        assert result is pd.NaT

    def test_none_becomes_nat(self):
        """None → NaT (NULL in BQ TIMESTAMP column)."""
        import pandas as pd

        result = self._write_one(None)
        assert result is pd.NaT

    def test_empty_string_becomes_nat(self):
        """Empty string cannot be parsed as datetime → NaT."""
        import pandas as pd

        result = self._write_one("")
        assert result is pd.NaT

    def test_multiple_utterances_all_written(self):
        """All rows in a batch are written; valid dates become Timestamps, None → NaT."""
        import os

        import pandas as pd

        os.environ.setdefault("GCP_PROJECT_ID", "test-project")
        db = _make_mock_db_for_bq_write()
        utterances = [
            {
                **self._BASE_UTTERANCE,
                "resolution_horizon": datetime(2025, 12, 31, tzinfo=timezone.utc),
            },
            {**self._BASE_UTTERANCE, "resolution_horizon": "2026-01-15T00:00:00Z"},
            {**self._BASE_UTTERANCE, "resolution_horizon": None},
        ]
        n = write_raw_utterances(
            utterances=utterances,
            source_doc_id="doc_multi",
            speaker_entity_id="entity_xyz",
            uttered_at=datetime(2025, 9, 1, tzinfo=timezone.utc),
            domain="nfl",
            db=db,
        )
        assert n == 3
        rows = _capture_load_args(db)
        assert len(rows) == 3
        # datetime → UTC Timestamp
        assert self._is_utc_timestamp(rows[0]["resolution_horizon"])
        assert rows[0]["resolution_horizon"].year == 2025
        # ISO string → UTC Timestamp
        assert self._is_utc_timestamp(rows[1]["resolution_horizon"])
        assert rows[1]["resolution_horizon"].year == 2026
        # None → NaT
        assert rows[2]["resolution_horizon"] is pd.NaT
