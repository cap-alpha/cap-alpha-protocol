"""
Tests for the NLP Assertion Extraction Pipeline (Issue #79).
Unit tests — no Gemini API or BigQuery required.
"""

import json
import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.assertion_extractor import (
    VALID_CATEGORIES,
    ExtractionResult,
    extract_assertions,
    get_unprocessed_media,
    mark_as_processed,
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
def mock_gemini_client():
    client = MagicMock()
    return client


def make_gemini_response(predictions_json: list) -> MagicMock:
    """Build a mock Gemini response."""
    resp = MagicMock()
    resp.text = json.dumps(predictions_json)
    return resp


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
    def test_returns_parsed_predictions(self, mock_gemini_client):
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
        mock_gemini_client.models.generate_content.return_value = make_gemini_response(
            predictions
        )

        result = extract_assertions(
            content_hash="abc123",
            text="Mahomes will win MVP this year",
            client=mock_gemini_client,
        )

        assert len(result.predictions) == 1
        assert (
            result.predictions[0]["extracted_claim"]
            == "Patrick Mahomes will win MVP in 2025"
        )
        assert result.predictions[0]["claim_category"] == "player_performance"
        assert result.error is None

    def test_handles_empty_array_response(self, mock_gemini_client):
        mock_gemini_client.models.generate_content.return_value = make_gemini_response(
            []
        )

        result = extract_assertions(
            content_hash="abc123",
            text="Just a recap of last week's games",
            client=mock_gemini_client,
        )

        assert len(result.predictions) == 0
        assert result.error is None

    def test_handles_clean_json_array(self, mock_gemini_client):
        """Structured output returns clean JSON — no fence stripping needed."""
        predictions = [
            {
                "extracted_claim": "Josh Allen wins Super Bowl",
                "claim_category": "game_outcome",
                "confidence_note": "strong",
            }
        ]
        resp = MagicMock()
        resp.text = json.dumps(predictions)
        mock_gemini_client.models.generate_content.return_value = resp

        result = extract_assertions(
            content_hash="abc123",
            text="Allen is going all the way",
            client=mock_gemini_client,
        )

        assert len(result.predictions) == 1
        assert result.predictions[0]["extracted_claim"] == "Josh Allen wins Super Bowl"

    def test_handles_invalid_json(self, mock_gemini_client):
        resp = MagicMock()
        resp.text = "This is not JSON at all"
        mock_gemini_client.models.generate_content.return_value = resp

        result = extract_assertions(
            content_hash="abc123",
            text="Some text",
            client=mock_gemini_client,
        )

        assert len(result.predictions) == 0
        assert result.error is not None

    def test_handles_non_array_json(self, mock_gemini_client):
        """Schema prevents this in production; error is surfaced gracefully."""
        resp = MagicMock()
        resp.text = json.dumps({"not": "an array"})
        mock_gemini_client.models.generate_content.return_value = resp

        result = extract_assertions(
            content_hash="abc123",
            text="Some text",
            client=mock_gemini_client,
        )

        assert len(result.predictions) == 0
        assert result.error is not None

    def test_handles_api_error(self, mock_gemini_client):
        mock_gemini_client.models.generate_content.side_effect = Exception(
            "API quota exceeded"
        )

        result = extract_assertions(
            content_hash="abc123",
            text="Some text",
            client=mock_gemini_client,
        )

        assert len(result.predictions) == 0
        assert "API quota exceeded" in result.error

    def test_schema_enforces_valid_categories(self, mock_gemini_client):
        """response_schema enum prevents invalid categories at the model level.
        In production the model can only output VALID_CATEGORIES values."""
        from src.assertion_extractor import VALID_CATEGORIES, _PREDICTION_SCHEMA
        from google.genai import types

        # The schema's enum field lists exactly the valid categories
        enum_values = set(_PREDICTION_SCHEMA.items.properties["claim_category"].enum)
        assert enum_values == VALID_CATEGORIES

    def test_skips_predictions_without_claim(self, mock_gemini_client):
        predictions = [
            {"extracted_claim": "", "claim_category": "trade"},
            {
                "extracted_claim": "Valid claim here",
                "claim_category": "trade",
            },
        ]
        mock_gemini_client.models.generate_content.return_value = make_gemini_response(
            predictions
        )

        result = extract_assertions(
            content_hash="abc123",
            text="Some text",
            client=mock_gemini_client,
        )

        assert len(result.predictions) == 1

    def test_truncates_long_text(self, mock_gemini_client):
        mock_gemini_client.models.generate_content.return_value = make_gemini_response(
            []
        )

        long_text = "x" * 10000
        extract_assertions(
            content_hash="abc123",
            text=long_text,
            client=mock_gemini_client,
        )

        call_args = mock_gemini_client.models.generate_content.call_args
        prompt_text = call_args[1]["contents"]
        # Text should be truncated to 4000 chars
        assert len(prompt_text) < len(long_text) + 1000


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

    def test_falls_back_on_missing_tracking_table(self, mock_db):
        mock_db.fetch_df.side_effect = [
            Exception("Table not found"),
            make_raw_media_df(2),
        ]
        df = get_unprocessed_media(mock_db)
        assert len(df) == 2
        assert mock_db.fetch_df.call_count == 2


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
# run_extraction (integration of all components)
# ---------------------------------------------------------------------------


class TestRunExtraction:
    @patch("src.assertion_extractor.ingest_batch")
    @patch("src.assertion_extractor.extract_assertions")
    def test_full_pipeline(self, mock_extract, mock_ingest, mock_db):
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

        summary = run_extraction(limit=10, db=mock_db, gemini_client=MagicMock())

        assert summary["total_processed"] == 1
        assert summary["predictions_extracted"] == 1
        assert summary["predictions_ingested"] == 1
        assert summary["errors"] == 0

    @patch("src.assertion_extractor.extract_assertions")
    def test_handles_extraction_errors(self, mock_extract, mock_db):
        mock_db.fetch_df.return_value = make_raw_media_df(1)
        mock_extract.return_value = ExtractionResult(
            content_hash="hash_0",
            predictions=[],
            error="Gemini quota exceeded",
        )

        summary = run_extraction(limit=10, db=mock_db, gemini_client=MagicMock())

        assert summary["errors"] == 1
        assert summary["predictions_extracted"] == 0

    @patch("src.assertion_extractor.extract_assertions")
    def test_counts_no_predictions(self, mock_extract, mock_db):
        mock_db.fetch_df.return_value = make_raw_media_df(1)
        mock_extract.return_value = ExtractionResult(
            content_hash="hash_0",
            predictions=[],
        )

        summary = run_extraction(limit=10, db=mock_db, gemini_client=MagicMock())

        assert summary["skipped_no_predictions"] == 1

    def test_dry_run_skips_gemini(self, mock_db):
        mock_db.fetch_df.return_value = make_raw_media_df(2)

        summary = run_extraction(limit=10, dry_run=True, db=mock_db)

        assert summary["total_processed"] == 2
        assert summary["predictions_extracted"] == 0
        mock_db.append_dataframe_to_table.assert_not_called()

    def test_no_work_when_empty(self, mock_db):
        mock_db.fetch_df.return_value = pd.DataFrame()

        summary = run_extraction(limit=10, db=mock_db)

        assert summary["total_processed"] == 0


# ---------------------------------------------------------------------------
# Constants validation
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
