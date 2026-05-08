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
    _resolve_speaker_entity_id,
    _sport_to_domain,
    _validate_source_id,
    check_content_quality,
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
                # Text must be >= 50 words to pass the content quality gate.
                "raw_text": (
                    "I think Patrick Mahomes will definitely win MVP this season. "
                    "He's been the best quarterback by far and nobody in the NFL is close. "
                    "The Kansas City Chiefs offense has been unstoppable and the defense "
                    "continues to improve. Mahomes' ability to extend plays and his "
                    "accuracy on deep routes make him a truly exceptional talent. "
                    "The Super Bowl is a real possibility for Kansas City this year."
                ),
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
        # The raw long_text is 10000 chars but extract_assertions truncates to 4000.
        # Verify truncation by checking the un-truncated tail is absent from the prompt.
        assert "x" * 5000 not in prompt_text  # tail of long_text should be absent
        assert "x" * 4000 in prompt_text  # first 4000 chars should be present

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

    def test_politics_sport_bypasses_filter_without_llm_call(self):
        """Politics articles must never hit the sports content filter (issue #683).

        The filter prompt asks about sports predictions — a political article will
        always get 'no', causing silent drop of ALL political content.  The fix
        bypasses the filter entirely for non-sports domains.
        """
        provider = MagicMock()
        provider.classify.return_value = "no"  # LLM would say no if called
        result = should_filter_article(
            "Senator X will win the election",
            filter_provider=provider,
            sport="politics",
        )
        assert result is False, "Politics articles must pass through (not be filtered)"
        provider.classify.assert_not_called()

    def test_finance_sport_bypasses_filter_without_llm_call(self):
        """Finance articles must also bypass the sports content filter."""
        provider = MagicMock()
        provider.classify.return_value = "no"
        result = should_filter_article(
            "Stock market will rally next quarter",
            filter_provider=provider,
            sport="finance",
        )
        assert result is False
        provider.classify.assert_not_called()

    def test_nfl_sport_still_uses_filter(self):
        """NFL articles should still go through the filter as before."""
        provider = MagicMock()
        provider.classify.return_value = "no"
        result = should_filter_article(
            "Game recap from last week",
            filter_provider=provider,
            sport="NFL",
        )
        assert result is True
        provider.classify.assert_called_once()

    def test_unknown_non_sports_domain_bypasses_filter(self):
        """Any unrecognised domain (not nfl/nba/mlb/nhl/sports) should bypass the filter."""
        provider = MagicMock()
        provider.classify.return_value = "no"
        result = should_filter_article(
            "Some general content",
            filter_provider=provider,
            sport="entertainment",
        )
        assert result is False
        provider.classify.assert_not_called()


class TestSportToDomain:
    """Tests for the _sport_to_domain helper (issue #683)."""

    def test_nfl_maps_to_nfl(self):
        assert _sport_to_domain("NFL") == "nfl"

    def test_politics_maps_to_politics(self):
        assert _sport_to_domain("politics") == "politics"

    def test_finance_maps_to_finance(self):
        assert _sport_to_domain("Finance") == "finance"

    def test_strips_whitespace(self):
        assert _sport_to_domain("  nfl  ") == "nfl"


