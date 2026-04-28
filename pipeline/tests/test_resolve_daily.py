"""
Tests for the Daily Prediction Resolution Engine (Issue #191).
Unit tests — no BigQuery required. All DB calls are mocked.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from src.resolve_daily import (
    _extract_draft_claim,
    _extract_game_claim,
    _extract_player_stat_claim,
    _normalize_name,
    _normalize_team,
    _resolve_team_claim,
    resolve_draft_picks,
    resolve_game_outcomes,
    resolve_player_performance,
)

FAKE_HASH = "b" * 64


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.fetch_df.return_value = pd.DataFrame()
    return db


def _make_pending_df(category: str, claims: list[dict]) -> pd.DataFrame:
    rows = []
    for i, c in enumerate(claims):
        rows.append(
            {
                "prediction_hash": f"{'a' * 60}{i:04d}",
                "extracted_claim": c.get("claim", ""),
                "claim_category": category,
                "season_year": c.get("season_year", 2024),
                "target_player_id": c.get("target_player_id"),
                "target_player_name": c.get("player_name"),
                "ingestion_timestamp": datetime(2024, 9, 1, tzinfo=timezone.utc),
                "sport": "NFL",
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# _normalize_team
# ---------------------------------------------------------------------------


class TestNormalizeTeam:
    def test_long_name_chiefs(self):
        assert _normalize_team("Kansas City Chiefs") == "KC"

    def test_nickname_only_eagles(self):
        assert _normalize_team("Eagles") == "PHI"

    def test_partial_match_bears(self):
        assert _normalize_team("Chicago Bears") == "CHI"

    def test_unknown_returns_none(self):
        assert _normalize_team("Unknown Football Club") is None

    def test_abbreviation_passthrough(self):
        result = _normalize_team("KC")
        assert result == "KC"

    def test_commanders_nickname(self):
        assert _normalize_team("Commanders") == "WAS"

    def test_washington_commanders_full_name(self):
        assert _normalize_team("Washington Commanders") == "WAS"

    def test_washington_only(self):
        assert _normalize_team("Washington") == "WAS"


# ---------------------------------------------------------------------------
# _extract_game_claim
# ---------------------------------------------------------------------------


class TestExtractGameClaim:
    def test_win_prediction(self):
        result = _extract_game_claim("Chiefs will beat Eagles in 2026 Super Bowl")
        assert result.get("team_a") == "KC"
        assert result.get("team_b") == "PHI"
        assert result.get("win_prediction") is True

    def test_playoff_make_prediction(self):
        result = _extract_game_claim("Bears will make the playoffs in 2026")
        assert result.get("team_focus") == "CHI"
        assert result.get("playoff_prediction") is True

    def test_playoff_miss_prediction(self):
        result = _extract_game_claim("Browns will miss the playoffs in 2026")
        assert result.get("team_focus") == "CLE"
        assert result.get("playoff_prediction") is False

    def test_super_bowl_win_prediction(self):
        result = _extract_game_claim("Lions will win the Super Bowl in 2026")
        assert result.get("team_focus") == "DET"
        assert result.get("super_bowl_win") is True

    def test_season_year_extracted(self):
        result = _extract_game_claim("Chiefs beat Ravens in 2025")
        assert result.get("season_year") == 2025

    def test_unparseable_returns_empty(self):
        result = _extract_game_claim(
            "The game will be close but someone will win eventually"
        )
        # No team identified → no structured output
        assert "team_a" not in result

    def test_commanders_playoff_prediction(self):
        result = _extract_game_claim("Commanders will make the playoffs in 2026")
        assert result.get("team_focus") == "WAS"
        assert result.get("playoff_prediction") is True

    def test_washington_playoff_prediction(self):
        result = _extract_game_claim("Washington will miss the playoffs in 2026")
        assert result.get("team_focus") == "WAS"
        assert result.get("playoff_prediction") is False


# ---------------------------------------------------------------------------
# _extract_player_stat_claim
# ---------------------------------------------------------------------------


class TestExtractPlayerStatClaim:
    def test_passing_yards(self):
        result = _extract_player_stat_claim(
            "Patrick Mahomes throws 5000+ passing yards in 2026"
        )
        assert result.get("stat_column") == "PassingYards"
        assert result.get("threshold") == 5000
        assert result.get("operator") == ">="

    def test_passing_tds(self):
        result = _extract_player_stat_claim("Josh Allen throws 40+ passing TDs in 2026")
        assert result.get("stat_column") in ("PassingTouchdowns", "PassingTDs")
        # stat_column should be one of the mapped aliases
        assert result.get("threshold") == 40

    def test_receiving_yards(self):
        result = _extract_player_stat_claim(
            "CeeDee Lamb records 1500 receiving yards in 2026"
        )
        assert result.get("stat_column") == "ReceivingYards"
        assert result.get("threshold") == 1500

    def test_rushing_yards(self):
        result = _extract_player_stat_claim(
            "Derrick Henry rushes for 1200+ yards in 2026"
        )
        assert result.get("stat_column") == "RushingYards"
        assert result.get("threshold") == 1200

    def test_fewer_than_operator(self):
        result = _extract_player_stat_claim(
            "Justin Fields throws fewer than 10 passing touchdowns in 2026"
        )
        assert result.get("threshold") == 10
        assert result.get("operator") == "<"

    def test_season_year_extracted(self):
        result = _extract_player_stat_claim("Mahomes passes for 4800 yards in 2025")
        assert result.get("season_year") == 2025

    def test_player_name_extracted(self):
        result = _extract_player_stat_claim(
            "Patrick Mahomes throws 45 passing TDs in 2026"
        )
        assert result.get("player_name") == "Patrick Mahomes"

    def test_no_stat_returns_incomplete(self):
        result = _extract_player_stat_claim("Mahomes will be great in 2026")
        assert "stat_column" not in result or "threshold" not in result


# ---------------------------------------------------------------------------
# resolve_game_outcomes
# ---------------------------------------------------------------------------


_SCORES_2024 = pd.DataFrame(
    [
        {
            "HomeTeam": "KC",
            "AwayTeam": "PHI",
            "Season": 2024,
            "Week": 11,
            "HomeScore": 21,
            "AwayScore": 17,
            "IsPlayoffGame": False,
        }
    ]
)

_SCORES_2024_EAGLES_WIN = pd.DataFrame(
    [
        {
            "HomeTeam": "PHI",
            "AwayTeam": "KC",
            "Season": 2024,
            "Week": 11,
            "HomeScore": 24,
            "AwayScore": 14,
            "IsPlayoffGame": False,
        }
    ]
)

_BEARS_PLAYOFF_2024 = pd.DataFrame(
    [
        {
            "HomeTeam": "CHI",
            "AwayTeam": "GB",
            "Season": 2024,
            "Week": 18,
            "HomeScore": 27,
            "AwayScore": 20,
            "IsPlayoffGame": True,
        }
    ]
)


class TestResolveGameOutcomes:
    @patch("src.resolve_daily._load_game_scores")
    @patch("src.resolve_daily.get_pending_predictions")
    @patch("src.resolve_daily.resolve_binary")
    def test_correct_win_prediction(
        self, mock_resolve, mock_pending, mock_load, mock_db
    ):
        """Chiefs beat Eagles correctly resolved when Chiefs won."""
        preds = _make_pending_df(
            "game_outcome",
            [{"claim": "Chiefs beat Eagles in 2024", "season_year": 2024}],
        )
        mock_pending.return_value = preds
        mock_load.return_value = _SCORES_2024

        summary = resolve_game_outcomes(mock_db, dry_run=False)

        assert summary["resolved"] == 1
        call_kwargs = mock_resolve.call_args[1]
        assert call_kwargs["correct"] is True

    @patch("src.resolve_daily._load_game_scores")
    @patch("src.resolve_daily.get_pending_predictions")
    @patch("src.resolve_daily.resolve_binary")
    def test_incorrect_win_prediction(
        self, mock_resolve, mock_pending, mock_load, mock_db
    ):
        """Chiefs beat Eagles incorrectly when Eagles actually won."""
        preds = _make_pending_df(
            "game_outcome",
            [{"claim": "Chiefs beat Eagles in 2024", "season_year": 2024}],
        )
        mock_pending.return_value = preds
        mock_load.return_value = _SCORES_2024_EAGLES_WIN

        summary = resolve_game_outcomes(mock_db, dry_run=False)

        assert summary["resolved"] == 1
        call_kwargs = mock_resolve.call_args[1]
        assert call_kwargs["correct"] is False

    @patch("src.resolve_daily.get_pending_predictions")
    def test_skips_current_season(self, mock_pending, mock_db):
        """Predictions for the current (incomplete) season are skipped."""
        current_year = pd.Timestamp.now().year
        preds = _make_pending_df(
            "game_outcome",
            [
                {
                    "claim": f"Chiefs beat Eagles in {current_year}",
                    "season_year": current_year,
                }
            ],
        )
        mock_pending.return_value = preds

        summary = resolve_game_outcomes(mock_db, dry_run=False)

        assert summary["skipped"] == 1
        assert summary["resolved"] == 0

    @patch("src.resolve_daily._load_game_scores")
    @patch("src.resolve_daily.get_pending_predictions")
    def test_skips_missing_data(self, mock_pending, mock_load, mock_db):
        """Predictions skipped gracefully when scores table returns empty."""
        preds = _make_pending_df(
            "game_outcome",
            [{"claim": "Chiefs beat Eagles in 2024", "season_year": 2024}],
        )
        mock_pending.return_value = preds
        mock_load.return_value = pd.DataFrame()

        summary = resolve_game_outcomes(mock_db, dry_run=False)

        assert summary["skipped"] == 1

    @patch("src.resolve_daily._load_game_scores")
    @patch("src.resolve_daily.get_pending_predictions")
    @patch("src.resolve_daily.void_prediction")
    def test_voids_unparseable_claim(self, mock_void, mock_pending, mock_load, mock_db):
        """Claims that can't be parsed are voided."""
        preds = _make_pending_df(
            "game_outcome",
            [{"claim": "The game will be entertaining in 2024", "season_year": 2024}],
        )
        mock_pending.return_value = preds
        mock_load.return_value = _SCORES_2024

        summary = resolve_game_outcomes(mock_db, dry_run=False)

        assert summary["voided"] == 1

    @patch("src.resolve_daily._load_game_scores")
    @patch("src.resolve_daily.get_pending_predictions")
    @patch("src.resolve_daily.resolve_binary")
    def test_playoff_make_correct(self, mock_resolve, mock_pending, mock_load, mock_db):
        """Bears making playoffs correctly resolved when Bears appear in playoff games."""
        preds = _make_pending_df(
            "game_outcome",
            [{"claim": "Bears will make the playoffs in 2024", "season_year": 2024}],
        )
        mock_pending.return_value = preds
        mock_load.return_value = _BEARS_PLAYOFF_2024

        summary = resolve_game_outcomes(mock_db, dry_run=False)

        assert summary["resolved"] == 1
        call_kwargs = mock_resolve.call_args[1]
        assert call_kwargs["correct"] is True

    @patch("src.resolve_daily.get_pending_predictions")
    def test_empty_predictions(self, mock_pending, mock_db):
        mock_pending.return_value = pd.DataFrame(
            columns=[
                "prediction_hash",
                "extracted_claim",
                "claim_category",
                "season_year",
            ]
        )
        summary = resolve_game_outcomes(mock_db, dry_run=False)
        assert summary["checked"] == 0


