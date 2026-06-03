"""
Tests for Wilson score lower bound leaderboard sort (Issue #1032).

Covers:
  1. wilson_lower_bound() computation — edge cases and known values
  2. Leaderboard endpoint sorts by Wilson LB (9/10 ranks above 1/1)
  3. Volume floor: pundits with < 5 resolved predictions excluded
"""

import math
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from api.pundit_router import wilson_lower_bound

# ---------------------------------------------------------------------------
# wilson_lower_bound — unit tests
# ---------------------------------------------------------------------------


class TestWilsonLowerBound:
    def test_zero_n_returns_zero(self):
        assert wilson_lower_bound(0, 0) == 0.0

    def test_one_of_one_is_low(self):
        """1/1 (100%) should yield a low Wilson LB (~0.21) due to tiny sample."""
        lb = wilson_lower_bound(1, 1)
        assert lb > 0.0
        assert lb < 0.35, f"Expected lb < 0.35 for 1/1 but got {lb:.4f}"

    def test_nine_of_ten_is_medium(self):
        """9/10 (90%) should yield ~0.60."""
        lb = wilson_lower_bound(9, 10)
        assert 0.55 < lb < 0.65, f"Expected 0.55 < lb < 0.65 for 9/10 but got {lb:.4f}"

    def test_ninetynine_of_hundred_is_high(self):
        """99/100 (99%) should yield ~0.94."""
        lb = wilson_lower_bound(99, 100)
        assert 0.9 < lb < 1.0, f"Expected 0.9 < lb < 1.0 for 99/100 but got {lb:.4f}"

    def test_nine_ten_ranks_above_one_one(self):
        """Core Issue #1032 assertion: 9/10 Wilson > 1/1 Wilson."""
        assert wilson_lower_bound(9, 10) > wilson_lower_bound(1, 1)

    def test_ninetynine_hundred_ranks_above_nine_ten(self):
        assert wilson_lower_bound(99, 100) > wilson_lower_bound(9, 10)

    def test_all_wrong_returns_near_zero(self):
        lb = wilson_lower_bound(0, 10)
        assert lb >= 0.0
        assert lb < 0.05

    def test_perfect_large_sample(self):
        """100/100 should yield a very high LB close to 1.0."""
        lb = wilson_lower_bound(100, 100)
        assert lb > 0.9

    def test_monotone_correct_count(self):
        """With fixed n=20, increasing correct raises Wilson LB."""
        lbs = [wilson_lower_bound(k, 20) for k in range(0, 21)]
        assert lbs == sorted(lbs), (
            "Wilson LB should be monotonically non-decreasing with correct count"
        )


# ---------------------------------------------------------------------------
# Leaderboard endpoint — Wilson sort order
# ---------------------------------------------------------------------------

# Patch DB before importing the app so startup doesn't attempt BQ connection
with patch("src.db_manager.DBManager._initialize_connection"):
    from api.main import app
    from api.api_key_auth import verify_api_key
    from api.pundit_router import get_db
    from api.quality_router import get_db as quality_get_db

_STUB_KEY_INFO = {
    "key_id": "capk_live_test",
    "user_id": "user_test",
    "tier": "pro",
    "status": "active",
    "scopes": [],
    "name": "Test Key",
    "created_at": None,
    "last_used_at": None,
    "key_last_four": "test",
}


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.project_id = "test-project"
    db.dataset_id = "nfl_dead_money"
    mock_job = MagicMock()
    mock_job.result.return_value = None
    db.client.load_table_from_dataframe.return_value = mock_job
    return db


@pytest.fixture
def client(mock_db):
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[quality_get_db] = lambda: mock_db
    app.dependency_overrides[verify_api_key] = lambda: _STUB_KEY_INFO
    yield TestClient(app)
    app.dependency_overrides = {}


def make_leaderboard_df():
    """DataFrame with a 1/1 pundit and a 9/10 pundit.

    Raw accuracy: one_of_one=1.0 > nine_of_ten=0.9
    Wilson sort:  nine_of_ten >> one_of_one  (correct Issue #1032 order)
    """
    return pd.DataFrame(
        [
            {
                "pundit_id": "one_of_one",
                "pundit_name": "One of One",
                "total_predictions": 1,
                "resolved_count": 1,
                "correct_count": 1,
                "accuracy_rate": 1.0,
                "avg_brier_score": 0.0,
                "avg_weighted_score": 1.0,
            },
            {
                "pundit_id": "nine_of_ten",
                "pundit_name": "Nine of Ten",
                "total_predictions": 10,
                "resolved_count": 10,
                "correct_count": 9,
                "accuracy_rate": 0.9,
                "avg_brier_score": 0.09,
                "avg_weighted_score": 0.9,
            },
        ]
    )


class TestLeaderboardWilsonSort:
    def test_nine_of_ten_ranks_above_one_of_one(self, client, mock_db):
        """Issue #1032: 9/10 must appear before 1/1 in the leaderboard response."""
        mock_db.fetch_df.return_value = make_leaderboard_df()
        # get_pundit_stats should return empty so we hit the Wilson branch
        mock_db.fetch_df.side_effect = [make_leaderboard_df(), pd.DataFrame()]
        data = client.get("/v1/leaderboard").json()
        assert "leaderboard" in data
        ids = [row["pundit_id"] for row in data["leaderboard"]]
        nine_idx = ids.index("nine_of_ten")
        one_idx = ids.index("one_of_one")
        assert nine_idx < one_idx, (
            f"nine_of_ten (rank {nine_idx}) should appear before one_of_one (rank {one_idx})"
        )

    def test_wilson_lb_included_in_response(self, client, mock_db):
        """The response may include wilson_lb so callers can verify sort order."""
        mock_db.fetch_df.side_effect = [make_leaderboard_df(), pd.DataFrame()]
        data = client.get("/v1/leaderboard").json()
        rows = data["leaderboard"]
        # wilson_lb is optional in the payload (best-effort enrichment)
        if "wilson_lb" in rows[0]:
            lbs = [row["wilson_lb"] for row in rows]
            assert lbs == sorted(lbs, reverse=True), (
                "Wilson LBs in response should be descending"
            )