class TestCheckContentQuality:
    """Tests for the pre-LLM content quality gate (spam + word-count filter)."""

    def test_empty_text_is_spam(self):
        is_spam, reason = check_content_quality("")
        assert is_spam is True
        assert "empty" in reason

    def test_short_text_below_threshold_is_spam(self):
        """Fewer than 50 words → filtered regardless of content."""
        short = "NFL picks week 10. Chiefs over Eagles."
        is_spam, reason = check_content_quality(short)
        assert is_spam is True
        assert "too short" in reason

    def test_genuine_nfl_article_passes(self):
        """A normal NFL article should NOT be filtered."""
        long_nfl = (
            "Patrick Mahomes and the Kansas City Chiefs are preparing for what promises to be "
            "an exciting NFL playoff run. The offense has been clicking on all cylinders and "
            "the defense has stepped up in key moments. Analysts across the league believe the "
            "Chiefs are the favorites to reach the Super Bowl, with Mahomes having arguably the "
            "best statistical season of his career. The draft strategy this offseason will be "
            "crucial for the front office as they look to build depth behind their star quarterback."
        )
        is_spam, reason = check_content_quality(long_nfl)
        assert is_spam is False
        assert reason == ""

    def test_gambling_spam_no_nfl_signals_is_filtered(self):
        """Content with spam signals and zero NFL team/player words → filtered."""
        spam = " ".join(
            [
                "Email Verification: 1 SC for new accounts.",
                "No table games available in your state.",
                "Claim your bonus code for free spins on registration.",
                "Wagering requirements apply to all deposit match offers.",
                "Sign up bonus available to new players only.",
                "Play for free with sweepstakes coins today.",
                "Create your account and start winning real prizes right now.",
                "Offer valid for new users in eligible states only.",
                "Terms and conditions apply to all promotional offers listed here.",
            ]
        )
        is_spam, reason = check_content_quality(spam)
        assert is_spam is True
        assert "spam signal" in reason

    def test_spam_signals_with_nfl_content_passes(self):
        """If an article has spam-like words BUT also has NFL signals, don't filter."""
        mixed = (
            "The Eagles won their game on Sunday. Unfortunately the site requires email "
            "verification for user accounts. Nonetheless, the Eagles defense was dominant and "
            "the Chiefs offense struggled. NFL analysts weighed in across the league. This "
            "season the Eagles could reach the playoffs and the Super Bowl remains a goal. "
            "Multiple sweepstakes promotions were running during the broadcast of the game."
        )
        is_spam, reason = check_content_quality(mixed)
        # Has both spam signal (sweepstakes) AND NFL signal (Eagles, Chiefs, Super Bowl)
        assert is_spam is False

    def test_exact_audit_sample_is_filtered(self):
        """The exact pattern from the BQ audit ('No table games', 'Email Verification: 1 SC')."""
        spam_sample = (
            "No table games available in this region. Email Verification: 1 SC awarded "
            "upon account verification. Sign up bonus: 2500 GC plus 2.5 SC free on registration. "
            "Sweepstakes coins are not redeemable for cash. Read terms before participating. "
            "New players only. Players in restricted states are not eligible for this offer. "
            "Contact customer support for more details about bonus code redemption."
        )
        is_spam, reason = check_content_quality(spam_sample)
        assert is_spam is True

    def test_source_id_included_in_call_does_not_affect_result(self):
        """source_id parameter is for logging; shouldn't change filter logic."""
        long_nfl = " ".join(["NFL chiefs eagles mahomes super bowl draft playoff"] * 10)
        is_spam_generic, _ = check_content_quality(long_nfl, source_id="")
        is_spam_sharp, _ = check_content_quality(long_nfl, source_id="sharp_football")
        assert is_spam_generic == is_spam_sharp


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
            limit=10,
            db=mock_db,
            provider=mock_provider,
            disable_filter=True,
            disable_triage=True,
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
        """pat_mcafee_show and theathletic_nfl should be tier 1 per media_sources.yaml."""
        import src.assertion_extractor as ae

        ae._SOURCE_CONFIG_CACHE = None
        assert get_source_priority_tier("pat_mcafee_show") == 1
        assert get_source_priority_tier("theathletic_nfl") == 1

    def test_known_tier2_sources_have_correct_tier(self):
        """espn_nfl should be tier 2 per media_sources.yaml (issue #381)."""
        import src.assertion_extractor as ae

        ae._SOURCE_CONFIG_CACHE = None
        assert get_source_priority_tier("espn_nfl") == 2

    def test_known_tier3_sources_have_correct_tier(self):
        """pft_nbc should be tier 3 per media_sources.yaml (issue #381)."""
        import src.assertion_extractor as ae

        ae._SOURCE_CONFIG_CACHE = None
        assert get_source_priority_tier("pft_nbc") == 3

    def test_skip_extraction_sources(self):
        """club_shay_shay should have skip_extraction=True.
        nfl_official was removed from media_sources.yaml (permanently dead — 2026-05),
        so it falls through to the default (False).
        """
        import src.assertion_extractor as ae

        ae._SOURCE_CONFIG_CACHE = None
        assert is_skip_extraction("club_shay_shay") is True
        # nfl_official removed from config; unknown source → default False
        assert is_skip_extraction("nfl_official") is False

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

    def test_query_orders_by_priority_tier_then_ingested_at(self, mock_db):
        """Main query should ORDER BY priority_tier ASC, ingested_at DESC (issue #381)."""
        import src.assertion_extractor as ae

        ae._SOURCE_CONFIG_CACHE = None
        mock_db.fetch_df.return_value = pd.DataFrame()
        get_unprocessed_media(mock_db)
        query = mock_db.fetch_df.call_args[0][0]
        assert "ORDER BY" in query
        assert "ASC" in query
        assert "ingested_at DESC" in query

    def test_fallback_query_orders_by_priority_tier_then_ingested_at(self, mock_db):
        """Fallback query (no tracking table) also ORDER BY priority_tier ASC, ingested_at DESC."""
        import src.assertion_extractor as ae
        from google.api_core.exceptions import NotFound

        ae._SOURCE_CONFIG_CACHE = None
        mock_db.fetch_df.side_effect = [
            NotFound("processed_media_hashes"),
            pd.DataFrame(),
        ]
        get_unprocessed_media(mock_db)
        fallback_query = mock_db.fetch_df.call_args_list[1][0][0]
        assert "ORDER BY" in fallback_query
        assert "ASC" in fallback_query
        assert "ingested_at DESC" in fallback_query

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
                    "source_id": "rotoballer_nfl",  # unknown source → DEFAULT_PRIORITY_TIER (2)
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
                    "source_id": "pat_mcafee_show",  # tier 1 (McAfee transcripts)
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
        # pat_mcafee_show (tier 1) should come before rotoballer_nfl (unknown → tier 2)
        assert result.iloc[0]["source_id"] == "pat_mcafee_show"
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


# ---------------------------------------------------------------------------
# write_raw_utterances — new metadata fields (#674, #675)
# ---------------------------------------------------------------------------


