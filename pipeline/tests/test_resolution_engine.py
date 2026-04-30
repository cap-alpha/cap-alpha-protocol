"""
Tests for the Prediction Resolution Engine (Issue #112).
Unit tests only — no BigQuery required.
"""

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.resolution_engine import (
    ResolutionResult,
    _compute_brier_score,
    _compute_timeliness_weight,
    _compute_weighted_score,
    get_pending_predictions,
    get_pundit_accuracy_summary,
    record_resolution,
    resolve_binary,
    resolve_manual,
    resolve_probabilistic,
    void_prediction,
)

FAKE_HASH = "a" * 64


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.fetch_df.return_value = pd.DataFrame()
    return db


# ---------------------------------------------------------------------------
# Timeliness weight
# ---------------------------------------------------------------------------


class TestTimelinessWeight:
    def test_baseline_for_same_day(self):
        ts = datetime(2025, 9, 1, tzinfo=timezone.utc)
        assert _compute_timeliness_weight(ts, ts) == 1.0

    def test_baseline_when_outcome_before_prediction(self):
        pred = datetime(2025, 9, 5, tzinfo=timezone.utc)
        outcome = datetime(2025, 9, 1, tzinfo=timezone.utc)
        assert _compute_timeliness_weight(pred, outcome) == 1.0

    def test_one_week_out(self):
        pred = datetime(2025, 9, 1, tzinfo=timezone.utc)
        outcome = pred + timedelta(days=10)
        assert _compute_timeliness_weight(pred, outcome) == 1.1

    def test_one_month_out(self):
        pred = datetime(2025, 9, 1, tzinfo=timezone.utc)
        outcome = pred + timedelta(days=35)
        assert _compute_timeliness_weight(pred, outcome) == 1.25

    def test_three_months_out(self):
        pred = datetime(2025, 9, 1, tzinfo=timezone.utc)
        outcome = pred + timedelta(days=100)
        assert _compute_timeliness_weight(pred, outcome) == 1.5

    def test_one_year_out(self):
        pred = datetime(2025, 9, 1, tzinfo=timezone.utc)
        outcome = pred + timedelta(days=400)
        assert _compute_timeliness_weight(pred, outcome) == 2.0


# ---------------------------------------------------------------------------
# Brier score
# ---------------------------------------------------------------------------


class TestBrierScore:
    def test_perfect_correct_prediction(self):
        assert _compute_brier_score(1.0, True) == 0.0

    def test_perfect_incorrect_prediction(self):
        assert _compute_brier_score(0.0, False) == 0.0

    def test_worst_case(self):
        assert _compute_brier_score(1.0, False) == 1.0

    def test_fifty_fifty(self):
        score = _compute_brier_score(0.5, True)
        assert abs(score - 0.25) < 1e-9

    def test_range(self):
        for p in [0.0, 0.25, 0.5, 0.75, 1.0]:
            for actual in [True, False]:
                score = _compute_brier_score(p, actual)
                assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# Weighted score
# ---------------------------------------------------------------------------


class TestWeightedScore:
    def test_binary_correct(self):
        assert _compute_weighted_score(True, None, 1.5) == 1.5

    def test_binary_incorrect(self):
        assert _compute_weighted_score(False, None, 1.0) == 0.0

    def test_brier_perfect(self):
        # brier=0 → weighted = (1-0)*weight = weight
        assert _compute_weighted_score(None, 0.0, 1.25) == 1.25

    def test_brier_worst(self):
        # brier=1 → weighted = (1-1)*weight = 0
        assert _compute_weighted_score(None, 1.0, 1.0) == 0.0

    def test_none_when_no_scores(self):
        assert _compute_weighted_score(None, None, 1.0) is None


# ---------------------------------------------------------------------------
# record_resolution
# ---------------------------------------------------------------------------


class TestRecordResolution:
    def test_calls_db_execute(self, mock_db):
        result = ResolutionResult(
            prediction_hash=FAKE_HASH,
            resolution_status="CORRECT",
            resolver="auto",
            binary_correct=True,
            timeliness_weight=1.0,
            weighted_score=1.0,
            outcome_source="sportsdataio",
        )
        record_resolution(result, db=mock_db)
        mock_db.execute.assert_called_once()

    def test_merge_sql_contains_hash(self, mock_db):
        result = ResolutionResult(
            prediction_hash=FAKE_HASH,
            resolution_status="VOID",
            resolver="manual",
        )
        record_resolution(result, db=mock_db)
        call_sql = mock_db.execute.call_args[0][0]
        assert FAKE_HASH in call_sql

    def test_void_uses_null_scores(self, mock_db):
        result = ResolutionResult(
            prediction_hash=FAKE_HASH,
            resolution_status="VOID",
            resolver="manual",
            outcome_notes="Player never played",
        )
        record_resolution(result, db=mock_db)
        call_sql = mock_db.execute.call_args[0][0]
        assert "VOID" in call_sql


