"""
Unit tests for pipeline/src/rolling_windows.py (Issue #831).
No BigQuery required — pure logic tests using mocks.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from src.rolling_windows import (
    DRIFT_THRESHOLD,
    MIN_30D,
    MIN_CAREER,
    MIN_LAST_SEASON,
    _compute_drift_flags,
    _displayable,
    _nba_last_completed_season,
    _nfl_last_completed_season,
    compute_rolling_windows,
    get_pundit_rolling_accuracy,
)


# ---------------------------------------------------------------------------
# NFL season boundary
# ---------------------------------------------------------------------------


class TestNflLastCompletedSeason:
    def test_may_returns_previous_sept_to_current_feb(self):
        """today=2026-05-08 → season 2025-09-01 to 2026-02-28"""
        start, end = _nfl_last_completed_season(date(2026, 5, 8))
        assert start == date(2025, 9, 1)
        assert end == date(2026, 2, 28)

    def test_september_start_returns_prior_season(self):
        """today=2025-09-01 → season 2024-09-01 to 2025-02-28"""
        start, end = _nfl_last_completed_season(date(2025, 9, 1))
        assert start == date(2024, 9, 1)
        assert end == date(2025, 2, 28)

    def test_january_still_in_current_season_window(self):
        """today=2026-01-15 → Feb 28 2026 hasn't passed → season 2024-09-01 to 2025-02-28"""
        start, end = _nfl_last_completed_season(date(2026, 1, 15))
        assert start == date(2024, 9, 1)
        assert end == date(2025, 2, 28)

    def test_march_1_season_has_ended(self):
        """today=2026-03-01 → Feb 28 2026 passed → season 2025-09-01 to 2026-02-28"""
        start, end = _nfl_last_completed_season(date(2026, 3, 1))
        assert start == date(2025, 9, 1)
        assert end == date(2026, 2, 28)

    def test_feb_28_boundary_not_yet_past(self):
        """today=2026-02-28 → Feb 28 2026 is today, not yet PAST → previous season"""
        start, end = _nfl_last_completed_season(date(2026, 2, 28))
        assert start == date(2024, 9, 1)
        assert end == date(2025, 2, 28)


# ---------------------------------------------------------------------------
# NBA season boundary
# ---------------------------------------------------------------------------


class TestNbaLastCompletedSeason:
    def test_july_returns_previous_oct_to_current_june(self):
        """today=2026-07-01 → season 2025-10-01 to 2026-06-30"""
        start, end = _nba_last_completed_season(date(2026, 7, 1))
        assert start == date(2025, 10, 1)
        assert end == date(2026, 6, 30)

    def test_may_still_in_season_window(self):
        """today=2026-05-08 → Jun 30 2026 hasn't passed → season 2024-10-01 to 2025-06-30"""
        start, end = _nba_last_completed_season(date(2026, 5, 8))
        assert start == date(2024, 10, 1)
        assert end == date(2025, 6, 30)

    def test_october_1_season_start_not_past_june(self):
        """today=2026-10-01 → Jun 30 2026 has passed → season 2025-10-01 to 2026-06-30"""
        start, end = _nba_last_completed_season(date(2026, 10, 1))
        assert start == date(2025, 10, 1)
        assert end == date(2026, 6, 30)


# ---------------------------------------------------------------------------
# Displayability thresholds
# ---------------------------------------------------------------------------


class TestDisplayable:
    def test_30d_below_min_not_displayable(self):
        assert _displayable("30d", MIN_30D - 1) is False

    def test_30d_at_min_displayable(self):
        assert _displayable("30d", MIN_30D) is True

    def test_30d_above_min_displayable(self):
        assert _displayable("30d", 100) is True

    def test_last_season_below_min_not_displayable(self):
        assert _displayable("last_season", MIN_LAST_SEASON - 1) is False

    def test_last_season_at_min_displayable(self):
        assert _displayable("last_season", MIN_LAST_SEASON) is True

    def test_career_below_min_not_displayable(self):
        assert _displayable("career", MIN_CAREER - 1) is False

    def test_career_at_min_displayable(self):
        assert _displayable("career", MIN_CAREER) is True

    def test_unknown_window_type_returns_false(self):
        # Unknown window → min threshold not found → 0 → always displayable with n>=0
        # But with 0 count it should fail
        assert _displayable("unknown", 0) is False

    def test_career_zero_count_not_displayable(self):
        assert _displayable("career", 0) is False


# ---------------------------------------------------------------------------
# Drift flag computation
# ---------------------------------------------------------------------------