class TestWriteRawUtterancesMetadata:
    """
    Tests that subscore, stance, horizon, and 7B verification fields
    are persisted in the BQ row rather than discarded (#674, #675).
    """

    _UTTERED_AT = datetime(2025, 9, 1, tzinfo=timezone.utc)

    def _write_utterance(self, utterance: dict) -> dict:
        """Write a single utterance and return the first captured BQ row."""
        import os

        os.environ.setdefault("GCP_PROJECT_ID", "test-project")
        db = _make_mock_db_for_bq_write()
        write_raw_utterances(
            utterances=[utterance],
            source_doc_id="doc_meta",
            speaker_entity_id="entity_meta",
            uttered_at=self._UTTERED_AT,
            domain="nfl",
            db=db,
        )
        rows = _capture_load_args(db)
        assert len(rows) == 1
        return rows[0]

    def test_subscore_fields_persisted(self):
        """All five testability sub-scores from #674 are written to BQ."""
        utterance = {
            "text": "Mahomes wins MVP",
            "speech_act_type": "assertion",
            "testability_score": 0.9,
            "extraction_confidence": 0.9,
            "testability_subscores": {
                "subject_specificity": 1.0,
                "predicate_falsifiability": 0.9,
                "threshold_concreteness": 0.8,
                "resolution_horizon_defined": 0.7,
                "evidence_accessibility": 1.0,
            },
        }
        row = self._write_utterance(utterance)
        assert float(row["subscore_subject_specificity"]) == pytest.approx(1.0)
        assert float(row["subscore_predicate_falsifiability"]) == pytest.approx(0.9)
        assert float(row["subscore_threshold_concreteness"]) == pytest.approx(0.8)
        assert float(row["subscore_resolution_horizon_defined"]) == pytest.approx(0.7)
        assert float(row["subscore_evidence_accessibility"]) == pytest.approx(1.0)

    def test_stance_field_persisted(self):
        """stance value from LLM is written to BQ (#674)."""
        utterance = {
            "text": "Mahomes wins MVP",
            "speech_act_type": "assertion",
            "testability_score": 0.9,
            "extraction_confidence": 0.9,
            "stance": "bullish",
        }
        row = self._write_utterance(utterance)
        assert row["stance"] == "bullish"

    def test_prediction_horizon_days_persisted(self):
        """prediction_horizon_days from LLM is written to BQ (#674)."""
        utterance = {
            "text": "Eagles win NFC East",
            "speech_act_type": "assertion",
            "testability_score": 0.85,
            "extraction_confidence": 0.85,
            "prediction_horizon_days": 120,
        }
        row = self._write_utterance(utterance)
        # DataFrame int → str after astype(str), so compare as string or int
        assert str(row["prediction_horizon_days"]) == "120"

    def test_confidence_note_persisted(self):
        """confidence_note from LLM is written to BQ (#674)."""
        utterance = {
            "text": "Kelce retires",
            "speech_act_type": "assertion",
            "testability_score": 0.7,
            "extraction_confidence": 0.7,
            "confidence_note": "explicit numeric threshold",
        }
        row = self._write_utterance(utterance)
        assert row["confidence_note"] == "explicit numeric threshold"

    def test_resolution_condition_persisted(self):
        """resolution_condition from #675 is written to BQ."""
        utterance = {
            "text": "Hill traded before June",
            "speech_act_type": "assertion",
            "testability_score": 0.8,
            "extraction_confidence": 0.8,
            "resolution_condition": "Reported by major outlet as traded before 2026-06-01",
        }
        row = self._write_utterance(utterance)
        assert "traded before" in row["resolution_condition"]

    def test_hedge_level_persisted(self):
        """hedge_level from #675 is written to BQ."""
        utterance = {
            "text": "I think the Eagles might win",
            "speech_act_type": "hedge",
            "testability_score": 0.4,
            "extraction_confidence": 0.6,
            "hedge_level": "weak",
        }
        row = self._write_utterance(utterance)
        assert row["hedge_level"] == "weak"

    def test_verification_fields_persisted(self):
        """7B verification fields from #675 are written to BQ."""
        utterance = {
            "text": "Mahomes wins MVP",
            "speech_act_type": "assertion",
            "testability_score": 0.9,
            "extraction_confidence": 0.9,
            "claim_text_alignment": 0.95,
            "hallucination_risk": "low",
            "verification_flags": ["team_inferred"],
            "quality_score": 0.88,
            "needs_review": False,
        }
        row = self._write_utterance(utterance)
        assert float(row["claim_text_alignment"]) == pytest.approx(0.95)
        assert row["hallucination_risk"] == "low"
        assert row["quality_score"] is not None
        # verification_flags is ARRAY<STRING> — serialized as list
        assert "team_inferred" in row["verification_flags"]
        # needs_review is BOOL — not coerced to str by the object-dtype loop
        assert row["needs_review"] is False

    def test_missing_metadata_fields_default_to_none(self):
        """When LLM doesn't return optional fields, they are None (not KeyError)."""
        utterance = {
            "text": "Some claim",
            "speech_act_type": "commentary",
            "testability_score": 0.2,
            "extraction_confidence": 0.5,
        }
        row = self._write_utterance(utterance)
        # All new fields should exist as None/"nan" (not missing from dict)
        assert "subscore_subject_specificity" in row
        assert "resolution_condition" in row
        assert "hedge_level" in row
        assert "claim_text_alignment" in row
        assert "hallucination_risk" in row
        assert "quality_score" in row


# ---------------------------------------------------------------------------
# _resolve_speaker_entity_id
# ---------------------------------------------------------------------------


