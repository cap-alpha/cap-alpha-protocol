"""
Unit tests for the 2025 season backtest precision report (issue #245).
No BigQuery required — all DB calls are mocked.
"""

import pandas as pd
import pytest

from scripts.backtest_precision_report import compute_precision_metrics


# ---------------------------------------------------------------------------
# compute_precision_metrics
# ---------------------------------------------------------------------------


def _make_pred_df(rows: list[dict]) -> pd.DataFrame:
    """Build a prediction_count DataFrame like the one returned by fetch_prediction_counts."""
    return pd.DataFrame(
        rows,
        columns=["claim_category", "status", "prediction_count", "pundit_count"],
    )


def _make_res_df(rows: list[dict]) -> pd.DataFrame:
    """Build a resolution summary DataFrame like the one returned by fetch_resolution_summary."""
    return pd.DataFrame(
        rows,
        columns=["claim_category", "resolution_status", "resolver", "count"],
    )


def test_no_data_returns_zeros():
    metrics = compute_precision_metrics(pd.DataFrame(), pd.DataFrame())
    assert metrics["total_predictions"] == 0
    assert metrics["testable"] == 0
    assert metrics["resolved"] == 0
    assert metrics["precision_pct"] == 0.0
    assert metrics["accuracy_pct"] is None


def test_all_pending_no_resolutions():
    pred_df = _make_pred_df(
        [
            ("draft_pick", "PENDING", 10, 3),
            ("game_outcome", "PENDING", 5, 2),
        ]
    )
    metrics = compute_precision_metrics(pred_df, pd.DataFrame())
    assert metrics["total_predictions"] == 15
    assert metrics["testable"] == 15
    assert metrics["resolved"] == 0
    assert metrics["precision_pct"] == 0.0
    assert metrics["accuracy_pct"] is None


def test_voided_excluded_from_testable():
    pred_df = _make_pred_df(
        [
            ("draft_pick", "PENDING", 8, 2),
            ("draft_pick", "VOIDED", 2, 1),
        ]
    )
    metrics = compute_precision_metrics(pred_df, pd.DataFrame())
    assert metrics["total_predictions"] == 10
    assert metrics["testable"] == 8  # VOIDED excluded


def test_precision_and_accuracy():
    pred_df = _make_pred_df(
        [
            ("draft_pick", "PENDING", 100, 5),
        ]
    )
    res_df = _make_res_df(
        [
            ("draft_pick", "CORRECT", "auto", 60),
            ("draft_pick", "INCORRECT", "auto", 40),
        ]
    )
    metrics = compute_precision_metrics(pred_df, res_df)
    assert metrics["total_predictions"] == 100
    assert metrics["testable"] == 100
    assert metrics["resolved"] == 100
    assert metrics["precision_pct"] == 100.0
    assert metrics["accuracy_pct"] == 60.0


def test_partial_resolution():
    pred_df = _make_pred_df(
        [
            ("game_outcome", "PENDING", 200, 8),
            ("game_outcome", "VOIDED", 20, 3),
        ]
    )
    res_df = _make_res_df(
        [
            ("game_outcome", "CORRECT", "auto", 50),
            ("game_outcome", "INCORRECT", "auto", 30),
        ]
    )
    metrics = compute_precision_metrics(pred_df, res_df)
    assert metrics["total_predictions"] == 220
    assert metrics["testable"] == 200  # 220 - 20 voided
    assert metrics["resolved"] == 80  # 50 + 30
    assert metrics["precision_pct"] == 40.0  # 80/200
    assert metrics["accuracy_pct"] == 62.5  # 50/80


def test_mixed_categories():
    pred_df = _make_pred_df(
        [
            ("draft_pick", "PENDING", 50, 5),
            ("game_outcome", "PENDING", 30, 4),
            ("player_performance", "VOIDED", 10, 2),
        ]
    )
    res_df = _make_res_df(
        [
            ("draft_pick", "CORRECT", "auto", 20),
            ("draft_pick", "INCORRECT", "auto", 10),
            ("game_outcome", "CORRECT", "auto", 15),
        ]
    )
    metrics = compute_precision_metrics(pred_df, res_df)
    assert metrics["total_predictions"] == 90
    assert metrics["testable"] == 80  # 90 - 10 voided
    assert metrics["resolved"] == 45  # 20+10+15
    assert metrics["precision_pct"] == 56.2  # 45/80 * 100 rounded
    assert metrics["accuracy_pct"] == 77.8  # 35/45 * 100 rounded


def test_zero_testable_no_division_error():
    pred_df = _make_pred_df(
        [
            ("draft_pick", "VOIDED", 10, 2),
        ]
    )
    res_df = _make_res_df(
        [
            ("draft_pick", "CORRECT", "auto", 5),
        ]
    )
    metrics = compute_precision_metrics(pred_df, res_df)
    assert metrics["testable"] == 0
    assert metrics["precision_pct"] == 0.0


def test_accuracy_none_when_no_resolutions():
    pred_df = _make_pred_df([("draft_pick", "PENDING", 10, 2)])
    metrics = compute_precision_metrics(pred_df, pd.DataFrame())
    assert metrics["accuracy_pct"] is None


def test_accuracy_none_when_only_voided_resolutions():
    pred_df = _make_pred_df([("draft_pick", "PENDING", 10, 2)])
    res_df = _make_res_df([("draft_pick", "VOID", "auto", 5)])
    metrics = compute_precision_metrics(pred_df, res_df)
    # VOID resolution_status not CORRECT or INCORRECT → resolved = 0
    assert metrics["resolved"] == 0
    assert metrics["accuracy_pct"] is None