# ---------------------------------------------------------------------------
# resolve_player_performance
# ---------------------------------------------------------------------------


_MAHOMES_STATS_2024 = pd.DataFrame(
    [
        {
            "Name": "Patrick Mahomes",
            "Season": 2024,
            "PassingYards": 5100,
            "PassingTouchdowns": 41,
            "Interceptions": 11,
            "RushingYards": 360,
            "RushingTouchdowns": 4,
            "ReceivingYards": None,
            "ReceivingTouchdowns": None,
            "Receptions": None,
            "Sacks": None,
            "Tackles": None,
        }
    ]
)

_MAHOMES_LOW_STATS_2024 = pd.DataFrame(
    [
        {
            "Name": "Patrick Mahomes",
            "Season": 2024,
            "PassingYards": 4200,
            "PassingTouchdowns": 35,
            "Interceptions": 10,
            "RushingYards": 290,
            "RushingTouchdowns": 3,
            "ReceivingYards": None,
            "ReceivingTouchdowns": None,
            "Receptions": None,
            "Sacks": None,
            "Tackles": None,
        }
    ]
)


class TestResolvePlayerPerformance:
    @patch("src.resolve_daily._load_player_season_stats")
    @patch("src.resolve_daily.get_pending_predictions")
    @patch("src.resolve_daily.resolve_binary")
    def test_correct_stat_prediction(
        self, mock_resolve, mock_pending, mock_load, mock_db
    ):
        """Mahomes throws 5000+ yards — correct when actual is 5100."""
        preds = _make_pending_df(
            "player_performance",
            [
                {
                    "claim": "Patrick Mahomes throws 5000+ passing yards in 2024",
                    "season_year": 2024,
                    "player_name": "Patrick Mahomes",
                }
            ],
        )
        mock_pending.return_value = preds
        mock_load.return_value = _MAHOMES_STATS_2024

        summary = resolve_player_performance(mock_db, dry_run=False)

        assert summary["resolved"] == 1
        call_kwargs = mock_resolve.call_args[1]
        assert call_kwargs["correct"] is True

    @patch("src.resolve_daily._load_player_season_stats")
    @patch("src.resolve_daily.get_pending_predictions")
    @patch("src.resolve_daily.resolve_binary")
    def test_incorrect_stat_prediction(
        self, mock_resolve, mock_pending, mock_load, mock_db
    ):
        """Mahomes throws 5000+ yards — incorrect when actual is 4200."""
        preds = _make_pending_df(
            "player_performance",
            [
                {
                    "claim": "Patrick Mahomes throws 5000+ passing yards in 2024",
                    "season_year": 2024,
                    "player_name": "Patrick Mahomes",
                }
            ],
        )
        mock_pending.return_value = preds
        mock_load.return_value = _MAHOMES_LOW_STATS_2024

        summary = resolve_player_performance(mock_db, dry_run=False)

        assert summary["resolved"] == 1
        call_kwargs = mock_resolve.call_args[1]
        assert call_kwargs["correct"] is False

    @patch("src.resolve_daily.get_pending_predictions")
    def test_skips_current_season(self, mock_pending, mock_db):
        """Incomplete seasons are skipped."""
        current_year = pd.Timestamp.now().year
        preds = _make_pending_df(
            "player_performance",
            [
                {
                    "claim": f"Mahomes throws 5000 yards in {current_year}",
                    "season_year": current_year,
                }
            ],
        )
        mock_pending.return_value = preds

        summary = resolve_player_performance(mock_db, dry_run=False)

        assert summary["skipped"] == 1
        assert summary["resolved"] == 0

    @patch("src.resolve_daily._load_player_season_stats")
    @patch("src.resolve_daily.get_pending_predictions")
    def test_skips_missing_stats_data(self, mock_pending, mock_load, mock_db):
        """Skips gracefully when stats table is empty."""
        preds = _make_pending_df(
            "player_performance",
            [
                {
                    "claim": "Mahomes throws 5000 passing yards in 2024",
                    "season_year": 2024,
                    "player_name": "Patrick Mahomes",
                }
            ],
        )
        mock_pending.return_value = preds
        mock_load.return_value = pd.DataFrame()

        summary = resolve_player_performance(mock_db, dry_run=False)

        assert summary["skipped"] == 1

    @patch("src.resolve_daily._load_player_season_stats")
    @patch("src.resolve_daily.get_pending_predictions")
    @patch("src.resolve_daily.void_prediction")
    def test_voids_unparseable_stat_claim(
        self, mock_void, mock_pending, mock_load, mock_db
    ):
        """Claims without a parseable stat threshold are voided."""
        preds = _make_pending_df(
            "player_performance",
            [
                {
                    "claim": "Mahomes will be great in 2024",
                    "season_year": 2024,
                    "player_name": "Patrick Mahomes",
                }
            ],
        )
        mock_pending.return_value = preds
        mock_load.return_value = _MAHOMES_STATS_2024

        summary = resolve_player_performance(mock_db, dry_run=False)

        assert summary["voided"] == 1

    @patch("src.resolve_daily._load_player_season_stats")
    @patch("src.resolve_daily.get_pending_predictions")
    def test_skips_player_not_found(self, mock_pending, mock_load, mock_db):
        """Skips when player name not found in stats table."""
        preds = _make_pending_df(
            "player_performance",
            [
                {
                    "claim": "Joe Schmoe throws 5000 passing yards in 2024",
                    "season_year": 2024,
                    "player_name": "Joe Schmoe",
                }
            ],
        )
        mock_pending.return_value = preds
        mock_load.return_value = _MAHOMES_STATS_2024  # Only Mahomes in table

        summary = resolve_player_performance(mock_db, dry_run=False)

        assert summary["skipped"] == 1

    @patch("src.resolve_daily.get_pending_predictions")
    def test_empty_predictions(self, mock_pending, mock_db):
        mock_pending.return_value = pd.DataFrame(
            columns=[
                "prediction_hash",
                "extracted_claim",
                "claim_category",
                "season_year",
            ]
        )
        summary = resolve_player_performance(mock_db, dry_run=False)
        assert summary["checked"] == 0