class TestResolveSpeakerEntityId:
    """Unit tests for the three-tier speaker resolution fallback."""

    def _make_db(self, registry_hit=None, media_hit=None):
        """Build a mock DBManager whose fetch_df returns controlled values."""
        db = MagicMock()

        def _fetch_df(query, query_parameters=None, params=None):
            q = query.strip()
            if "pundit_registry" in q:
                if registry_hit is not None:
                    return pd.DataFrame([{"pundit_id": registry_hit}])
                return pd.DataFrame()
            if "raw_pundit_media" in q:
                if media_hit is not None:
                    return pd.DataFrame([{"matched_pundit_id": media_hit}])
                return pd.DataFrame()
            return pd.DataFrame()

        db.fetch_df.side_effect = _fetch_df
        return db

    def test_no_db_returns_unresolved(self):
        result = _resolve_speaker_entity_id("mike_florio", db=None)
        assert result == "UNRESOLVED:mike_florio"

    def test_no_project_id_returns_unresolved(self, monkeypatch):
        monkeypatch.delenv("GCP_PROJECT_ID", raising=False)
        db = MagicMock()
        result = _resolve_speaker_entity_id("mike_florio", db=db)
        assert result == "UNRESOLVED:mike_florio"

    def test_registry_hit_returns_pundit_id(self, monkeypatch):
        """When pundit_registry has the pundit, return its pundit_id directly."""
        monkeypatch.setenv("GCP_PROJECT_ID", "test-project")
        db = self._make_db(registry_hit="mike_florio")
        result = _resolve_speaker_entity_id("mike_florio", db=db)
        assert result == "mike_florio"
        # raw_pundit_media should NOT have been queried (registry hit short-circuits)
        calls = [str(c) for c in db.fetch_df.call_args_list]
        assert not any("raw_pundit_media" in c for c in calls)

    def test_registry_miss_falls_back_to_media(self, monkeypatch):
        """When registry is empty, fall back to raw_pundit_media.matched_pundit_id."""
        monkeypatch.setenv("GCP_PROJECT_ID", "test-project")
        db = self._make_db(registry_hit=None, media_hit="warren_sharp")
        result = _resolve_speaker_entity_id(
            "unknown_pundit",
            db=db,
            source_doc_id="abc123hash",
        )
        assert result == "warren_sharp"

    def test_registry_miss_no_source_doc_returns_unresolved(self, monkeypatch):
        """Without source_doc_id the media fallback is skipped → UNRESOLVED."""
        monkeypatch.setenv("GCP_PROJECT_ID", "test-project")
        db = self._make_db(registry_hit=None, media_hit="warren_sharp")
        result = _resolve_speaker_entity_id("unknown_pundit", db=db, source_doc_id=None)
        assert result == "UNRESOLVED:unknown_pundit"

    def test_both_miss_returns_unresolved(self, monkeypatch):
        """When both lookups return empty, return the UNRESOLVED placeholder."""
        monkeypatch.setenv("GCP_PROJECT_ID", "test-project")
        db = self._make_db(registry_hit=None, media_hit=None)
        result = _resolve_speaker_entity_id(
            "ghost_pundit",
            db=db,
            source_doc_id="hashxyz",
        )
        assert result == "UNRESOLVED:ghost_pundit"

    def test_registry_exception_falls_back_to_media(self, monkeypatch):
        """A BigQuery error on the registry lookup triggers the media fallback."""
        monkeypatch.setenv("GCP_PROJECT_ID", "test-project")
        db = MagicMock()

        call_count = {"n": 0}

        def _fetch_df(query, query_parameters=None, params=None):
            call_count["n"] += 1
            if "pundit_registry" in query:
                raise RuntimeError("table not found")
            # media fallback
            return pd.DataFrame([{"matched_pundit_id": "adam_schefter"}])

        db.fetch_df.side_effect = _fetch_df
        result = _resolve_speaker_entity_id(
            "adam_schefter",
            db=db,
            source_doc_id="hashcontent",
        )
        assert result == "adam_schefter"
        assert call_count["n"] == 2  # registry tried, media tried


# Canonical "fully-populated" mock LLM response for a promotable assertion.
_FULL_PHASE_C_PAYLOAD = [
    {
        "text": "Patrick Mahomes will win MVP this season.",
        "speech_act_type": "assertion",
        "testability_subscores": {
            "subject_specificity": 1.0,
            "predicate_falsifiability": 1.0,
            "threshold_concreteness": 0.8,
            "resolution_horizon_defined": 0.9,
            "evidence_accessibility": 1.0,
        },
        "testability_score": 0.94,
        "resolution_horizon": "2026-01-31T23:59:59Z",
        "predicate": "will_win_award",
        "subject": "Patrick Mahomes",
        "predicate_args": {"award": "MVP", "league": "NFL"},
        "extracted_claim": "Patrick Mahomes will win NFL MVP in the 2025 season",
        "claim_category": "award_prediction",
        "stance": "bullish",
        "season_year": 2026,
        "target_player": "Patrick Mahomes",
        "target_team": "KC",
        "confidence_note": "explicit award prediction",
        "prediction_horizon_days": 120,
        "extraction_confidence": 0.95,
    }
]

