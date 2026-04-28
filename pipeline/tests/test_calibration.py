"""
Unit tests for pipeline/src/calibration.py (Issue #341).
No BigQuery required — pure math tests.
"""

import pytest

from src.calibration import (
    compute_brier_score,
    compute_overconfidence_score,
    compute_reliability_bins,
)


# ---------------------------------------------------------------------------
# compute_brier_score
# ---------------------------------------------------------------------------


class TestComputeBrierScore:
    def test_empty_returns_random_baseline(self):
        assert compute_brier_score([]) == 0.25

    def test_all_correct_perfect_confidence(self):
        # confidence=1.0, outcome=1 → (1-1)^2 = 0 for each
        preds = [{"confidence": 1.0, "outcome": 1} for _ in range(10)]
        assert compute_brier_score(preds) == pytest.approx(0.0)

    def test_all_wrong_full_confidence(self):
        # confidence=1.0, outcome=0 → (1-0)^2 = 1 for each
        preds = [{"confidence": 1.0, "outcome": 0} for _ in range(10)]
        assert compute_brier_score(preds) == pytest.approx(1.0)

    def test_random_baseline_half_confidence(self):
        # confidence=0.5, outcome alternates → mean((0.5-1)^2, (0.5-0)^2) = 0.25
        preds = [
            {"confidence": 0.5, "outcome": 1},
            {"confidence": 0.5, "outcome": 0},
        ]
        assert compute_brier_score(preds) == pytest.approx(0.25)

    def test_single_prediction_correct(self):
        preds = [{"confidence": 0.8, "outcome": 1}]
        assert compute_brier_score(preds) == pytest.approx(0.04)  # (0.8-1)^2 = 0.04

    def test_single_prediction_incorrect(self):
        preds = [{"confidence": 0.8, "outcome": 0}]
        assert compute_brier_score(preds) == pytest.approx(0.64)  # (0.8-0)^2 = 0.64

    def test_mixed_predictions(self):
        preds = [
            {"confidence": 0.9, "outcome": 1},  # (0.1)^2 = 0.01
            {"confidence": 0.3, "outcome": 0},  # (0.3)^2 = 0.09
            {"confidence": 0.7, "outcome": 1},  # (0.3)^2 = 0.09
        ]
        expected = (0.01 + 0.09 + 0.09) / 3
        assert compute_brier_score(preds) == pytest.approx(expected)

    def test_bool_outcomes_accepted(self):
        preds = [
            {"confidence": 0.9, "outcome": True},
            {"confidence": 0.1, "outcome": False},
        ]
        # (0.9-1)^2 = 0.01, (0.1-0)^2 = 0.01
        assert compute_brier_score(preds) == pytest.approx(0.01)

    def test_perfect_probabilistic_predictions(self):
        # Confidence matches outcomes exactly
        preds = [
            {"confidence": 0.0, "outcome": 0},
            {"confidence": 1.0, "outcome": 1},
            {"confidence": 0.0, "outcome": 0},
        ]
        assert compute_brier_score(preds) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# compute_reliability_bins
# ---------------------------------------------------------------------------