# _extract_draft_claim
# ---------------------------------------------------------------------------


class TestExtractDraftClaim:
    def test_numeric_pick_format(self):
        result = _extract_draft_claim(
            "Will Anderson Jr. is the No. 3 overall pick in 2023"
        )
        assert result["pick_number"] == 3
        assert result["draft_year"] == 2023

    def test_hash_pick_format(self):
        result = _extract_draft_claim("CJ Stroud goes at #2 pick in 2023")
        assert result["pick_number"] == 2

    def test_ordinal_first_overall(self):
        result = _extract_draft_claim(
            "Caleb Williams will be the first overall pick in 2024"
        )
        assert result["pick_number"] == 1

    def test_ordinal_third_pick(self):
        result = _extract_draft_claim("Drake Maye is the third pick in 2024")
        assert result["pick_number"] == 3

    def test_top_n_extraction(self):
        result = _extract_draft_claim("Jayden Daniels will be a top-5 pick in 2024")
        assert result["top_n"] == 5

    def test_top_10_extraction(self):
        result = _extract_draft_claim("J.J. McCarthy goes in the top-10 picks of 2024")
        assert result["top_n"] == 10

    def test_round_number_extraction(self):
        result = _extract_draft_claim("Player X is a Round 2 pick in 2024")
        assert result["round_number"] == 2

    def test_first_round_text(self):
        result = _extract_draft_claim("Michael Penix Jr. is a first round pick in 2024")
        assert result["round_number"] == 1

    def test_year_extraction(self):
        result = _extract_draft_claim("Top QB prospect in the 2025 NFL draft")
        assert result["draft_year"] == 2025

    def test_no_year_in_claim(self):
        result = _extract_draft_claim("Will Anderson Jr. is the #3 overall pick")
        assert "draft_year" not in result
        assert result["pick_number"] == 3

    def test_unparseable_returns_empty(self):
        result = _extract_draft_claim("This player will do well in football")
        assert result == {}

    def test_pick_and_year_combined(self):
        result = _extract_draft_claim(
            "Bryce Young is the No. 1 overall pick in the 2023 NFL Draft"
        )
        assert result["pick_number"] == 1
        assert result["draft_year"] == 2023