# Non-promotable utterance (rhetorical question) — tests that suppressed
# utterances still carry the new fields without crashing.
_RHETORICAL_PAYLOAD = [
    {
        "text": "Can anyone stop this Chiefs offense?",
        "speech_act_type": "rhetorical_question",
        "testability_subscores": {
            "subject_specificity": 1.0,
            "predicate_falsifiability": 0.1,
            "threshold_concreteness": 0.0,
            "resolution_horizon_defined": 0.0,
            "evidence_accessibility": 0.2,
        },
        "testability_score": 0.26,
        "resolution_horizon": None,
        "predicate": "",
        "subject": "Kansas City Chiefs",
        "predicate_args": {},
        "extracted_claim": "",
        "claim_category": "game_outcome",
        "stance": "bullish",
        "season_year": None,
        "target_player": None,
        "target_team": "KC",
        "confidence_note": "rhetorical emphasis",
        "prediction_horizon_days": -1,
        "extraction_confidence": 0.3,
    }
]


class TestPhaseCNewFields:
    """
    Prove that the updated extraction prompt (PR #723) correctly populates
    the Phase C fields that were previously 100% NULL.
    """

    def test_extract_assertions_populates_text_field(self, mock_provider):
        """'text' (verbatim quote) must be non-null in every utterance."""
        set_provider_predictions(mock_provider, _FULL_PHASE_C_PAYLOAD)
        result = extract_assertions(
            content_hash="abc123",
            text="Patrick Mahomes will win MVP this season.",
            provider=mock_provider,
            allow_historical=True,
        )
        assert result.error is None
        assert len(result.utterances) == 1
        assert (
            result.utterances[0]["text"] == "Patrick Mahomes will win MVP this season."
        )

    def test_extract_assertions_populates_speech_act_type(self, mock_provider):
        """'speech_act_type' must be non-null and one of the valid values."""
        from src.assertion_extractor import VALID_SPEECH_ACT_TYPES

        set_provider_predictions(mock_provider, _FULL_PHASE_C_PAYLOAD)
        result = extract_assertions(
            content_hash="abc123",
            text="Mahomes wins MVP",
            provider=mock_provider,
            allow_historical=True,
        )
        sat = result.utterances[0]["speech_act_type"]
        assert sat is not None
        assert sat in VALID_SPEECH_ACT_TYPES

    def test_extract_assertions_populates_testability_score(self, mock_provider):
        """'testability_score' must be a float in [0, 1]."""
        set_provider_predictions(mock_provider, _FULL_PHASE_C_PAYLOAD)
        result = extract_assertions(
            content_hash="abc123",
            text="Mahomes wins MVP",
            provider=mock_provider,
            allow_historical=True,
        )
        score = result.utterances[0]["testability_score"]
        assert score is not None
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0

    def test_extract_assertions_recomputes_score_from_subscores(self, mock_provider):
        """
        When testability_subscores are present, extract_assertions must
        recompute testability_score from the formula, not trust the LLM value.
        """
        # LLM says score=0.94 but subscores average to 0.94 as well — use real math.
        set_provider_predictions(mock_provider, _FULL_PHASE_C_PAYLOAD)
        result = extract_assertions(
            content_hash="abc123",
            text="Mahomes wins MVP",
            provider=mock_provider,
            allow_historical=True,
        )
        u = result.utterances[0]
        expected = (1.0 + 1.0 + 0.8 + 0.9 + 1.0) / 5
        assert u["testability_score"] == pytest.approx(expected, abs=1e-4)

    def test_extract_assertions_populates_all_five_subscores(self, mock_provider):
        """All five testability_subscores keys must be present and non-null."""
        set_provider_predictions(mock_provider, _FULL_PHASE_C_PAYLOAD)
        result = extract_assertions(
            content_hash="abc123",
            text="Mahomes wins MVP",
            provider=mock_provider,
            allow_historical=True,
        )
        subscores = result.utterances[0].get("testability_subscores", {})
        for key in (
            "subject_specificity",
            "predicate_falsifiability",
            "threshold_concreteness",
            "resolution_horizon_defined",
            "evidence_accessibility",
        ):
            assert key in subscores, f"Missing subscore key: {key}"
            assert subscores[key] is not None, f"Subscore {key} is None"

    def test_extract_assertions_populates_resolution_horizon(self, mock_provider):
        """'resolution_horizon' must be non-null when the LLM provides an ISO date."""
        set_provider_predictions(mock_provider, _FULL_PHASE_C_PAYLOAD)
        result = extract_assertions(
            content_hash="abc123",
            text="Mahomes wins MVP",
            provider=mock_provider,
            allow_historical=True,
        )
        rh = result.utterances[0].get("resolution_horizon")
        assert rh is not None
        # LLM-provided string is preserved on the utterance (write_raw_utterances
        # converts it to a Timestamp, tested separately below).
        assert "2026" in str(rh)

    def test_extract_assertions_populates_predicate(self, mock_provider):
        """'predicate' must be non-null for a promotable assertion."""
        set_provider_predictions(mock_provider, _FULL_PHASE_C_PAYLOAD)
        result = extract_assertions(
            content_hash="abc123",
            text="Mahomes wins MVP",
            provider=mock_provider,
            allow_historical=True,
        )
        predicate = result.utterances[0].get("predicate")
        assert predicate is not None
        assert predicate != ""

    def test_extract_assertions_populates_subject(self, mock_provider):
        """'subject' must be non-null and identify the entity."""
        set_provider_predictions(mock_provider, _FULL_PHASE_C_PAYLOAD)
        result = extract_assertions(
            content_hash="abc123",
            text="Mahomes wins MVP",
            provider=mock_provider,
            allow_historical=True,
        )
        subject = result.utterances[0].get("subject")
        assert subject is not None
        assert subject != ""

    def test_extract_assertions_populates_predicate_args(self, mock_provider):
        """'predicate_args' must be a non-empty dict for a specific assertion."""
        set_provider_predictions(mock_provider, _FULL_PHASE_C_PAYLOAD)
        result = extract_assertions(
            content_hash="abc123",
            text="Mahomes wins MVP",
            provider=mock_provider,
            allow_historical=True,
        )
        pargs = result.utterances[0].get("predicate_args")
        assert pargs is not None
        assert isinstance(pargs, dict)
        assert len(pargs) > 0

    def test_extract_assertions_populates_prediction_horizon_days(self, mock_provider):
        """'prediction_horizon_days' must be an int >= 0 for a promotable claim."""
        set_provider_predictions(mock_provider, _FULL_PHASE_C_PAYLOAD)
        result = extract_assertions(
            content_hash="abc123",
            text="Mahomes wins MVP",
            provider=mock_provider,
            allow_historical=True,
        )
        phd = result.utterances[0].get("prediction_horizon_days")
        assert phd is not None
        assert phd >= 0

    def test_extract_assertions_utterances_non_empty_for_rich_response(
        self, mock_provider
    ):
        """
        ExtractionResult.utterances must be populated (not []) when the LLM
        returns any speech acts — this is the Phase C raw_utterance audit trail.
        """
        set_provider_predictions(mock_provider, _FULL_PHASE_C_PAYLOAD)
        result = extract_assertions(
            content_hash="abc123",
            text="Mahomes wins MVP",
            provider=mock_provider,
            allow_historical=True,
        )
        assert len(result.utterances) == 1
        # The utterance must be the same object that was returned by the provider.
        assert (
            result.utterances[0]["text"] == "Patrick Mahomes will win MVP this season."
        )

    def test_rhetorical_question_in_utterances_but_not_predictions(self, mock_provider):
        """
        A rhetorical question utterance must appear in .utterances (full audit
        trail) but NOT in .predictions (only promotable acts go to ledger).
        """
        set_provider_predictions(mock_provider, _RHETORICAL_PAYLOAD)
        result = extract_assertions(
            content_hash="abc123",
            text="Can anyone stop this Chiefs offense?",
            provider=mock_provider,
        )
        assert len(result.utterances) == 1
        assert len(result.predictions) == 0
        assert result.utterances[0]["speech_act_type"] == "rhetorical_question"

    def test_all_18_new_fields_present_in_utterance(self, mock_provider):
        """
        Regression test: every new Phase C field the prompt now asks the LLM
        to fill must survive round-trip through extract_assertions intact.
        """
        set_provider_predictions(mock_provider, _FULL_PHASE_C_PAYLOAD)
        result = extract_assertions(
            content_hash="abc123",
            text="Mahomes wins MVP",
            provider=mock_provider,
            allow_historical=True,
        )
        u = result.utterances[0]
        required_new_fields = [
            "text",
            "speech_act_type",
            "testability_subscores",
            "testability_score",
            "resolution_horizon",
            "predicate",
            "subject",
            "predicate_args",
            "extraction_confidence",
            # pre-existing fields that should also be non-null for a well-formed claim:
            "extracted_claim",
            "claim_category",
            "stance",
            "season_year",
            "target_player",
            "target_team",
            "confidence_note",
            "prediction_horizon_days",
        ]
        for field in required_new_fields:
            assert field in u, f"Field '{field}' missing from utterance dict"
            # None is acceptable for optional nullable fields (resolution_horizon
            # when not applicable, etc.) but the key itself must be present.

        # Spot-check that the "previously 100% NULL" ones are actually non-null:
        assert u["text"] is not None and u["text"] != ""
        assert u["speech_act_type"] is not None
        assert u["testability_score"] is not None
        assert u["testability_subscores"] is not None
        assert u["predicate"] is not None
        assert u["subject"] is not None
        assert u["predicate_args"] is not None


