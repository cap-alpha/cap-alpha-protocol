import pytest
from src.win_probability import WinProbabilityModel


@pytest.fixture
def model():
    return WinProbabilityModel()


def test_qb_impact(model):
    """
    Test that a QB trade has massive impact (10x weight).
    """
    qb_asset = {
        "type": "player",
        "position": "QB",
        "surplus_value": 20.0,  # Great value
        "risk_score": 0.1,
    }

    # Trade Proposal: Team A gets QB, Team B gets nothing
    proposal = {
        "team_a": "NYJ",
        "team_b": "GB",
        "team_b_assets": [qb_asset],  # Going TO Team A
        "team_a_assets": [],
    }

    impact = model.calculate_win_impact(proposal)
    a_impact = impact["NYJ"]

    # 20 surplus * 10 weight = 200. / 50 divisor = +4 Wins.
    assert a_impact["delta_wins"] == 4.0
    assert a_impact["new_win_total"] == 12.5  # 8.5 + 4


def test_variance_calculation(model):
    """
    Test that high risk assets increase the spread.
    """
    risky_asset = {
        "type": "player",
        "position": "WR",
        "surplus_value": 10.0,
        "risk_score": 0.9,  # High Risk
    }

    proposal = {
        "team_a": "LV",
        "team_b": "KC",
        "team_b_assets": [risky_asset],
        "team_a_assets": [],
    }

    impact = model.calculate_win_impact(proposal)
    a_impact = impact["LV"]

    # Check that variance is calculated
    # 10 surplus * 2 weight = 20. / 50 = 0.4 Wins.
    assert a_impact["delta_wins"] == 0.4

    # Variance check
    # 20 weighted * 0.9 risk = 18. / 50 = 0.36 sigma.
    # Spread = 0.36 * 1.96 = ~0.7
    assert a_impact["vegas_variance"] > 0.5


def test_balanced_trade(model):
    """
    Test a trade where assets cancel out.
    """
    asset_a = {
        "type": "player",
        "position": "OL",
        "surplus_value": 5.0,
        "risk_score": 0.1,
    }
    asset_b = {
        "type": "player",
        "position": "OL",
        "surplus_value": 5.0,
        "risk_score": 0.1,
    }

    proposal = {
        "team_a": "IND",
        "team_b": "TEN",
        "team_a_assets": [asset_a],  # Out
        "team_b_assets": [asset_b],  # In
    }

    impact = model.calculate_win_impact(proposal)
    assert impact["IND"]["delta_wins"] == 0.0