# ---------------------------------------------------------------------------
# resolve_draft_picks
# ---------------------------------------------------------------------------

_DRAFT_DATA_2024 = pd.DataFrame(
    [
        {
            "Name": "Caleb Williams",
            "name_lower": "caleb williams",
            "draft_year": 2024,
            "draft_round": 1,
            "draft_pick": 1,
            "draft_team": "CHI",
            "current_team": "CHI",
            "undrafted": False,
        },
        {
            "Name": "Jayden Daniels",
            "name_lower": "jayden daniels",
            "draft_year": 2024,
            "draft_round": 1,
            "draft_pick": 2,
            "draft_team": "WAS",
            "current_team": "WAS",
            "undrafted": False,
        },
        {
            "Name": "Drake Maye",
            "name_lower": "drake maye",
            "draft_year": 2024,
            "draft_round": 1,
            "draft_pick": 3,
            "draft_team": "NE",
            "current_team": "NE",
            "undrafted": False,
        },
        {
            "Name": "Marvin Harrison Jr.",
            "name_lower": "marvin harrison jr.",
            "draft_year": 2024,
            "draft_round": 1,
            "draft_pick": 4,
            "draft_team": "ARI",
            "current_team": "ARI",
            "undrafted": False,
        },
    ]
)


class TestResolveDraftPicks:
    @patch("src.resolve_daily._load_draft_data")
    @patch("src.resolve_daily.get_pending_predictions")
    @patch("src.resolve_daily.resolve_binary")
    def test_correct_pick_number(self, mock_resolve, mock_pending, mock_load, mock_db):
        """Caleb Williams predicted as #1 pick — correct when he was actually pick #1."""
        preds = _make_pending_df(
            "draft_pick",
            [
                {
                    "claim": "Caleb Williams is the No. 1 overall pick in 2024",
                    "season_year": 2024,
                    "target_player_id": "Caleb Williams",
                }
            ],
        )
        mock_pending.return_value = preds
        mock_load.return_value = _DRAFT_DATA_2024

        summary = resolve_draft_picks(mock_db, dry_run=False)

        assert summary["resolved"] == 1
        assert summary["skipped"] == 0
        call_kwargs = mock_resolve.call_args[1]
        assert call_kwargs["correct"] is True

    @patch("src.resolve_daily._load_draft_data")
    @patch("src.resolve_daily.get_pending_predictions")
    @patch("src.resolve_daily.resolve_binary")
    def test_incorrect_pick_number(
        self, mock_resolve, mock_pending, mock_load, mock_db
    ):
        """Drake Maye predicted as #1 pick — incorrect (actual pick #3)."""
        preds = _make_pending_df(
            "draft_pick",
            [
                {
                    "claim": "Drake Maye is the No. 1 overall pick in 2024",
                    "season_year": 2024,
                    "target_player_id": "Drake Maye",
                }
            ],
        )
        mock_pending.return_value = preds
        mock_load.return_value = _DRAFT_DATA_2024

        summary = resolve_draft_picks(mock_db, dry_run=False)

        assert summary["resolved"] == 1
        call_kwargs = mock_resolve.call_args[1]
        assert call_kwargs["correct"] is False

    @patch("src.resolve_daily._load_draft_data")
    @patch("src.resolve_daily.get_pending_predictions")
    @patch("src.resolve_daily.resolve_binary")
    def test_correct_top_n_prediction(
        self, mock_resolve, mock_pending, mock_load, mock_db
    ):
        """Marvin Harrison Jr. predicted as top-5 — correct (actual pick #4)."""
        preds = _make_pending_df(
            "draft_pick",
            [
                {
                    "claim": "Marvin Harrison Jr. will be a top-5 pick in 2024",
                    "season_year": 2024,
                    "target_player_id": "Marvin Harrison Jr.",
                }
            ],
        )
        mock_pending.return_value = preds
        mock_load.return_value = _DRAFT_DATA_2024

        summary = resolve_draft_picks(mock_db, dry_run=False)

        assert summary["resolved"] == 1
        call_kwargs = mock_resolve.call_args[1]
        assert call_kwargs["correct"] is True

    @patch("src.resolve_daily._load_draft_data")
    @patch("src.resolve_daily.get_pending_predictions")
    @patch("src.resolve_daily.resolve_binary")
    def test_correct_round_prediction(
        self, mock_resolve, mock_pending, mock_load, mock_db
    ):
        """Drake Maye predicted as first round pick — correct (actual round 1)."""
        preds = _make_pending_df(
            "draft_pick",
            [
                {
                    "claim": "Drake Maye is a first round pick in 2024",
                    "season_year": 2024,
                    "target_player_id": "Drake Maye",
                }
            ],
        )
        mock_pending.return_value = preds
        mock_load.return_value = _DRAFT_DATA_2024

        summary = resolve_draft_picks(mock_db, dry_run=False)

        assert summary["resolved"] == 1
        call_kwargs = mock_resolve.call_args[1]
        assert call_kwargs["correct"] is True

    @patch("src.resolve_daily._load_draft_data")
    @patch("src.resolve_daily.get_pending_predictions")
    def test_skip_no_draft_year_in_claim_or_metadata(
        self, mock_pending, mock_load, mock_db
    ):
        """Skip predictions with no year in claim and no season_year."""
        rows = _make_pending_df(
            "draft_pick",
            [
                {
                    "claim": "Someone will be the #1 pick",
                    "season_year": None,
                    "target_player_id": "Some Player",
                }
            ],
        )
        mock_pending.return_value = rows
        mock_load.return_value = _DRAFT_DATA_2024

        summary = resolve_draft_picks(mock_db, dry_run=False)

        assert summary["skipped"] == 1
        assert summary["resolved"] == 0

    @patch("src.resolve_daily._load_draft_data")
    @patch("src.resolve_daily.get_pending_predictions")
    @patch("src.resolve_daily.resolve_binary")
    def test_season_year_used_as_draft_year_fallback(
        self, mock_resolve, mock_pending, mock_load, mock_db
    ):
        """season_year is used as draft year when not present in claim text."""
        preds = _make_pending_df(
            "draft_pick",
            [
                {
                    "claim": "Caleb Williams is the No. 1 overall pick",
                    "season_year": 2024,
                    "target_player_id": "Caleb Williams",
                }
            ],
        )
        mock_pending.return_value = preds
        mock_load.return_value = _DRAFT_DATA_2024

        summary = resolve_draft_picks(mock_db, dry_run=False)

        assert summary["resolved"] == 1

    @patch("src.resolve_daily._load_draft_data")
    @patch("src.resolve_daily.get_pending_predictions")
    def test_skip_future_draft_year(self, mock_pending, mock_load, mock_db):
        """Skip predictions for future draft years (data not available yet)."""
        future_year = pd.Timestamp.now().year + 1
        preds = _make_pending_df(
            "draft_pick",
            [
                {
                    "claim": f"Top QB will be the #1 pick in {future_year}",
                    "season_year": future_year,
                }
            ],
        )
        mock_pending.return_value = preds
        mock_load.return_value = _DRAFT_DATA_2024  # Has 2024 data, not future year

        summary = resolve_draft_picks(mock_db, dry_run=False)

        assert summary["skipped"] == 1

    @patch("src.resolve_daily._load_draft_data")
    @patch("src.resolve_daily.get_pending_predictions")
    def test_skip_player_not_found_in_draft_data(
        self, mock_pending, mock_load, mock_db
    ):
        """Skip when the predicted player isn't in the draft data."""
        preds = _make_pending_df(
            "draft_pick",
            [
                {
                    "claim": "John Nobody is the #5 pick in 2024",
                    "season_year": 2024,
                    "target_player_id": "John Nobody",
                }
            ],
        )
        mock_pending.return_value = preds
        mock_load.return_value = _DRAFT_DATA_2024

        summary = resolve_draft_picks(mock_db, dry_run=False)

        assert summary["skipped"] == 1
        assert summary["resolved"] == 0

    @patch("src.resolve_daily._load_draft_data")
    @patch("src.resolve_daily.get_pending_predictions")
    def test_return_early_when_no_draft_data(self, mock_pending, mock_load, mock_db):
        """Return with 0 checked when the draft data table is empty."""
        preds = _make_pending_df(
            "draft_pick",
            [{"claim": "Caleb Williams is the #1 pick in 2024", "season_year": 2024}],
        )
        mock_pending.return_value = preds
        mock_load.return_value = pd.DataFrame()

        summary = resolve_draft_picks(mock_db, dry_run=False)

        assert summary["checked"] == 0

    @patch("src.resolve_daily._load_draft_data")
    @patch("src.resolve_daily.get_pending_predictions")
    @patch("src.resolve_daily.void_prediction")
    def test_void_when_claim_has_no_pick_structure(
        self, mock_void, mock_pending, mock_load, mock_db
    ):
        """Void when player is found but claim has no pick number, round, or top-N."""
        preds = _make_pending_df(
            "draft_pick",
            [
                {
                    "claim": "Caleb Williams will have an impact in 2024",
                    "season_year": 2024,
                    "target_player_id": "Caleb Williams",
                }
            ],
        )
        mock_pending.return_value = preds
        mock_load.return_value = _DRAFT_DATA_2024

        summary = resolve_draft_picks(mock_db, dry_run=False)

        assert summary["voided"] == 1
        mock_void.assert_called_once()

    @patch("src.resolve_daily.get_pending_predictions")
    def test_empty_predictions(self, mock_pending, mock_db):
        """Return 0 checked when there are no draft_pick predictions."""
        mock_pending.return_value = pd.DataFrame(
            columns=[
                "prediction_hash",
                "extracted_claim",
                "claim_category",
                "season_year",
            ]
        )
        summary = resolve_draft_picks(mock_db, dry_run=False)
        assert summary["checked"] == 0