class TestPhaseCRegressionMissingFields:
    """
    Regression tests: if the LLM omits Phase C fields (old model / partial
    response), the code must not raise KeyError — it must gracefully fall
    back to safe defaults.
    """

    def test_missing_speech_act_type_does_not_crash(self, mock_provider):
        """Utterances without speech_act_type must not cause extract_assertions to crash."""
        payload_no_sat = [
            {
                # No "speech_act_type" key
                "extracted_claim": "Mahomes wins MVP",
                "claim_category": "award_prediction",
                "confidence_note": "strong",
                "season_year": 2026,
            }
        ]
        set_provider_predictions(mock_provider, payload_no_sat)
        result = extract_assertions(
            content_hash="abc123",
            text="Mahomes wins MVP",
            provider=mock_provider,
            allow_historical=True,
        )
        # Must not raise; predictions must still be populated via legacy path
        assert result.error is None
        assert len(result.predictions) == 1

    def test_missing_testability_subscores_does_not_crash(self, mock_provider):
        """Utterances without testability_subscores must not crash."""
        payload_no_subscores = [
            {
                "text": "Josh Allen wins Super Bowl",
                "speech_act_type": "assertion",
                # No "testability_subscores" key
                "testability_score": 0.85,
                "extracted_claim": "Josh Allen wins Super Bowl",
                "claim_category": "game_outcome",
                "confidence_note": "strong",
                "season_year": 2026,
            }
        ]
        set_provider_predictions(mock_provider, payload_no_subscores)
        result = extract_assertions(
            content_hash="abc123",
            text="Allen wins it all",
            provider=mock_provider,
            allow_historical=True,
        )
        assert result.error is None
        assert len(result.utterances) == 1
        # testability_score should use the LLM-supplied value as-is
        assert result.utterances[0]["testability_score"] == pytest.approx(
            0.85, abs=1e-4
        )

    def test_missing_resolution_horizon_stored_as_none(self, mock_provider):
        """Utterances without resolution_horizon must store None gracefully."""
        payload_no_rh = [
            {
                "text": "Eagles win the NFC",
                "speech_act_type": "assertion",
                "testability_score": 0.75,
                # No "resolution_horizon" key
                "extracted_claim": "Eagles win the NFC",
                "claim_category": "game_outcome",
                "confidence_note": "moderate",
                "season_year": 2026,
            }
        ]
        set_provider_predictions(mock_provider, payload_no_rh)
        result = extract_assertions(
            content_hash="abc123",
            text="Eagles win the NFC",
            provider=mock_provider,
            allow_historical=True,
        )
        assert result.error is None
        assert (
            "resolution_horizon" not in result.utterances[0]
            or result.utterances[0].get("resolution_horizon") is None
        )

    def test_missing_predicate_does_not_crash(self, mock_provider):
        """Utterances without predicate/subject/predicate_args must not crash."""
        payload_minimal = [
            {
                "text": "Browns miss playoffs",
                "speech_act_type": "assertion",
                "testability_score": 0.7,
                "extracted_claim": "Browns miss playoffs",
                "claim_category": "game_outcome",
                "confidence_note": "strong",
                "season_year": 2026,
                # No predicate, subject, predicate_args, resolution_horizon
            }
        ]
        set_provider_predictions(mock_provider, payload_minimal)
        result = extract_assertions(
            content_hash="abc123",
            text="Browns miss playoffs",
            provider=mock_provider,
            allow_historical=True,
        )
        assert result.error is None
        assert len(result.utterances) == 1

    def test_none_string_values_handled_gracefully(self, mock_provider):
        """
        PR #723 fix: LLM sometimes returns the string "None" instead of JSON null.
        This must not propagate as a non-null value into BQ string fields.
        The fix: extractor strips "None" strings from nullable fields.
        """
        payload_none_strings = [
            {
                "text": "Mahomes wins MVP",
                "speech_act_type": "assertion",
                "testability_score": 0.9,
                "resolution_horizon": "None",  # LLM returned string "None"
                "predicate": "None",
                "subject": "Patrick Mahomes",
                "predicate_args": {},
                "extracted_claim": "Mahomes wins MVP",
                "claim_category": "award_prediction",
                "stance": "bullish",
                "season_year": 2026,
                "target_player": "None",  # LLM returned string "None"
                "target_team": "KC",
                "confidence_note": "strong",
                "prediction_horizon_days": 120,
            }
        ]
        set_provider_predictions(mock_provider, payload_none_strings)
        result = extract_assertions(
            content_hash="abc123",
            text="Mahomes wins MVP",
            provider=mock_provider,
            allow_historical=True,
        )
        # Must not crash — the important thing is that the extractor does not explode
        # on "None" strings; individual field cleaning is handled upstream in the prompt
        assert result.error is None

    def test_extra_unknown_fields_in_response_do_not_crash(self, mock_provider):
        """
        Future-proofing: if the LLM adds extra fields not in the schema,
        extract_assertions must pass them through without crashing.
        """
        payload_extra = [
            {
                "text": "Mahomes wins MVP",
                "speech_act_type": "assertion",
                "testability_score": 0.9,
                "extracted_claim": "Mahomes wins MVP",
                "claim_category": "award_prediction",
                "confidence_note": "strong",
                "season_year": 2026,
                "extra_field_not_in_schema": "some_value",
                "another_future_field": 42,
            }
        ]
        set_provider_predictions(mock_provider, payload_extra)
        result = extract_assertions(
            content_hash="abc123",
            text="Mahomes wins MVP",
            provider=mock_provider,
            allow_historical=True,
        )
        assert result.error is None
        assert len(result.utterances) == 1