class TestComputeDriftFlags:
    def _make_row(
        self, pundit_id, window_type, accuracy_rate, resolved_count, sport=None
    ):
        return {
            "pundit_id": pundit_id,
            "entity_class": "player",
            "claim_type": "contract",
            "sport": sport,
            "window_type": window_type,
            "accuracy_rate": accuracy_rate,
            "resolved_count": resolved_count,
        }

    def test_no_drift_when_difference_below_threshold(self):
        rows = [
            self._make_row("p1", "career", 0.70, MIN_CAREER),
            self._make_row("p1", "last_season", 0.65, MIN_LAST_SEASON),
        ]
        drift = _compute_drift_flags(rows)
        key = ("p1", "player", "contract", None)
        flagged, magnitude = drift[key]
        assert not flagged
        assert abs(magnitude - 0.05) < 1e-6

    def test_drift_flagged_when_above_threshold(self):
        rows = [
            self._make_row("p1", "career", 0.80, MIN_CAREER),
            self._make_row("p1", "last_season", 0.60, MIN_LAST_SEASON),
        ]
        drift = _compute_drift_flags(rows)
        key = ("p1", "player", "contract", None)
        flagged, magnitude = drift[key]
        assert flagged
        assert abs(magnitude - 0.20) < 1e-6

    def test_drift_exactly_at_threshold_is_flagged(self):
        rows = [
            self._make_row("p1", "career", 0.72, MIN_CAREER),
            self._make_row("p1", "last_season", 0.60, MIN_LAST_SEASON),
        ]
        drift = _compute_drift_flags(rows)
        key = ("p1", "player", "contract", None)
        flagged, magnitude = drift[key]
        assert flagged  # 0.12 >= 0.12

    def test_drift_not_flagged_when_career_below_min(self):
        rows = [
            self._make_row("p1", "career", 0.80, MIN_CAREER - 1),  # not enough
            self._make_row("p1", "last_season", 0.60, MIN_LAST_SEASON),
        ]
        drift = _compute_drift_flags(rows)
        key = ("p1", "player", "contract", None)
        flagged, _ = drift[key]
        assert not flagged

    def test_drift_not_flagged_when_last_season_below_min(self):
        rows = [
            self._make_row("p1", "career", 0.80, MIN_CAREER),
            self._make_row("p1", "last_season", 0.60, MIN_LAST_SEASON - 1),
        ]
        drift = _compute_drift_flags(rows)
        key = ("p1", "player", "contract", None)
        flagged, _ = drift[key]
        assert not flagged

    def test_no_drift_when_last_season_missing(self):
        rows = [
            self._make_row("p1", "career", 0.80, MIN_CAREER),
            self._make_row("p1", "30d", 0.50, MIN_30D),
        ]
        drift = _compute_drift_flags(rows)
        key = ("p1", "player", "contract", None)
        flagged, magnitude = drift[key]
        assert not flagged
        assert magnitude == 0.0

    def test_multiple_pundits_independent(self):
        rows = [
            self._make_row("p1", "career", 0.80, MIN_CAREER),
            self._make_row("p1", "last_season", 0.50, MIN_LAST_SEASON),  # drift 0.30
            self._make_row("p2", "career", 0.70, MIN_CAREER),
            self._make_row("p2", "last_season", 0.65, MIN_LAST_SEASON),  # drift 0.05
        ]
        drift = _compute_drift_flags(rows)
        key1 = ("p1", "player", "contract", None)
        key2 = ("p2", "player", "contract", None)
        assert drift[key1][0] is True  # flagged
        assert drift[key2][0] is False  # not flagged

    def test_drift_not_flagged_when_accuracy_none(self):
        rows = [
            self._make_row("p1", "career", None, MIN_CAREER),
            self._make_row("p1", "last_season", 0.60, MIN_LAST_SEASON),
        ]
        drift = _compute_drift_flags(rows)
        key = ("p1", "player", "contract", None)
        flagged, _ = drift[key]
        assert not flagged

    def test_drift_magnitude_is_absolute(self):
        """Drift is always positive regardless of direction."""
        rows = [
            self._make_row("p1", "career", 0.50, MIN_CAREER),
            self._make_row("p1", "last_season", 0.80, MIN_LAST_SEASON),  # improving
        ]
        drift = _compute_drift_flags(rows)
        key = ("p1", "player", "contract", None)
        flagged, magnitude = drift[key]
        assert flagged
        assert magnitude > 0


# ---------------------------------------------------------------------------
# compute_rolling_windows — BQ mock smoke test
# ---------------------------------------------------------------------------


