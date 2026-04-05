import os
import sys

# Add pipeline root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from pipeline.src.win_probability import WinProbabilityModel


def test_qb_impact():
    print("Testing QB Impact...")
    model = WinProbabilityModel()
    qb_asset = {
        "type": "player",
        "position": "QB",
        "surplus_value": 20.0,
        "risk_score": 0.1,
    }
    proposal = {
        "team_a": "NYJ",
        "team_b": "GB",
        "team_b_assets": [qb_asset],
        "team_a_assets": [],
    }
    impact = model.calculate_win_impact(proposal)
    a_impact = impact["NYJ"]

    print(f"  Delta Wins: {a_impact['delta_wins']}")
    if a_impact["delta_wins"] == 4.0:
        print("  ✅ PASS: QB Impact correct.")
    else:
        print(f"  ❌ FAIL: Expected 4.0, got {a_impact['delta_wins']}")


def test_variance():
    print("Testing Variance...")
    model = WinProbabilityModel()
    risky_asset = {
        "type": "player",
        "position": "WR",
        "surplus_value": 10.0,
        "risk_score": 0.9,
    }
    proposal = {
        "team_a": "LV",
        "team_b": "KC",
        "team_b_assets": [risky_asset],
        "team_a_assets": [],
    }
    impact = model.calculate_win_impact(proposal)
    a_impact = impact["LV"]

    print(f"  Variance: {a_impact['vegas_variance']}")
    if a_impact["vegas_variance"] > 0.5:
        print("  ✅ PASS: Variance detected.")
    else:
        print(f"  ❌ FAIL: Variance too low.")


if __name__ == "__main__":
    test_qb_impact()
    test_variance()
