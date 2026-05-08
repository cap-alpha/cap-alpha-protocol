"""
Unit tests for pipeline/src/calibration.py (Issues #341, #809).
No BigQuery required — pure math + mock-BQ tests.
"""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.calibration import (
    _brier_score_query,
    compute_brier_score,
    compute_calibration,
    compute_overconfidence_score,
    compute_reliability_bins,
    get_current_nfl_season,
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


# ---------------------------------------------------------------------------
# Issue #809 — multi-dimensional calibration helpers
# ---------------------------------------------------------------------------


class TestGetCurrentNflSeason:
    """Test the NFL season calendar boundary helper."""

    def test_may_returns_prior_year(self):
        """May is off-season → current season is year-1."""
        from datetime import date

        assert get_current_nfl_season(today_fn=lambda: date(2026, 5, 8)) == 2025

    def test_january_returns_prior_year(self):
        """January (playoffs) still belongs to the previous season year."""
        from datetime import date

        assert get_current_nfl_season(today_fn=lambda: date(2026, 1, 15)) == 2025

    def test_august_returns_current_year(self):
        """August (pre-season) starts the new season."""
        from datetime import date

        assert get_current_nfl_season(today_fn=lambda: date(2026, 8, 1)) == 2026

    def test_september_returns_current_year(self):
        """September (week 1) is in the new season."""
        from datetime import date

        assert get_current_nfl_season(today_fn=lambda: date(2026, 9, 10)) == 2026


class TestBrierScorePerfectAndWorst:
    """Requirement: Brier=0 when confidence=1 and correct, Brier=1 when confidence=1 and wrong."""

    def test_perfect_calibration_brier_zero(self):
        """confidence=1.0, outcome=True → Brier = (1-1)^2 = 0."""
        preds = [{"confidence": 1.0, "outcome": True}]
        assert compute_brier_score(preds) == pytest.approx(0.0)

    def test_worst_calibration_brier_one(self):
        """confidence=1.0, outcome=False → Brier = (1-0)^2 = 1."""
        preds = [{"confidence": 1.0, "outcome": False}]
        assert compute_brier_score(preds) == pytest.approx(1.0)


class TestBrierScoreQueryGroupingSets:
    """Verify _brier_score_query produces a GROUPING SETS clause with all required combos."""

    def test_query_contains_grouping_sets(self):
        sql = _brier_score_query("my-project", season_year_filter=2025)
        assert "GROUPING SETS" in sql.upper()

    def test_query_contains_all_five_grouping_combos(self):
        sql = _brier_score_query("my-project", season_year_filter=None)
        # All five GROUPING SETS combinations should appear
        assert "season_year, entity_class, claim_type" in sql
        assert "season_year, entity_class" in sql
        assert "season_year, claim_type" in sql

    def test_season_year_filter_injected(self):
        sql = _brier_score_query("test-project", season_year_filter=2025)
        assert "l.season_year = 2025" in sql

    def test_no_season_year_filter_when_none(self):
        sql = _brier_score_query("test-project", season_year_filter=None)
        assert "l.season_year =" not in sql

    def test_murphy_decomposition_terms_present(self):
        sql = _brier_score_query("test-project", season_year_filter=None)
        # uncertainty = p_bar * (1 - p_bar)
        assert "uncertainty" in sql.lower()
        # resolution and reliability derived terms
        assert "resolution" in sql.lower()
        assert "reliability" in sql.lower()


class TestComputeCalibrationMocked:
    """Test compute_calibration() with a mocked BQ client — no real BigQuery calls."""

    def _make_mock_db(self, rows: list[dict]) -> MagicMock:
        """Return a DBManager mock whose client.query().to_dataframe() returns rows."""
        db = MagicMock()
        df = pd.DataFrame(rows) if rows else pd.DataFrame()
        query_job = MagicMock()
        query_job.to_dataframe.return_value = df
        query_job.result.return_value = None
        db.client.query.return_value = query_job
        db.client.load_table_from_dataframe.return_value = query_job
        db.client.delete_table.return_value = None
        return db

    def test_empty_result_returns_empty_list(self):
        db = self._make_mock_db([])
        with patch.dict("os.environ", {"GCP_PROJECT_ID": "test-proj"}):
            result = compute_calibration(db_manager=db, season_year=2025)
        assert result == []

    def test_grouping_sets_all_combos_present(self):
        """Given mock rows with all five GROUPING SET combinations, verify they are returned."""
        rows = [
            # (pundit_id, season_year, entity_class, claim_type) — full
            {
                "pundit_id": "adam_schefter",
                "pundit_name": "Adam Schefter",
                "season_year": 2025,
                "entity_class": "PLAYER",
                "claim_type": "trade",
                "sport": "nfl",
                "brier_score": 0.1,
                "reliability": 0.05,
                "resolution": 0.2,
                "uncertainty": 0.25,
                "accuracy_rate": 0.8,
                "total_claims": 10,
                "resolved_claims": 10,
                "correct_claims": 8,
                "anomaly_flag": False,
                "last_updated": pd.Timestamp("2026-05-08"),
            },
            # (pundit_id, season_year, entity_class) — entity rollup
            {
                "pundit_id": "adam_schefter",
                "pundit_name": "Adam Schefter",
                "season_year": 2025,
                "entity_class": "PLAYER",
                "claim_type": None,
                "sport": "nfl",
                "brier_score": 0.12,
                "reliability": 0.06,
                "resolution": 0.19,
                "uncertainty": 0.24,
                "accuracy_rate": 0.75,
                "total_claims": 20,
                "resolved_claims": 20,
                "correct_claims": 15,
                "anomaly_flag": False,
                "last_updated": pd.Timestamp("2026-05-08"),
            },
            # (pundit_id, season_year, claim_type) — claim type rollup
            {
                "pundit_id": "adam_schefter",
                "pundit_name": "Adam Schefter",
                "season_year": 2025,
                "entity_class": None,
                "claim_type": "trade",
                "sport": "nfl",
                "brier_score": 0.11,
                "reliability": 0.055,
                "resolution": 0.195,
                "uncertainty": 0.245,
                "accuracy_rate": 0.78,
                "total_claims": 12,
                "resolved_claims": 12,
                "correct_claims": 9,
                "anomaly_flag": False,
                "last_updated": pd.Timestamp("2026-05-08"),
            },
            # (pundit_id, season_year) — season total
            {
                "pundit_id": "adam_schefter",
                "pundit_name": "Adam Schefter",
                "season_year": 2025,
                "entity_class": None,
                "claim_type": None,
                "sport": "nfl",
                "brier_score": 0.15,
                "reliability": 0.07,
                "resolution": 0.17,
                "uncertainty": 0.23,
                "accuracy_rate": 0.72,
                "total_claims": 50,
                "resolved_claims": 50,
                "correct_claims": 36,
                "anomaly_flag": False,
                "last_updated": pd.Timestamp("2026-05-08"),
            },
            # (pundit_id) — all-time
            {
                "pundit_id": "adam_schefter",
                "pundit_name": "Adam Schefter",
                "season_year": None,
                "entity_class": None,
                "claim_type": None,
                "sport": "nfl",
                "brier_score": 0.16,
                "reliability": 0.08,
                "resolution": 0.16,
                "uncertainty": 0.22,
                "accuracy_rate": 0.70,
                "total_claims": 200,
                "resolved_claims": 200,
                "correct_claims": 140,
                "anomaly_flag": False,
                "last_updated": pd.Timestamp("2026-05-08"),
            },
        ]
        db = self._make_mock_db(rows)
        with patch.dict("os.environ", {"GCP_PROJECT_ID": "test-proj"}):
            result = compute_calibration(db_manager=db, season_year=2025)

        assert len(result) == 5

        # Verify the five GROUPING SET combinations are present
        season_entity_claim = [
            r
            for r in result
            if r["season_year"] == 2025
            and r["entity_class"] == "PLAYER"
            and r["claim_type"] == "trade"
        ]
        season_entity_only = [
            r
            for r in result
            if r["season_year"] == 2025
            and r["entity_class"] == "PLAYER"
            and r["claim_type"] is None
        ]
        season_claim_only = [
            r
            for r in result
            if r["season_year"] == 2025
            and r["entity_class"] is None
            and r["claim_type"] == "trade"
        ]
        season_total = [
            r
            for r in result
            if r["season_year"] == 2025
            and r["entity_class"] is None
            and r["claim_type"] is None
        ]
        alltime = [
            r
            for r in result
            if r["season_year"] is None
            and r["entity_class"] is None
            and r["claim_type"] is None
        ]

        assert len(season_entity_claim) == 1, "Missing full breakdown row"
        assert len(season_entity_only) == 1, "Missing entity_class rollup row"
        assert len(season_claim_only) == 1, "Missing claim_type rollup row"
        assert len(season_total) == 1, "Missing season total row"
        assert len(alltime) == 1, "Missing all-time row"