class TestComputeRollingWindowsSmoke:
    """
    Smoke test: verify compute_rolling_windows correctly annotates rows
    using mocked BQ. Does not hit the network.
    """

    def _make_df_row(self, pundit_id, window_type, accuracy_rate, resolved_count):
        return {
            "pundit_id": pundit_id,
            "entity_class": "player",
            "claim_type": "contract",
            "sport": "NFL",
            "window_type": window_type,
            "accuracy_rate": accuracy_rate,
            "brier_score": 0.2,
            "resolved_count": resolved_count,
        }

    @patch("src.rolling_windows.DBManager")
    @patch.dict("os.environ", {"GCP_PROJECT_ID": "test-project"})
    def test_returns_row_count(self, MockDBManager):
        import pandas as pd

        mock_db = MagicMock()
        MockDBManager.return_value = mock_db
        mock_db.client = MagicMock()

        # Stub out query → dataframe with 2 rows (career + 30d)
        rows = [
            self._make_df_row("p1", "career", 0.75, 25),
            self._make_df_row("p1", "30d", 0.80, 6),
        ]
        mock_df = pd.DataFrame(rows)
        mock_db.client.query.return_value.to_dataframe.return_value = mock_df

        # Stub load job + merge job
        mock_db.client.load_table_from_dataframe.return_value.result.return_value = None
        mock_db.client.query.return_value.result.return_value = None
        mock_db.client.delete_table.return_value = None

        n = compute_rolling_windows(db=mock_db, today=date(2026, 5, 8))
        assert n == 2

    @patch("src.rolling_windows.DBManager")
    @patch.dict("os.environ", {"GCP_PROJECT_ID": "test-project"})
    def test_empty_dataframe_returns_zero(self, MockDBManager):
        import pandas as pd

        mock_db = MagicMock()
        MockDBManager.return_value = mock_db
        mock_db.client = MagicMock()

        mock_db.client.query.return_value.to_dataframe.return_value = pd.DataFrame()

        n = compute_rolling_windows(db=mock_db, today=date(2026, 5, 8))
        assert n == 0


# ---------------------------------------------------------------------------
# get_pundit_rolling_accuracy — API read path
# ---------------------------------------------------------------------------