# ---------------------------------------------------------------------------
# resolve_binary
# ---------------------------------------------------------------------------


class TestResolveBinary:
    def test_correct_resolution(self, mock_db):
        result = resolve_binary(FAKE_HASH, True, "sportsdataio", db=mock_db)
        assert result.resolution_status == "CORRECT"
        assert result.binary_correct is True
        assert result.resolver == "auto"

    def test_incorrect_resolution(self, mock_db):
        result = resolve_binary(FAKE_HASH, False, "pfr", db=mock_db)
        assert result.resolution_status == "INCORRECT"
        assert result.binary_correct is False

    def test_timeliness_applied(self, mock_db):
        pred_ts = datetime(2025, 9, 1, tzinfo=timezone.utc)
        outcome_ts = pred_ts + timedelta(days=400)
        result = resolve_binary(
            FAKE_HASH,
            True,
            "pfr",
            prediction_ts=pred_ts,
            outcome_ts=outcome_ts,
            db=mock_db,
        )
        assert result.timeliness_weight == 2.0
        assert result.weighted_score == 2.0


# ---------------------------------------------------------------------------
# resolve_probabilistic
# ---------------------------------------------------------------------------


class TestResolveProbabilistic:
    def test_brier_score_computed(self, mock_db):
        result = resolve_probabilistic(
            FAKE_HASH,
            predicted_prob=0.8,
            actual_outcome=True,
            outcome_source="sportsdataio",
            db=mock_db,
        )
        assert result.brier_score is not None
        assert abs(result.brier_score - 0.04) < 1e-9  # (0.8-1)^2 = 0.04

    def test_correct_status_when_outcome_true(self, mock_db):
        result = resolve_probabilistic(FAKE_HASH, 0.9, True, "sportsdataio", db=mock_db)
        assert result.resolution_status == "CORRECT"

    def test_incorrect_status_when_outcome_false(self, mock_db):
        result = resolve_probabilistic(
            FAKE_HASH, 0.9, False, "sportsdataio", db=mock_db
        )
        assert result.resolution_status == "INCORRECT"


# ---------------------------------------------------------------------------
# resolve_manual / void_prediction
# ---------------------------------------------------------------------------


class TestResolveManual:
    def test_manual_correct(self, mock_db):
        result = resolve_manual(
            FAKE_HASH, True, "Mahomes won MVP per AP vote", db=mock_db
        )
        assert result.resolution_status == "CORRECT"
        assert result.resolver == "manual"

    def test_manual_incorrect(self, mock_db):
        result = resolve_manual(FAKE_HASH, False, "Mahomes did not win MVP", db=mock_db)
        assert result.resolution_status == "INCORRECT"


class TestVoidPrediction:
    def test_void_status(self, mock_db):
        result = void_prediction(FAKE_HASH, "Season cancelled", db=mock_db)
        assert result.resolution_status == "VOID"
        assert result.outcome_notes == "Season cancelled"

    def test_void_has_no_score(self, mock_db):
        result = void_prediction(FAKE_HASH, "Unresolvable", db=mock_db)
        assert result.brier_score is None
        assert result.binary_correct is None
        assert result.weighted_score is None


# ---------------------------------------------------------------------------
# get_pending_predictions
# ---------------------------------------------------------------------------


class TestGetPendingPredictions:
    def test_returns_dataframe(self, mock_db):
        mock_db.fetch_df.return_value = pd.DataFrame(
            [{"prediction_hash": FAKE_HASH, "pundit_id": "adam_schefter"}]
        )
        df = get_pending_predictions(db=mock_db)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 1

    def test_queries_both_tables(self, mock_db):
        get_pending_predictions(db=mock_db)
        query = mock_db.fetch_df.call_args[0][0]
        assert "prediction_ledger" in query
        assert "prediction_resolutions" in query


# ---------------------------------------------------------------------------
# get_pundit_accuracy_summary
# ---------------------------------------------------------------------------


class TestGetPunditAccuracySummary:
    def test_returns_dataframe(self, mock_db):
        mock_db.fetch_df.return_value = pd.DataFrame(
            [
                {
                    "pundit_id": "adam_schefter",
                    "pundit_name": "Adam Schefter",
                    "total_predictions": 10,
                    "resolved_count": 8,
                    "correct_count": 6,
                    "accuracy_rate": 0.75,
                    "avg_brier_score": None,
                    "avg_weighted_score": 0.75,
                }
            ]
        )
        df = get_pundit_accuracy_summary(db=mock_db)
        assert isinstance(df, pd.DataFrame)
        assert df.iloc[0]["accuracy_rate"] == 0.75

    def test_query_contains_brier(self, mock_db):
        get_pundit_accuracy_summary(db=mock_db)
        query = mock_db.fetch_df.call_args[0][0]
        assert "brier_score" in query
        assert "weighted_score" in query