class TestComputeReliabilityBins:
    def test_empty_returns_empty(self):
        assert compute_reliability_bins([]) == []

    def test_single_bin(self):
        # All predictions in the 0.8-1.0 bucket (confidence = 0.9)
        preds = [
            {"confidence": 0.9, "outcome": 1},
            {"confidence": 0.9, "outcome": 1},
            {"confidence": 0.9, "outcome": 0},
        ]
        bins = compute_reliability_bins(preds, n_bins=5)
        # bin index 4 = [0.8, 1.0), center = 0.9
        assert len(bins) == 1
        b = bins[0]
        assert b["bin_center"] == pytest.approx(0.9)
        assert b["count"] == 3
        assert b["actual_hit_rate"] == pytest.approx(2 / 3, abs=1e-3)
        assert b["predicted_confidence"] == pytest.approx(0.9)

    def test_multiple_bins(self):
        preds = [
            {"confidence": 0.1, "outcome": 0},  # bin 0
            {"confidence": 0.1, "outcome": 1},  # bin 0
            {"confidence": 0.9, "outcome": 1},  # bin 4
            {"confidence": 0.9, "outcome": 1},  # bin 4
        ]
        bins = compute_reliability_bins(preds, n_bins=5)
        assert len(bins) == 2

        low_bin = next(b for b in bins if b["bin_center"] == pytest.approx(0.1))
        high_bin = next(b for b in bins if b["bin_center"] == pytest.approx(0.9))

        assert low_bin["count"] == 2
        assert low_bin["actual_hit_rate"] == pytest.approx(0.5)
        assert high_bin["count"] == 2
        assert high_bin["actual_hit_rate"] == pytest.approx(1.0)

    def test_all_same_confidence(self):
        preds = [{"confidence": 0.5, "outcome": 1} for _ in range(10)]
        bins = compute_reliability_bins(preds, n_bins=5)
        assert len(bins) == 1
        b = bins[0]
        # confidence 0.5 → bin index 2 (0.4–0.6), center 0.5
        assert b["bin_center"] == pytest.approx(0.5)
        assert b["count"] == 10
        assert b["actual_hit_rate"] == pytest.approx(1.0)

    def test_confidence_at_exactly_one_clamps_to_last_bin(self):
        preds = [{"confidence": 1.0, "outcome": 1}]
        bins = compute_reliability_bins(preds, n_bins=5)
        assert len(bins) == 1
        # confidence 1.0 → clamps to bin index 4
        assert bins[0]["bin_center"] == pytest.approx(0.9)

    def test_confidence_at_zero(self):
        preds = [{"confidence": 0.0, "outcome": 0}]
        bins = compute_reliability_bins(preds, n_bins=5)
        assert len(bins) == 1
        assert bins[0]["bin_center"] == pytest.approx(0.1)

    def test_n_bins_respected(self):
        # With n_bins=10, only populate bins at 0.05 and 0.95
        preds = [
            {"confidence": 0.05, "outcome": 0},
            {"confidence": 0.95, "outcome": 1},
        ]
        bins = compute_reliability_bins(preds, n_bins=10)
        assert len(bins) == 2
        centers = [b["bin_center"] for b in bins]
        assert 0.05 in [pytest.approx(c) for c in centers]
        assert 0.95 in [pytest.approx(c) for c in centers]

    def test_perfect_calibration_is_diagonal(self):
        # For a perfectly calibrated pundit each bin's hit_rate == predicted_confidence
        preds = [
            {"confidence": 0.1, "outcome": 0},
            {"confidence": 0.3, "outcome": 0},
            {"confidence": 0.5, "outcome": 1},
            {"confidence": 0.7, "outcome": 1},
            {"confidence": 0.9, "outcome": 1},
        ]
        bins = compute_reliability_bins(preds, n_bins=5)
        # Each bin has exactly 1 prediction so hit_rate == outcome (0 or 1)
        # Not a perfect test of calibration, but checks structure
        for b in bins:
            assert 0.0 <= b["actual_hit_rate"] <= 1.0
            assert 0.0 <= b["predicted_confidence"] <= 1.0
            assert b["count"] >= 1


# ---------------------------------------------------------------------------
# compute_overconfidence_score
# ---------------------------------------------------------------------------


class TestComputeOverconfidenceScore:
    def test_empty_returns_zero(self):
        assert compute_overconfidence_score([]) == pytest.approx(0.0)

    def test_perfectly_calibrated(self):
        # confidence == outcome on average → 0
        preds = [
            {"confidence": 1.0, "outcome": 1},
            {"confidence": 0.0, "outcome": 0},
        ]
        assert compute_overconfidence_score(preds) == pytest.approx(0.0)

    def test_overconfident(self):
        # Always confident 0.9 but only correct half the time → overconfident
        preds = [
            {"confidence": 0.9, "outcome": 1},
            {"confidence": 0.9, "outcome": 0},
        ]
        # mean(0.9-1, 0.9-0) = mean(-0.1, 0.9) = 0.4
        assert compute_overconfidence_score(preds) == pytest.approx(0.4)

    def test_underconfident(self):
        # Always modest 0.3 but correct most of the time
        preds = [
            {"confidence": 0.3, "outcome": 1},
            {"confidence": 0.3, "outcome": 1},
            {"confidence": 0.3, "outcome": 0},
        ]
        # mean(-0.7, -0.7, 0.3) = -1.1/3 ≈ -0.3667
        expected = (-0.7 - 0.7 + 0.3) / 3
        assert compute_overconfidence_score(preds) == pytest.approx(expected)

    def test_single_correct_high_confidence(self):
        preds = [{"confidence": 0.95, "outcome": 1}]
        assert compute_overconfidence_score(preds) == pytest.approx(-0.05)

    def test_all_wrong_with_full_confidence(self):
        preds = [{"confidence": 1.0, "outcome": 0} for _ in range(5)]
        assert compute_overconfidence_score(preds) == pytest.approx(1.0)