# ---------------------------------------------------------------------------
# _resolve_team_claim
# ---------------------------------------------------------------------------


_YEAR_DRAFT_DATA_2026 = pd.DataFrame(
    [
        {
            "Name": "Travis Hunter",
            "name_lower": "travis hunter",
            "draft_year": 2026,
            "draft_round": 1,
            "draft_pick": 2,
            "draft_team": "NYG",
        },
        {
            "Name": "Shedeur Sanders",
            "name_lower": "shedeur sanders",
            "draft_year": 2026,
            "draft_round": 1,
            "draft_pick": 5,
            "draft_team": "CLE",
        },
        {
            "Name": "Ashton Jeanty",
            "name_lower": "ashton jeanty",
            "draft_year": 2026,
            "draft_round": 1,
            "draft_pick": 6,
            "draft_team": "LV",
        },
        {
            "Name": "Mason Graham",
            "name_lower": "mason graham",
            "draft_year": 2026,
            "draft_round": 1,
            "draft_pick": 3,
            "draft_team": "CLE",
        },
    ]
)


class TestResolveTeamClaim:
    def test_no_team_in_claim_returns_none(self, mock_db):
        """Claims with no recognizable team are returned as None."""
        result = _resolve_team_claim(
            claim="Someone will have two top-10 picks",
            parsed={},
            year_draft_data=_YEAR_DRAFT_DATA_2026,
            phash=FAKE_HASH,
            db=mock_db,
            dry_run=True,
        )
        assert result is None

    def test_qb_claim_returns_none(self, mock_db):
        """QB position claims can't be verified from draft data — returns None."""
        result = _resolve_team_claim(
            claim="Browns will pick a quarterback in Round 1",
            parsed={},
            year_draft_data=_YEAR_DRAFT_DATA_2026,
            phash=FAKE_HASH,
            db=mock_db,
            dry_run=True,
        )
        assert result is None

    @patch("src.resolve_daily.resolve_binary")
    def test_two_top_picks_correct(self, mock_resolve, mock_db):
        """Team with two picks in top-10 resolves as CORRECT."""
        result = _resolve_team_claim(
            claim="Browns will have two top-10 picks in the 2026 draft",
            parsed={},
            year_draft_data=_YEAR_DRAFT_DATA_2026,
            phash=FAKE_HASH,
            db=mock_db,
            dry_run=False,
        )
        assert result == "resolved"
        # resolve_binary(phash, correct, ...) — correct is positional arg [1]
        assert mock_resolve.call_args[0][1] is True

    @patch("src.resolve_daily.resolve_binary")
    def test_two_top_picks_incorrect(self, mock_resolve, mock_db):
        """Team with only one top-10 pick resolves as INCORRECT when two expected."""
        result = _resolve_team_claim(
            claim="Raiders will have two top-10 picks in the draft",
            parsed={},
            year_draft_data=_YEAR_DRAFT_DATA_2026,
            phash=FAKE_HASH,
            db=mock_db,
            dry_run=False,
        )
        assert result == "resolved"
        # resolve_binary(phash, correct, ...) — correct is positional arg [1]
        assert mock_resolve.call_args[0][1] is False

    @patch("src.resolve_daily.resolve_binary")
    def test_dry_run_does_not_call_resolve_binary(self, mock_resolve, mock_db):
        """dry_run=True suppresses the resolve_binary write."""
        _resolve_team_claim(
            claim="Browns will have two top-10 picks in the 2026 draft",
            parsed={},
            year_draft_data=_YEAR_DRAFT_DATA_2026,
            phash=FAKE_HASH,
            db=mock_db,
            dry_run=True,
        )
        mock_resolve.assert_not_called()

    def test_unrecognized_team_pattern_returns_none(self, mock_db):
        """Team found but no resolvable claim pattern → None."""
        result = _resolve_team_claim(
            claim="The Giants will do well in the draft this year",
            parsed={},
            year_draft_data=_YEAR_DRAFT_DATA_2026,
            phash=FAKE_HASH,
            db=mock_db,
            dry_run=True,
        )
        assert result is None