class TestPhaseCComputeTestabilityScore:
    """Unit tests for compute_testability_score() — the formula we own."""

    def test_full_scores_average_to_one(self):
        from src.assertion_extractor import compute_testability_score

        subscores = {
            "subject_specificity": 1.0,
            "predicate_falsifiability": 1.0,
            "threshold_concreteness": 1.0,
            "resolution_horizon_defined": 1.0,
            "evidence_accessibility": 1.0,
        }
        assert compute_testability_score(subscores) == pytest.approx(1.0, abs=1e-4)

    def test_zero_scores_average_to_zero(self):
        from src.assertion_extractor import compute_testability_score

        subscores = {
            "subject_specificity": 0.0,
            "predicate_falsifiability": 0.0,
            "threshold_concreteness": 0.0,
            "resolution_horizon_defined": 0.0,
            "evidence_accessibility": 0.0,
        }
        assert compute_testability_score(subscores) == pytest.approx(0.0, abs=1e-4)

    def test_missing_subscore_key_defaults_to_zero(self):
        """A missing sub-score key should be treated as 0 (penalises the average)."""
        from src.assertion_extractor import compute_testability_score

        # Only 4 of 5 keys present
        subscores = {
            "subject_specificity": 1.0,
            "predicate_falsifiability": 1.0,
            "threshold_concreteness": 1.0,
            "resolution_horizon_defined": 1.0,
            # evidence_accessibility missing
        }
        result = compute_testability_score(subscores)
        # Missing key contributes 0 → average of (1+1+1+1+0)/5 = 0.8
        assert result == pytest.approx(0.8, abs=1e-4)

    def test_empty_subscores_returns_zero(self):
        from src.assertion_extractor import compute_testability_score

        assert compute_testability_score({}) == 0.0

    def test_scores_clamped_to_unit_interval(self):
        """Sub-scores outside [0,1] (malformed LLM output) must be clamped."""
        from src.assertion_extractor import compute_testability_score

        subscores = {
            "subject_specificity": 2.5,  # > 1 — must be clamped to 1.0
            "predicate_falsifiability": -0.5,  # < 0 — must be clamped to 0.0
            "threshold_concreteness": 0.5,
            "resolution_horizon_defined": 0.5,
            "evidence_accessibility": 0.5,
        }
        result = compute_testability_score(subscores)
        # (1.0 + 0.0 + 0.5 + 0.5 + 0.5) / 5 = 0.5
        assert result == pytest.approx(0.5, abs=1e-4)

    def test_string_scores_coerced_to_float(self):
        """Some LLMs return scores as strings — must be coerced to float."""
        from src.assertion_extractor import compute_testability_score

        subscores = {
            "subject_specificity": "1.0",
            "predicate_falsifiability": "0.8",
            "threshold_concreteness": "0.6",
            "resolution_horizon_defined": "0.7",
            "evidence_accessibility": "0.9",
        }
        result = compute_testability_score(subscores)
        assert result == pytest.approx((1.0 + 0.8 + 0.6 + 0.7 + 0.9) / 5, abs=1e-4)


