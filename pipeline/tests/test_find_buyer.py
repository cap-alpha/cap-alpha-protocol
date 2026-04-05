import pytest
import pandas as pd
from unittest.mock import MagicMock, patch
from src.trade_partner_finder import TradePartnerFinder

# Mock Data
MOCK_TEAMS = pd.DataFrame(
    [
        {
            "team": "LV",
            "cap_space": 40000000,
            "qb_spending": 10000000,
            "win_total": 6.5,
            "conference": "AFC",
        },
        {
            "team": "NYG",
            "cap_space": 35000000,
            "qb_spending": 45000000,
            "win_total": 5.5,
            "conference": "NFC",
        },
        {
            "team": "KC",
            "cap_space": 5000000,
            "qb_spending": 60000000,
            "win_total": 11.5,
            "conference": "AFC",
        },
        {
            "team": "TEN",
            "cap_space": 70000000,
            "qb_spending": 8000000,
            "win_total": 6.5,
            "conference": "AFC",
        },
    ]
)


@pytest.fixture
def finder():
    """Returns a TradePartnerFinder instance with mocked database."""
    mock_db = MagicMock()
    # Mock return for team stats query
    mock_db.fetch_df.return_value = MOCK_TEAMS
    return TradePartnerFinder(db_manager=mock_db)


def test_filter_by_cap_space_strict(finder):
    """Refuse likely rejection if team can't afford player."""
    # Player: $30M Cap Hit
    partners = finder.find_buyers(player_id="Kyler", position="QB", cap_hit=30000000)

    # KC ($5M space) should be excluded
    teams = [p["team"] for p in partners]
    assert "KC" not in teams
    assert "LV" in teams
    assert "TEN" in teams


def test_positional_spending_rank(finder):
    """Teams spending LESS on a position should score HIGHER (Need)."""
    # Kyler (QB)
    partners = finder.find_buyers(player_id="Kyler", position="QB", cap_hit=10000000)

    # LV ($10M QB spending) should rank higher than NYG ($45M QB spending)
    lv_score = next(p["score"] for p in partners if p["team"] == "LV")
    nyg_score = next(p["score"] for p in partners if p["team"] == "NYG")

    assert lv_score > nyg_score


def test_window_logic_veteran(finder):
    """Veterans should go to Contenders (High Win Total)."""
    # Mock teams again to ensure clear contender vs rebuilder
    # Assume we override the mock_db for this test or use the fixture logic
    # Just checking relative scoring if logic uses win_total
    pass  # Todo: Refine logic in implementation


def test_edge_case_negative_cap_space(finder):
    """Ensure teams with negative space are handled (excluded)."""
    mock_negative = pd.DataFrame(
        [
            {
                "team": "NO",
                "cap_space": -50000000,
                "qb_spending": 10000000,
                "win_total": 7.5,
                "conference": "NFC",
            }
        ]
    )
    finder.db.fetch_df.return_value = mock_negative

    partners = finder.find_buyers(player_id="Carr", position="QB", cap_hit=10000000)
    assert len(partners) == 0


def test_find_buyer_input_validation(finder):
    """Should raise error on invalid inputs."""
    with pytest.raises(ValueError):
        finder.find_buyers(player_id="Ghost", position="QB", cap_hit=-100)