class TestGetPunditRollingAccuracy:
    """
    Unit tests for the API read path.  All BQ calls are mocked.
    """

    def _make_bq_row(
        self,
        window_type: str,
        accuracy_rate: float | None,
        resolved_count: int,
        displayable: bool,
        drift_flagged: bool,
        drift_magnitude: float,
    ) -> dict:
        return {
            "window_type": window_type,
            "accuracy_rate": accuracy_rate,
            "resolved_count": resolved_count,
            "displayable": displayable,
            "drift_flagged": drift_flagged,
            "drift_magnitude": drift_magnitude,
        }

    def _mock_db_with_rows(self, rows: list[dict]) -> MagicMock:
        import os

        import pandas as pd

        mock_db = MagicMock()
        mock_db.client = MagicMock()
        mock_db.client.query.return_value.to_dataframe.return_value = pd.DataFrame(rows)
        return mock_db

    def test_returns_all_three_windows(self):
        rows = [
            self._make_bq_row("career", 0.81, 412, True, True, 0.07),
            self._make_bq_row("last_season", 0.74, 89, True, True, 0.07),
            self._make_bq_row("30d", 0.68, 12, True, False, 0.0),
        ]
        mock_db = self._mock_db_with_rows(rows)

        with patch.dict("os.environ", {"GCP_PROJECT_ID": "test-project"}):
            result = get_pundit_rolling_accuracy("adam_schefter", db=mock_db)

        assert result["accuracy"]["career"] == pytest.approx(0.81)
        assert result["accuracy"]["last_season"] == pytest.approx(0.74)
        assert result["accuracy"]["last_30_days"] == pytest.approx(0.68)
        assert result["sample_sizes"]["career"] == 412
        assert result["sample_sizes"]["last_season"] == 89
        assert result["sample_sizes"]["last_30_days"] == 12

    def test_drift_flag_true_when_any_window_flagged(self):
        rows = [
            self._make_bq_row("career", 0.81, 412, True, True, 0.07),
            self._make_bq_row("last_season", 0.74, 89, True, True, 0.07),
            self._make_bq_row("30d", 0.68, 12, True, False, 0.0),
        ]
        mock_db = self._mock_db_with_rows(rows)

        with patch.dict("os.environ", {"GCP_PROJECT_ID": "test-project"}):
            result = get_pundit_rolling_accuracy("p1", db=mock_db)

        assert result["accuracy"]["drift_flag"] is True
        assert result["accuracy"]["drift_note"] is not None
        assert (
            "below" in result["accuracy"]["drift_note"]
            or "above" in result["accuracy"]["drift_note"]
        )

    def test_drift_flag_false_when_no_window_flagged(self):
        rows = [
            self._make_bq_row("career", 0.70, 100, True, False, 0.05),
            self._make_bq_row("last_season", 0.68, 30, True, False, 0.05),
            self._make_bq_row("30d", 0.72, 8, True, False, 0.0),
        ]
        mock_db = self._mock_db_with_rows(rows)

        with patch.dict("os.environ", {"GCP_PROJECT_ID": "test-project"}):
            result = get_pundit_rolling_accuracy("p1", db=mock_db)

        assert result["accuracy"]["drift_flag"] is False
        assert result["accuracy"]["drift_note"] is None

    def test_empty_bq_result_returns_null_accuracy(self):
        mock_db = self._mock_db_with_rows([])

        with patch.dict("os.environ", {"GCP_PROJECT_ID": "test-project"}):
            result = get_pundit_rolling_accuracy("unknown_pundit", db=mock_db)

        assert result["accuracy"]["career"] is None
        assert result["accuracy"]["last_season"] is None
        assert result["accuracy"]["last_30_days"] is None
        assert result["accuracy"]["drift_flag"] is False
        assert result["sample_sizes"]["career"] == 0
        assert result["sample_sizes"]["last_season"] == 0
        assert result["sample_sizes"]["last_30_days"] == 0

    def test_missing_window_returns_none_accuracy(self):
        """Only career window exists — last_season and 30d should be None."""
        rows = [
            self._make_bq_row("career", 0.75, 50, True, False, 0.0),
        ]
        mock_db = self._mock_db_with_rows(rows)

        with patch.dict("os.environ", {"GCP_PROJECT_ID": "test-project"}):
            result = get_pundit_rolling_accuracy("p1", db=mock_db)

        assert result["accuracy"]["career"] == pytest.approx(0.75)
        assert result["accuracy"]["last_season"] is None
        assert result["accuracy"]["last_30_days"] is None
        assert result["sample_sizes"]["career"] == 50
        assert result["sample_sizes"]["last_season"] == 0

    def test_drift_note_uses_below_when_last_season_lower(self):
        rows = [
            self._make_bq_row("career", 0.80, 200, True, True, 0.13),
            self._make_bq_row("last_season", 0.67, 30, True, True, 0.13),
            self._make_bq_row("30d", 0.65, 8, False, False, 0.0),
        ]
        mock_db = self._mock_db_with_rows(rows)

        with patch.dict("os.environ", {"GCP_PROJECT_ID": "test-project"}):
            result = get_pundit_rolling_accuracy("p1", db=mock_db)

        assert "below" in result["accuracy"]["drift_note"]

    def test_drift_note_uses_above_when_last_season_higher(self):
        rows = [
            self._make_bq_row("career", 0.60, 200, True, True, 0.20),
            self._make_bq_row("last_season", 0.80, 30, True, True, 0.20),
            self._make_bq_row("30d", 0.82, 8, False, False, 0.0),
        ]
        mock_db = self._mock_db_with_rows(rows)

        with patch.dict("os.environ", {"GCP_PROJECT_ID": "test-project"}):
            result = get_pundit_rolling_accuracy("p1", db=mock_db)

        assert "above" in result["accuracy"]["drift_note"]

    def test_displayable_keys_in_result(self):
        rows = [
            self._make_bq_row("career", 0.75, MIN_CAREER, True, False, 0.0),
            self._make_bq_row(
                "last_season", 0.70, MIN_LAST_SEASON - 1, False, False, 0.0
            ),
            self._make_bq_row("30d", 0.65, MIN_30D + 1, True, False, 0.0),
        ]
        mock_db = self._mock_db_with_rows(rows)

        with patch.dict("os.environ", {"GCP_PROJECT_ID": "test-project"}):
            result = get_pundit_rolling_accuracy("p1", db=mock_db)

        assert result["displayable"]["career"] is True
        assert result["displayable"]["last_season"] is False
        assert result["displayable"]["last_30_days"] is True

    def test_weighted_accuracy_across_multiple_rows_same_window(self):
        """Multiple rows for same window_type (different entity_class) → weighted avg."""
        rows = [
            # career: 2 rows, n=100 @ 0.80, n=100 @ 0.60 → weighted avg = 0.70
            self._make_bq_row("career", 0.80, 100, True, False, 0.0),
            self._make_bq_row("career", 0.60, 100, True, False, 0.0),
        ]
        mock_db = self._mock_db_with_rows(rows)

        with patch.dict("os.environ", {"GCP_PROJECT_ID": "test-project"}):
            result = get_pundit_rolling_accuracy("p1", db=mock_db)

        assert result["accuracy"]["career"] == pytest.approx(0.70)
        assert result["sample_sizes"]["career"] == 200
