"""
Unit tests for Phase A resolution stub modules (Issue #683).

Verifies that resolve_pending_politics and resolve_pending_finance:
  - call get_pending_predictions with the correct sport value
  - always return an empty list (no resolution logic yet)
"""

from unittest.mock import MagicMock, patch

import pandas as pd


def _make_df(n_rows: int) -> pd.DataFrame:
    """Return a minimal DataFrame with n_rows to simulate pending predictions."""
    return pd.DataFrame(
        {
            "prediction_hash": [f"hash_{i:03d}" * 8 for i in range(n_rows)],
            "sport": ["politics"] * n_rows,
        }
    )


class TestResolvePendingPolitics:
    def test_resolve_pending_politics_returns_empty_list(self):
        """Mock get_pending_predictions to return 3-row DF; assert [] is returned."""
        fake_df = _make_df(3)

        with patch(
            "src.resolve_daily_politics.get_pending_predictions", return_value=fake_df
        ) as mock_get:
            from src.resolve_daily_politics import resolve_pending_politics

            result = resolve_pending_politics()

        assert result == [], f"Expected [], got {result!r}"
        mock_get.assert_called_once_with(sport="politics", db=None)

    def test_resolve_pending_politics_passes_db(self):
        """db kwarg is forwarded to get_pending_predictions."""
        fake_df = _make_df(1)
        mock_db = MagicMock()

        with patch(
            "src.resolve_daily_politics.get_pending_predictions", return_value=fake_df
        ) as mock_get:
            from src.resolve_daily_politics import resolve_pending_politics

            result = resolve_pending_politics(db=mock_db)

        assert result == []
        mock_get.assert_called_once_with(sport="politics", db=mock_db)


class TestResolvePendingFinance:
    def test_resolve_pending_finance_returns_empty_list(self):
        """Mock get_pending_predictions to return 3-row DF; assert [] is returned."""
        fake_df = _make_df(3)

        with patch(
            "src.resolve_daily_finance.get_pending_predictions", return_value=fake_df
        ) as mock_get:
            from src.resolve_daily_finance import resolve_pending_finance

            result = resolve_pending_finance()

        assert result == [], f"Expected [], got {result!r}"
        mock_get.assert_called_once_with(sport="finance", db=None)

    def test_resolve_pending_finance_passes_db(self):
        """db kwarg is forwarded to get_pending_predictions."""
        fake_df = _make_df(1)
        mock_db = MagicMock()

        with patch(
            "src.resolve_daily_finance.get_pending_predictions", return_value=fake_df
        ) as mock_get:
            from src.resolve_daily_finance import resolve_pending_finance

            result = resolve_pending_finance(db=mock_db)

        assert result == []
        mock_get.assert_called_once_with(sport="finance", db=mock_db)