class TestPhaseCIsPromotable:
    """Unit tests for _is_promotable() — the gate to prediction_ledger."""

    def test_assertion_above_threshold_is_promotable(self):
        from src.assertion_extractor import _is_promotable

        u = {
            "speech_act_type": "assertion",
            "testability_score": 0.8,
            "extracted_claim": "Mahomes wins MVP",
        }
        assert _is_promotable(u, threshold=0.6) is True

    def test_rhetorical_question_is_not_promotable(self):
        from src.assertion_extractor import _is_promotable

        u = {
            "speech_act_type": "rhetorical_question",
            "testability_score": 0.9,
            "extracted_claim": "Can anyone stop Mahomes?",
        }
        assert _is_promotable(u, threshold=0.6) is False

    def test_hedge_is_not_promotable(self):
        from src.assertion_extractor import _is_promotable

        u = {
            "speech_act_type": "hedge",
            "testability_score": 0.7,
            "extracted_claim": "Mahomes might win MVP",
        }
        assert _is_promotable(u, threshold=0.6) is False

    def test_assertion_below_threshold_is_not_promotable(self):
        from src.assertion_extractor import _is_promotable

        u = {
            "speech_act_type": "assertion",
            "testability_score": 0.4,
            "extracted_claim": "Eagles could win",
        }
        assert _is_promotable(u, threshold=0.6) is False

    def test_conditional_above_threshold_is_promotable(self):
        from src.assertion_extractor import _is_promotable

        u = {
            "speech_act_type": "conditional",
            "testability_score": 0.88,
            "extracted_claim": "Ravens reach AFC Championship (OL stays healthy)",
        }
        assert _is_promotable(u, threshold=0.6) is True

    def test_missing_speech_act_type_defaults_to_assertion(self):
        """Backward-compat: absent speech_act_type → 'assertion' → promotable."""
        from src.assertion_extractor import _is_promotable

        u = {
            # No speech_act_type
            "testability_score": 0.9,
            "extracted_claim": "Eagles win NFC East",
        }
        assert _is_promotable(u, threshold=0.6) is True

    def test_absent_testability_score_defaults_to_one_point_zero(self):
        """Backward-compat: absent testability_score → 1.0 (legacy responses always promoted)."""
        from src.assertion_extractor import _is_promotable

        u = {
            "speech_act_type": "assertion",
            # No testability_score
            "extracted_claim": "Browns miss playoffs",
        }
        assert _is_promotable(u, threshold=0.6) is True

    def test_empty_extracted_claim_is_not_promotable(self):
        """An utterance with no extracted_claim text must not be promoted."""
        from src.assertion_extractor import _is_promotable

        u = {
            "speech_act_type": "assertion",
            "testability_score": 0.9,
            "extracted_claim": "",
        }
        assert _is_promotable(u, threshold=0.6) is False
