"""
Tests for metadata completeness fixes — Issue (extraction metadata quality).

Covers:
  1. extract_assertions always returns complete metadata (defaults applied).
  2. write_raw_utterances uses defaults when LLM omits fields.
  3. infer_resolution_horizon for common temporal patterns.
  4. backfill_metadata script logic (unit tests, no BQ).
"""

import calendar
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.assertion_extractor import (
    DEFAULT_CLAIM_CATEGORY,
    DEFAULT_TESTABILITY_SCORE,
    ExtractionResult,
    infer_resolution_horizon,
    write_raw_utterances,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_db_for_bq_write():
    """Build a mock DBManager whose BQ load path succeeds."""
    db = MagicMock()
    mock_job = MagicMock()
    mock_job.result.return_value = None
    db.client.load_table_from_dataframe.return_value = mock_job
    return db


def _write_utterance(utterance: dict, uttered_at=None) -> dict:
    """Write a single utterance and return the captured BQ row dict."""
    os.environ.setdefault("GCP_PROJECT_ID", "test-project")
    db = _make_mock_db_for_bq_write()
    write_raw_utterances(
        utterances=[utterance],
        source_doc_id="doc_test",
        speaker_entity_id="entity_test",
        uttered_at=uttered_at or datetime(2025, 9, 1, tzinfo=timezone.utc),
        domain="nfl",
        db=db,
    )
    call_args = db.client.load_table_from_dataframe.call_args
    df = call_args[0][0]
    rows = df.to_dict(orient="records")
    assert len(rows) == 1
    return rows[0]


_FULL_UTTERANCE = {
    "text": "Mahomes will win MVP this season",
    "speech_act_type": "assertion",
    "testability_score": 0.9,
    "extraction_confidence": 0.85,
    "resolution_horizon": "2026-12-31T23:59:59Z",
    "claim_category": "player_performance",
    "stance": "bullish",
}


# ---------------------------------------------------------------------------
# Test class: infer_resolution_horizon patterns
# ---------------------------------------------------------------------------


class TestInferResolutionHorizon:
    """
    Verify the rule-based resolution_horizon inferencer handles common
    temporal patterns from pundit claims.
    """

    def _assert_date(self, text, year=None, month=None, day=None):
        """Helper: assert inferred timestamp has expected year/month/day."""
        result = infer_resolution_horizon(text)
        assert result is not None, f"Expected non-None for: {text!r}"
        from datetime import datetime

        dt = datetime.fromisoformat(result.replace("Z", "+00:00"))
        if year is not None:
            assert dt.year == year, f"Expected year {year}, got {dt.year} for: {text!r}"
        if month is not None:
            assert dt.month == month, (
                f"Expected month {month}, got {dt.month} for: {text!r}"
            )
        if day is not None:
            assert dt.day == day, f"Expected day {day}, got {dt.day} for: {text!r}"

    def test_this_season_returns_current_year_dec31(self):
        """'this season' → December 31 of the current year."""
        now = datetime.now()
        result = infer_resolution_horizon("He will win MVP this season")
        assert result is not None
        dt = datetime.fromisoformat(result.replace("Z", "+00:00"))
        assert dt.year == now.year
        assert dt.month == 12
        assert dt.day == 31

    def test_next_season_returns_next_year_dec31(self):
        """'next season' → December 31 of next year."""
        now = datetime.now()
        result = infer_resolution_horizon("She will sign next season")
        assert result is not None
        dt = datetime.fromisoformat(result.replace("Z", "+00:00"))
        assert dt.year == now.year + 1
        assert dt.month == 12

    def test_before_the_draft_returns_april30(self):
        """'before the draft' → April 30 of current/next year."""
        result = infer_resolution_horizon("He will be traded before the draft")
        assert result is not None
        dt = datetime.fromisoformat(result.replace("Z", "+00:00"))
        assert dt.month == 4
        assert dt.day == 30

    def test_nfl_draft_returns_april30(self):
        """'NFL Draft' → April 30."""
        result = infer_resolution_horizon("The team will address this in the NFL Draft")
        assert result is not None
        dt = datetime.fromisoformat(result.replace("Z", "+00:00"))
        assert dt.month == 4

    def test_week_10_returns_approx_nov(self):
        """'by Week 10' → approximately week 10 of NFL season (November)."""
        result = infer_resolution_horizon("He will be the starter by Week 10")
        assert result is not None
        dt = datetime.fromisoformat(result.replace("Z", "+00:00"))
        # Week 10 of an NFL season starting in September falls in November
        # (Sep 5 + 10 weeks ≈ Nov 14)
        assert dt.month in (10, 11, 12), f"Expected November-ish, got month={dt.month}"

    def test_week_1_returns_september(self):
        """'Week 1' → approximately September of NFL season."""
        uttered = datetime(2025, 7, 1, tzinfo=timezone.utc)
        result = infer_resolution_horizon("He will start in Week 1", uttered_at=uttered)
        assert result is not None
        dt = datetime.fromisoformat(result.replace("Z", "+00:00"))
        assert dt.month == 9

    def test_before_training_camp_returns_july31(self):
        """'before training camp' → July 31."""
        result = infer_resolution_horizon("He will be cut before training camp")
        assert result is not None
        dt = datetime.fromisoformat(result.replace("Z", "+00:00"))
        assert dt.month == 7
        assert dt.day == 31

    def test_offseason_returns_july31(self):
        """'this offseason' → July 31."""
        result = infer_resolution_horizon("He will sign this offseason")
        assert result is not None
        dt = datetime.fromisoformat(result.replace("Z", "+00:00"))
        assert dt.month == 7

    def test_playoffs_returns_january15(self):
        """'make the playoffs' → January 15 of playoffs resolution year."""
        result = infer_resolution_horizon("The Eagles will make the playoffs")
        assert result is not None
        dt = datetime.fromisoformat(result.replace("Z", "+00:00"))
        assert dt.month == 1
        assert dt.day == 15

    def test_super_bowl_returns_february10(self):
        """'Super Bowl' → February 10 of next year (game occurs ~Feb)."""
        result = infer_resolution_horizon("The Chiefs will win the Super Bowl")
        assert result is not None
        dt = datetime.fromisoformat(result.replace("Z", "+00:00"))
        assert dt.month == 2
        assert dt.day == 10

    def test_ever_returns_none(self):
        """'ever' → None (unresolvable lifetime claim)."""
        result = infer_resolution_horizon("He will never win a Super Bowl")
        assert result is None

    def test_career_returns_none(self):
        """'career' → None (unresolvable career-span claim)."""
        result = infer_resolution_horizon("He has the best career stats ever")
        assert result is None

    def test_before_retiring_returns_none(self):
        """'before he retires' → None (unresolvable retirement horizon)."""
        result = infer_resolution_horizon(
            "Mahomes will win 4 Super Bowls before he retires"
        )
        assert result is None

    def test_empty_text_returns_none(self):
        """Empty text → None."""
        assert infer_resolution_horizon("") is None
        assert infer_resolution_horizon(None) is None

    def test_no_pattern_returns_none(self):
        """Text with no recognizable temporal pattern → None."""
        result = infer_resolution_horizon("He is a great quarterback")
        assert result is None

    def test_by_june_returns_june_last_day(self):
        """'by June' → June 30 of appropriate year."""
        result = infer_resolution_horizon("He will be cut by June")
        assert result is not None
        dt = datetime.fromisoformat(result.replace("Z", "+00:00"))
        assert dt.month == 6
        assert dt.day == 30  # June has 30 days

    def test_by_april_returns_april30(self):
        """'by April' → April 30."""
        result = infer_resolution_horizon("The deal will be done by April")
        assert result is not None
        dt = datetime.fromisoformat(result.replace("Z", "+00:00"))
        assert dt.month == 4
        assert dt.day == 30


# ---------------------------------------------------------------------------
# Test class: write_raw_utterances with missing LLM fields
# ---------------------------------------------------------------------------


class TestWriteRawUtterancesDefaults:
    """
    When LLM omits metadata fields, write_raw_utterances must apply defaults.
    """

    def test_full_metadata_passes_through_unchanged(self):
        """Complete LLM output → all fields preserved."""
        row = _write_utterance(_FULL_UTTERANCE)
        assert row["speech_act_type"] == "assertion"
        assert float(row["testability_score"]) == pytest.approx(0.9)
        assert float(row["extraction_confidence"]) == pytest.approx(0.85)

    def test_missing_speech_act_type_defaults_to_assertion(self):
        """No speech_act_type in LLM output → defaults to 'assertion'."""
        u = {k: v for k, v in _FULL_UTTERANCE.items() if k != "speech_act_type"}
        row = _write_utterance(u)
        assert row["speech_act_type"] == "assertion"

    def test_invalid_speech_act_type_becomes_commentary(self):
        """Invalid speech_act_type (not in VALID_SPEECH_ACT_TYPES) → 'commentary'."""
        u = {**_FULL_UTTERANCE, "speech_act_type": "gibberish"}
        row = _write_utterance(u)
        assert row["speech_act_type"] == "commentary"

    def test_missing_testability_score_with_subscores_computed(self):
        """When subscores are present, score is recomputed from them."""
        u = {
            **_FULL_UTTERANCE,
            "testability_subscores": {
                "subject_specificity": 1.0,
                "predicate_falsifiability": 1.0,
                "threshold_concreteness": 1.0,
                "resolution_horizon_defined": 1.0,
                "evidence_accessibility": 1.0,
            },
            "testability_score": None,  # LLM omitted
        }
        row = _write_utterance(u)
        assert float(row["testability_score"]) == pytest.approx(1.0)

    def test_extraction_confidence_defaults_to_testability_score(self):
        """Missing extraction_confidence defaults to testability_score value."""
        u = {k: v for k, v in _FULL_UTTERANCE.items() if k != "extraction_confidence"}
        u["testability_score"] = 0.75
        row = _write_utterance(u)
        # extraction_confidence should fall back to testability_score
        assert float(row["extraction_confidence"]) == pytest.approx(0.75)

    def test_resolution_horizon_inferred_when_missing_this_season(self):
        """LLM omits resolution_horizon + 'this season' in text → inferred.

        The uttered_at is 2025-09-01, so 'this season' infers to 2025-12-31.
        """
        uttered = datetime(2025, 9, 1, tzinfo=timezone.utc)
        u = {
            "text": "Mahomes will win MVP this season",
            "speech_act_type": "assertion",
            "testability_score": 0.9,
            "extraction_confidence": 0.9,
            "resolution_horizon": None,
        }
        row = _write_utterance(u, uttered_at=uttered)
        rh = row["resolution_horizon"]
        # Should have been inferred — not NaT
        import pandas as pd

        assert rh is not pd.NaT, "Expected inferred resolution_horizon, got NaT"
        assert hasattr(rh, "year"), "Expected pd.Timestamp"
        # "this season" with uttered_at=2025-09-01 → 2025 season → Dec 31 2025
        assert rh.year == 2025
        assert rh.month == 12
        assert rh.day == 31

    def test_resolution_horizon_inferred_playoffs(self):
        """'make the playoffs' → inferred January 15 timestamp."""
        u = {
            "text": "The Eagles will make the playoffs this year",
            "speech_act_type": "assertion",
            "testability_score": 0.85,
            "extraction_confidence": 0.85,
            "resolution_horizon": None,
        }
        row = _write_utterance(u)
        rh = row["resolution_horizon"]
        import pandas as pd

        assert rh is not pd.NaT
        assert rh.month == 1 and rh.day == 15

    def test_resolution_horizon_not_overwritten_when_set(self):
        """LLM provides resolution_horizon → must NOT be overwritten by inference."""
        u = {
            "text": "Mahomes will win MVP this season",
            "speech_act_type": "assertion",
            "testability_score": 0.9,
            "extraction_confidence": 0.9,
            "resolution_horizon": "2026-06-15T00:00:00Z",
        }
        row = _write_utterance(u)
        rh = row["resolution_horizon"]
        import pandas as pd

        assert isinstance(rh, pd.Timestamp)
        assert rh.year == 2026
        assert rh.month == 6
        assert rh.day == 15

    def test_not_null_invariant_still_enforced(self):
        """Rows with truly irresolvable NULLs in NOT-NULL cols raise ValueError."""
        # Manually craft a row that would have a NULL in a NOT-NULL column
        # by bypassing the defaults (e.g., domain=None)
        u = {
            "text": "Some claim",
            "speech_act_type": "assertion",
            "testability_score": 0.5,
            "extraction_confidence": 0.5,
        }
        # write_raw_utterances takes domain as a parameter — pass None-like
        # This should raise ValueError due to the NOT-NULL invariant
        os.environ.setdefault("GCP_PROJECT_ID", "test-project")
        db = _make_mock_db_for_bq_write()
        with pytest.raises(ValueError, match="NOT NULL invariant"):
            write_raw_utterances(
                utterances=[u],
                source_doc_id="doc_test",
                speaker_entity_id="entity_test",
                uttered_at=datetime(2025, 9, 1, tzinfo=timezone.utc),
                domain=None,  # This triggers the NOT-NULL check
                db=db,
            )


# ---------------------------------------------------------------------------
# Test class: extract_assertions metadata defaults
# ---------------------------------------------------------------------------


class TestExtractAssertionsMetadataDefaults:
    """
    extract_assertions must apply defaults BEFORE returning predictions,
    so callers always get complete metadata.
    """

    def _make_provider(self, utterances: list):
        """Create a mock LLM provider returning given utterances."""
        provider = MagicMock()
        provider.model = "mock-model"
        provider.extract_predictions.return_value = utterances
        return provider

    def test_missing_speech_act_type_defaulted_in_extract_assertions(self):
        """LLM returns utterance without speech_act_type → defaulted to 'assertion'."""
        from src.assertion_extractor import extract_assertions

        utterances = [
            {
                "extracted_claim": "Mahomes wins MVP in 2026",
                "claim_category": "player_performance",
                "season_year": 2026,
                # No speech_act_type
            }
        ]
        provider = self._make_provider(utterances)
        result = extract_assertions("hash1", "some text", provider=provider)
        # The prediction should be promoted (defaults to assertion + 1.0 testability)
        assert len(result.utterances) == 1
        assert result.utterances[0].get("speech_act_type") == "assertion"

    def test_missing_claim_category_defaulted_to_general(self):
        """LLM returns utterance without claim_category → defaulted to 'general'."""
        from src.assertion_extractor import extract_assertions

        utterances = [
            {
                "extracted_claim": "Mahomes wins MVP in 2026",
                "speech_act_type": "assertion",
                "testability_score": 0.9,
                "season_year": 2026,
                # No claim_category
            }
        ]
        provider = self._make_provider(utterances)
        result = extract_assertions("hash2", "some text", provider=provider)
        assert len(result.utterances) == 1
        assert result.utterances[0].get("claim_category") == DEFAULT_CLAIM_CATEGORY

    def test_unparseable_testability_score_defaulted(self):
        """LLM returns non-numeric testability_score → DEFAULT_TESTABILITY_SCORE.

        write_raw_utterances must apply DEFAULT_TESTABILITY_SCORE when the LLM
        returns a non-parseable value like "HIGH" instead of a float.
        """
        from src.assertion_extractor import write_raw_utterances

        # Simulate utterance dict as it comes back from the LLM (non-numeric score)
        utterances = [
            {
                "text": "Mahomes wins MVP",
                "speech_act_type": "assertion",
                "testability_score": "HIGH",  # Non-numeric — should default
                "claim_category": "player_performance",
            }
        ]
        os.environ.setdefault("GCP_PROJECT_ID", "test-project")
        db = _make_mock_db_for_bq_write()
        write_raw_utterances(
            utterances=utterances,
            source_doc_id="doc3",
            speaker_entity_id="e3",
            uttered_at=datetime(2025, 9, 1, tzinfo=timezone.utc),
            domain="nfl",
            db=db,
        )
        call_args = db.client.load_table_from_dataframe.call_args
        rows = call_args[0][0].to_dict(orient="records")
        assert len(rows) == 1
        assert float(rows[0]["testability_score"]) == pytest.approx(
            DEFAULT_TESTABILITY_SCORE
        )

    def test_claim_category_in_pundit_prediction_defaults_general(self):
        """run_extraction: pred with no claim_category gets 'general' in PunditPrediction."""
        from src.assertion_extractor import run_extraction
        from src.cryptographic_ledger import PunditPrediction

        # Build a minimal media df
        media_df = pd.DataFrame(
            [
                {
                    "content_hash": "hash_cc",
                    "source_id": "espn_nfl",
                    "title": "Test Article",
                    "raw_text": (
                        "Patrick Mahomes will win the MVP award this season. "
                        "He has been absolutely outstanding all year and the Kansas City Chiefs look like "
                        "they will go all the way to the Super Bowl. The Chiefs offense is completely unstoppable "
                        "and their defense has really stepped up in recent weeks to become elite. "
                        "Their offensive line is much improved from last season too and Mahomes is the best."
                    ),
                    "source_url": "https://espn.com/test",
                    "author": "Test Author",
                    "matched_pundit_id": "test_pundit",
                    "matched_pundit_name": "Test Pundit",
                    "published_at": datetime(2025, 9, 1, tzinfo=timezone.utc),
                    "sport": "NFL",
                }
            ]
        )

        prediction_no_category = {
            "extracted_claim": "Mahomes wins MVP",
            "speech_act_type": "assertion",
            "testability_score": 0.9,
            "season_year": 2026,
            # claim_category intentionally missing
        }

        ingested_predictions = []

        def mock_ingest(predictions, db=None):
            ingested_predictions.extend(predictions)
            return ["hash_x"]

        with (
            patch(
                "src.assertion_extractor.get_unprocessed_media", return_value=media_df
            ),
            patch("src.assertion_extractor.extract_assertions") as mock_extract,
            patch("src.assertion_extractor.ingest_batch", side_effect=mock_ingest),
            patch("src.assertion_extractor.write_raw_utterances", return_value=(1, {})),
            patch("src.assertion_extractor._write_extraction_run"),
        ):
            mock_extract.return_value = ExtractionResult(
                content_hash="hash_cc",
                predictions=[prediction_no_category],
                utterances=[prediction_no_category],
            )

            db = MagicMock()
            db.fetch_df.return_value = pd.DataFrame()
            db.append_dataframe_to_table.return_value = None

            provider = MagicMock()
            provider.model = "mock"

            run_extraction(limit=1, db=db, provider=provider, disable_triage=True)

        assert len(ingested_predictions) == 1
        pred = ingested_predictions[0]
        assert isinstance(pred, PunditPrediction)
        assert pred.claim_category == DEFAULT_CLAIM_CATEGORY, (
            f"Expected claim_category='{DEFAULT_CLAIM_CATEGORY}', got {pred.claim_category!r}"
        )


# ---------------------------------------------------------------------------
# Test class: backfill_metadata script
# ---------------------------------------------------------------------------


class TestBackfillMetadata:
    """Unit tests for the backfill_metadata.py script logic (no real BQ)."""

    def _make_db(self, rows=None):
        """Build a mock DBManager for backfill tests."""
        db = MagicMock()
        df = pd.DataFrame(rows or [])
        db.fetch_df.return_value = df
        mock_result = MagicMock()
        mock_result.job.num_dml_affected_rows = len(rows) if rows else 0
        db.execute.return_value = mock_result
        return db

    def test_dry_run_returns_zero_rows_updated(self, monkeypatch):
        """dry_run=True must not call db.execute."""
        monkeypatch.setenv("GCP_PROJECT_ID", "test-project")
        from scripts.backfill_metadata import backfill_raw_utterance

        db = self._make_db(
            [
                {
                    "utterance_id": "u1",
                    "text": "Mahomes wins MVP this season",
                    "resolution_condition": None,
                    "uttered_at": datetime(2025, 9, 1),
                    "speech_act_type": None,
                    "testability_score": None,
                    "extraction_confidence": None,
                    "resolution_horizon": None,
                }
            ]
        )

        result = backfill_raw_utterance(db, limit=100, dry_run=True)
        assert result["rows_updated"] == 0
        db.execute.assert_not_called()

    def test_no_nulls_returns_empty_result(self, monkeypatch):
        """When table has no NULL metadata, backfill returns rows_updated=0."""
        monkeypatch.setenv("GCP_PROJECT_ID", "test-project")
        from scripts.backfill_metadata import backfill_raw_utterance

        db = self._make_db([])  # empty dataframe — no NULLs found
        result = backfill_raw_utterance(db, limit=100)
        assert result["rows_scanned"] == 0
        assert result["rows_updated"] == 0

    def test_resolution_horizon_filled_from_text(self, monkeypatch):
        """Rows with NULL resolution_horizon get inferred values from text."""
        monkeypatch.setenv("GCP_PROJECT_ID", "test-project")
        from scripts.backfill_metadata import backfill_raw_utterance

        db = self._make_db(
            [
                {
                    "utterance_id": "u2",
                    "text": "The team will make the playoffs this season",
                    "resolution_condition": None,
                    "uttered_at": datetime(2025, 9, 1),
                    "speech_act_type": "assertion",
                    "testability_score": 0.8,
                    "extraction_confidence": 0.8,
                    "resolution_horizon": None,  # NULL — to be inferred
                }
            ]
        )

        result = backfill_raw_utterance(
            db, limit=100, dry_run=True
        )  # dry to avoid MERGE
        # The count should reflect 1 inferred resolution_horizon
        assert result["resolution_horizon_filled"] == 1

    def test_speech_act_type_filled_with_default(self, monkeypatch):
        """Rows with NULL speech_act_type get 'assertion' default."""
        monkeypatch.setenv("GCP_PROJECT_ID", "test-project")
        from scripts.backfill_metadata import backfill_raw_utterance

        db = self._make_db(
            [
                {
                    "utterance_id": "u3",
                    "text": "Some claim",
                    "resolution_condition": None,
                    "uttered_at": datetime(2025, 9, 1),
                    "speech_act_type": None,
                    "testability_score": 0.7,
                    "extraction_confidence": 0.7,
                    "resolution_horizon": pd.Timestamp("2025-12-31"),
                }
            ]
        )

        result = backfill_raw_utterance(db, limit=100, dry_run=True)
        assert result["speech_act_type_filled"] == 1

    def test_testability_score_filled_with_default(self, monkeypatch):
        """Rows with NULL testability_score get DEFAULT_TESTABILITY_SCORE (0.5)."""
        monkeypatch.setenv("GCP_PROJECT_ID", "test-project")
        from scripts.backfill_metadata import backfill_raw_utterance

        db = self._make_db(
            [
                {
                    "utterance_id": "u4",
                    "text": "Some claim",
                    "resolution_condition": None,
                    "uttered_at": datetime(2025, 9, 1),
                    "speech_act_type": "assertion",
                    "testability_score": None,
                    "extraction_confidence": 0.5,
                    "resolution_horizon": pd.Timestamp("2025-12-31"),
                }
            ]
        )

        result = backfill_raw_utterance(db, limit=100, dry_run=True)
        assert result["testability_score_filled"] == 1

    def test_prediction_ledger_dry_run(self, monkeypatch):
        """prediction_ledger backfill dry run does not call execute."""
        monkeypatch.setenv("GCP_PROJECT_ID", "test-project")
        from scripts.backfill_metadata import backfill_prediction_ledger

        db = self._make_db(
            [
                {
                    "prediction_hash": "ph1",
                    "claim_category": None,
                }
            ]
        )

        result = backfill_prediction_ledger(db, limit=100, dry_run=True)
        assert result["rows_updated"] == 0
        assert result["claim_category_filled"] == 1
        db.execute.assert_not_called()

    def test_prediction_ledger_no_nulls(self, monkeypatch):
        """prediction_ledger backfill with no NULL rows returns 0."""
        monkeypatch.setenv("GCP_PROJECT_ID", "test-project")
        from scripts.backfill_metadata import backfill_prediction_ledger

        db = self._make_db([])
        result = backfill_prediction_ledger(db, limit=100)
        assert result["rows_updated"] == 0
