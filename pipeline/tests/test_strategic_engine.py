import pytest
import pandas as pd
import os
from unittest.mock import MagicMock
from src.strategic_engine import StrategicEngine
from pathlib import Path

# Skip if DB missing in CI environment
DB_PATH = os.getenv("DB_PATH", "data/nfl_data.db")
if not Path(DB_PATH).exists():
    pytest.skip(
        "Production DB not found, skipping strategic engine tests",
        allow_module_level=True,
    )


@pytest.fixture
def engine():
    db_path = os.getenv("DB_PATH", "data/nfl_data.db")
    return StrategicEngine(db_path)


def test_prescribe_emergency_purge(engine):
    row = pd.Series(
        {
            "team": "TEST_TEAM",
            "avg_risk": 0.7,
            "avg_efficiency": 0.4,
            "anchor_risk_player": "Sample Veteran",
            "top_risk_position": "QB",
            "anchor_risk_position": "QB",
        }
    )
    strat, draft = engine.prescribe(row)
    assert "EMERGENCY PURGE" in strat
    assert "QB" in draft


def test_prescribe_aggressive_expansion(engine):
    row = pd.Series(
        {
            "team": "TEST_TEAM",
            "avg_risk": 0.2,
            "avg_efficiency": 1.5,
            "anchor_risk_player": "Elite Talent",
            "top_risk_position": "WR",
            "anchor_risk_position": "WR",
        }
    )
    strat, draft = engine.prescribe(row)
    assert "AGGRESSIVE EXPANSION" in strat
    assert (
        "Best Player Available (BPA)" in draft or "WR" in draft
    )  # Depending on logic specifics


def test_prescribe_structural_rebalancing(engine):
    row = pd.Series(
        {
            "team": "TEST_TEAM",
            "avg_risk": 0.5,
            "avg_efficiency": 0.8,
            "anchor_risk_player": "Aging Star",
            "top_risk_position": "LT",
            "anchor_risk_position": "LT",
        }
    )
    strat, draft = engine.prescribe(row)
    assert "STRUCTURAL REBALANCING" in strat
    assert "LT" in draft


def test_prescribe_successor_suppression(engine):
    # Mocking the database response for check_succession_plan
    # We need to mock the execute method of the connection
    engine.con = MagicMock()

    # Mock query logic:
    # 1. FA Check -> Returns None (No FA splash)
    # 2. Table Exist Check -> Returns 1 (True)
    # 3. Successor Check -> Returns Successor
    engine.con.execute.return_value.fetchone.side_effect = [
        None,  # FA Check
        (1,),  # Table Exists
        ("Michael Penix Jr.", 1, 2024),  # Found successor
    ]

    row = pd.Series(
        {
            "team": "ATL",
            "avg_risk": 0.5,
            "avg_efficiency": 0.8,
            "anchor_risk_player": "Kirk Cousins",
            "top_risk_position": "QB",
            "anchor_risk_position": "QB",
        }
    )

    strat, draft = engine.prescribe(row)
    assert "STRUCTURAL REBALANCING" in strat
    assert "Develop Successor" in draft
    assert "Michael Penix Jr." in draft


def test_prescribe_fa_suppression(engine):
    # Mock connection and cursor
    engine.con = MagicMock()

    # Mock query responses in order:
    # 1. FA Check -> Returns Player (Big Splash found)
    # 2. Successor Check -> Skipped or None (if flow requires it, but logic should short-circuit)

    # We need to simulate the sequence of valid calls:
    # First call to execute is inside check_fa_signings
    engine.con.execute.return_value.fetchone.return_value = ("Tee Higgins",)

    row = pd.Series(
        {
            "team": "NYG",
            "avg_risk": 0.65,  # High risk
            "avg_efficiency": 0.45,  # Low Efficiency
            "anchor_risk_player": "Daniel Jones",
            "top_risk_position": "WR",
            "anchor_risk_position": "QB",
        }
    )

    # NOTE: top_risk_position is WR, so we check FA for WR.
    # Logic: draft_pos = top_risk or anchor_risk. Here WR.

    strat, draft = engine.prescribe(row)

    # Expect EMERGENCY PURGE due to stats
    assert "EMERGENCY PURGE" in strat
    # Expect FA Solution logic
    assert "FA Solution Acquired" in draft
    assert "Tee Higgins" in draft
