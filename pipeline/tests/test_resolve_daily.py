"""
Tests for the Daily Prediction Resolution Engine (Issue #191).
Unit tests — no BigQuery required. All DB calls are mocked.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.resolve_daily import (
    _dual_write_silver_v2_resolution,
    _extract_draft_claim,
    _extract_game_claim,
    _extract_player_stat_claim,
    _normalize_name,
    _normalize_team,
    _resolve_binary_with_dual_write,
    _resolve_team_claim,
    _silver_v2_resolution_method_id,
    _void_prediction_with_dual_write,
    expire_stale_predictions,
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
        assert result.get("stat_column") == "passing_yards"
        assert result.get("threshold") == 5000
        assert result.get("operator") == ">="

    def test_passing_tds(self):
        result = _extract_player_stat_claim("Josh Allen throws 40+ passing TDs in 2026")
        assert result.get("stat_column") in ("passing_tds", "passing_touchdowns")
        # stat_column should be one of the mapped aliases
        assert result.get("threshold") == 40

    def test_receiving_yards(self):
        result = _extract_player_stat_claim(
            "CeeDee Lamb records 1500 receiving yards in 2026"
        )
        assert result.get("stat_column") == "receiving_yards"
        assert result.get("threshold") == 1500

    def test_rushing_yards(self):
        result = _extract_player_stat_claim(
            "Derrick Henry rushes for 1200+ yards in 2026"
        )
        assert result.get("stat_column") == "rushing_yards"
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
    @patch("src.resolve_daily._resolve_binary_with_dual_write")
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
    @patch("src.resolve_daily._resolve_binary_with_dual_write")
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
    @patch("src.resolve_daily._void_prediction_with_dual_write")
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
    @patch("src.resolve_daily._resolve_binary_with_dual_write")
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
            "passing_yards": 5100,
            "passing_tds": 41,
            "interceptions": 11,
            "rushing_yards": 360,
            "rushing_tds": 4,
            "receiving_yards": None,
            "receiving_tds": None,
            "receptions": None,
            "sacks": None,
        }
    ]
)

_MAHOMES_LOW_STATS_2024 = pd.DataFrame(
    [
        {
            "Name": "Patrick Mahomes",
            "Season": 2024,
            "passing_yards": 4200,
            "passing_tds": 35,
            "interceptions": 10,
            "rushing_yards": 290,
            "rushing_tds": 3,
            "receiving_yards": None,
            "receiving_tds": None,
            "receptions": None,
            "sacks": None,
        }
    ]
)


class TestResolvePlayerPerformance:
    @patch("src.resolve_daily._load_player_season_stats")
    @patch("src.resolve_daily.get_pending_predictions")
    @patch("src.resolve_daily._resolve_binary_with_dual_write")
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
    @patch("src.resolve_daily._resolve_binary_with_dual_write")
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
    @patch("src.resolve_daily._void_prediction_with_dual_write")
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


# ---------------------------------------------------------------------------
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
    @patch("src.resolve_daily._resolve_binary_with_dual_write")
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
    @patch("src.resolve_daily._resolve_binary_with_dual_write")
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
    @patch("src.resolve_daily._resolve_binary_with_dual_write")
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
    @patch("src.resolve_daily._resolve_binary_with_dual_write")
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
    @patch("src.resolve_daily._resolve_binary_with_dual_write")
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
    @patch("src.resolve_daily._void_prediction_with_dual_write")
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

    @patch("src.resolve_daily._load_draft_data")
    @patch("src.resolve_daily.get_pending_predictions")
    @patch("src.resolve_daily._resolve_binary_with_dual_write")
    def test_zero_indexed_picks_normalized(
        self, mock_resolve, mock_pending, mock_load, mock_db
    ):
        """SportsDataIO 0-indexed picks (round=0, pick=0 = #1 overall) are normalized to 1-indexed."""
        # Simulate SportsDataIO raw data: #1 overall stored as round=0, pick=0
        zero_indexed_data = pd.DataFrame(
            [
                {
                    "Name": "Fernando Mendoza",
                    "name_lower": "fernando mendoza",
                    "draft_year": 2025,
                    "draft_round": 0,  # SportsDataIO 0-indexed
                    "draft_pick": 0,  # SportsDataIO 0-indexed — means pick #1
                    "draft_team": "CLE",
                    "current_team": "CLE",
                    "undrafted": False,
                },
                {
                    "Name": "Arvell Reese",
                    "name_lower": "arvell reese",
                    "draft_year": 2025,
                    "draft_round": 0,  # SportsDataIO 0-indexed
                    "draft_pick": 2,  # SportsDataIO 0-indexed — means pick #3
                    "draft_team": "NYG",
                    "current_team": "NYG",
                    "undrafted": False,
                },
            ]
        )
        preds = _make_pending_df(
            "draft_pick",
            [
                {
                    "claim": "Fernando Mendoza is the No. 1 overall pick in 2025",
                    "season_year": 2025,
                    "target_player_id": "Fernando Mendoza",
                }
            ],
        )
        mock_pending.return_value = preds
        mock_load.return_value = zero_indexed_data

        summary = resolve_draft_picks(mock_db, dry_run=False)

        # Should resolve (not skip) because pick 0 is normalized to 1
        assert summary["resolved"] == 1
        assert summary["skipped"] == 0
        call_kwargs = mock_resolve.call_args[1]
        assert call_kwargs["correct"] is True

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

    # -----------------------------------------------------------------------
    # Fuzzy-match regression tests (issue #997)
    # -----------------------------------------------------------------------

    @patch("src.resolve_daily._load_draft_data")
    @patch("src.resolve_daily.get_pending_predictions")
    @patch("src.resolve_daily._resolve_binary_with_dual_write")
    def test_fuzzy_within3_team_matches_is_correct(
        self, mock_resolve, mock_pending, mock_load, mock_db
    ):
        """Predicted pick #38 for NE, actual pick #39 by NE → CORRECT (±1, team match).

        Regression for issue #997: post-event tracker off-by-one was marking
        correct predictions as INCORRECT.
        """
        # Build a player drafted at #39 by NE
        fuzzy_data = pd.DataFrame(
            [
                {
                    "Name": "John Doe",
                    "name_lower": "john doe",
                    "draft_year": 2026,
                    "draft_round": 2,
                    "draft_pick": 39,
                    "draft_team": "NE",
                    "current_team": "NE",
                    "undrafted": False,
                }
            ]
        )
        preds = _make_pending_df(
            "draft_pick",
            [
                {
                    "claim": "John Doe drafted by Patriots at pick No. 38 in 2026",
                    "season_year": 2026,
                    "target_player_id": "John Doe",
                }
            ],
        )
        mock_pending.return_value = preds
        mock_load.return_value = fuzzy_data

        summary = resolve_draft_picks(mock_db, dry_run=False)

        assert summary["resolved"] == 1
        call_kwargs = mock_resolve.call_args[1]
        assert call_kwargs["correct"] is True, (
            "pick #38 vs actual #39 with matching team should be CORRECT (fuzzy ±3)"
        )

    @patch("src.resolve_daily._load_draft_data")
    @patch("src.resolve_daily.get_pending_predictions")
    @patch("src.resolve_daily._resolve_binary_with_dual_write")
    def test_fuzzy_within3_wrong_team_is_incorrect(
        self, mock_resolve, mock_pending, mock_load, mock_db
    ):
        """Predicted pick #38 for CHI, actual pick #39 by NE → INCORRECT (team mismatch).

        Even a ±1 pick delta should not flip to CORRECT when the team is wrong.
        """
        fuzzy_data = pd.DataFrame(
            [
                {
                    "Name": "John Doe",
                    "name_lower": "john doe",
                    "draft_year": 2026,
                    "draft_round": 2,
                    "draft_pick": 39,
                    "draft_team": "NE",
                    "current_team": "NE",
                    "undrafted": False,
                }
            ]
        )
        preds = _make_pending_df(
            "draft_pick",
            [
                {
                    # Claim says Bears (#38), actual is Patriots (#39)
                    "claim": "John Doe drafted by Bears at pick No. 38 in 2026",
                    "season_year": 2026,
                    "target_player_id": "John Doe",
                }
            ],
        )
        mock_pending.return_value = preds
        mock_load.return_value = fuzzy_data

        summary = resolve_draft_picks(mock_db, dry_run=False)

        assert summary["resolved"] == 1
        call_kwargs = mock_resolve.call_args[1]
        assert call_kwargs["correct"] is False, (
            "pick delta ±1 with team mismatch should remain INCORRECT"
        )

    @patch("src.resolve_daily._load_draft_data")
    @patch("src.resolve_daily.get_pending_predictions")
    @patch("src.resolve_daily._resolve_binary_with_dual_write")
    def test_fuzzy_beyond3_team_matches_is_incorrect(
        self, mock_resolve, mock_pending, mock_load, mock_db
    ):
        """Predicted pick #32 for NE, actual pick #39 by NE → INCORRECT (delta=7 > ±3).

        Pick delta > 3 is a real prediction error even when the team matches.
        """
        fuzzy_data = pd.DataFrame(
            [
                {
                    "Name": "Jane Smith",
                    "name_lower": "jane smith",
                    "draft_year": 2026,
                    "draft_round": 1,
                    "draft_pick": 39,
                    "draft_team": "NE",
                    "current_team": "NE",
                    "undrafted": False,
                }
            ]
        )
        preds = _make_pending_df(
            "draft_pick",
            [
                {
                    "claim": "Jane Smith drafted by Patriots at pick No. 32 in 2026",
                    "season_year": 2026,
                    "target_player_id": "Jane Smith",
                }
            ],
        )
        mock_pending.return_value = preds
        mock_load.return_value = fuzzy_data

        summary = resolve_draft_picks(mock_db, dry_run=False)

        assert summary["resolved"] == 1
        call_kwargs = mock_resolve.call_args[1]
        assert call_kwargs["correct"] is False, (
            "pick delta 7 (>±3) should remain INCORRECT even with team match"
        )

    @patch("src.resolve_daily._load_draft_data")
    @patch("src.resolve_daily.get_pending_predictions")
    @patch("src.resolve_daily._resolve_binary_with_dual_write")
    def test_fuzzy_exact3_team_matches_is_correct(
        self, mock_resolve, mock_pending, mock_load, mock_db
    ):
        """Predicted pick #36 for NE, actual pick #39 by NE → CORRECT (delta=3, boundary)."""
        fuzzy_data = pd.DataFrame(
            [
                {
                    "Name": "Boundary Case",
                    "name_lower": "boundary case",
                    "draft_year": 2026,
                    "draft_round": 2,
                    "draft_pick": 39,
                    "draft_team": "NE",
                    "current_team": "NE",
                    "undrafted": False,
                }
            ]
        )
        preds = _make_pending_df(
            "draft_pick",
            [
                {
                    "claim": "Boundary Case drafted by Patriots at pick No. 36 in 2026",
                    "season_year": 2026,
                    "target_player_id": "Boundary Case",
                }
            ],
        )
        mock_pending.return_value = preds
        mock_load.return_value = fuzzy_data

        summary = resolve_draft_picks(mock_db, dry_run=False)

        assert summary["resolved"] == 1
        call_kwargs = mock_resolve.call_args[1]
        assert call_kwargs["correct"] is True, (
            "pick delta exactly 3 with team match should be CORRECT (inclusive boundary)"
        )


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

    @patch("src.resolve_daily._resolve_binary_with_dual_write")
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
        # _resolve_binary_with_dual_write(phash, correct, ...) — correct is positional arg [1]
        assert mock_resolve.call_args[0][1] is True

    @patch("src.resolve_daily._resolve_binary_with_dual_write")
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
        # _resolve_binary_with_dual_write(phash, correct, ...) — correct is positional arg [1]
        assert mock_resolve.call_args[0][1] is False

    @patch("src.resolve_daily._resolve_binary_with_dual_write")
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

    def test_word_ordinal_sixteenth_overall(self):
        """'sixteenth overall' — new extended word ordinal."""
        result = _extract_draft_claim(
            "Kenyon Sadiq will go sixteenth overall in the 2026 NFL Draft"
        )
        assert result.get("pick_number") == 16

    def test_word_ordinal_twentieth_overall(self):
        """'twentieth overall' — new extended word ordinal at boundary."""
        result = _extract_draft_claim(
            "Player will be selected twentieth overall in the 2026 draft"
        )
        assert result.get("pick_number") == 20

    def test_numeric_ordinal_suffix_th_overall(self):
        """'16th overall' — numeric ordinal suffix pattern."""
        result = _extract_draft_claim(
            "Kenyon Sadiq will be picked 16th overall in the 2026 NFL Draft"
        )
        assert result.get("pick_number") == 16

    def test_numeric_ordinal_suffix_st_overall(self):
        """'21st overall' — st suffix."""
        result = _extract_draft_claim("Player will go 21st overall in the 2026 draft")
        assert result.get("pick_number") == 21

    def test_numeric_ordinal_suffix_nd_overall(self):
        """'2nd overall' — nd suffix."""
        result = _extract_draft_claim("Player selected 2nd overall in 2026")
        assert result.get("pick_number") == 2

    def test_numeric_ordinal_suffix_rd_overall(self):
        """'13th overall' — rd-adjacent th suffix."""
        result = _extract_draft_claim(
            "Ty Simpson will be picked by the Rams 13th overall in the 2026 draft"
        )
        assert result.get("pick_number") == 13

    def test_numeric_ordinal_suffix_with_pick(self):
        """'16th pick' — ordinal before 'pick' keyword."""
        result = _extract_draft_claim("Player goes as the 16th pick in 2026")
        assert result.get("pick_number") == 16

    def test_at_no_dot_in_the(self):
        """'at No. 20 in the' — 'at No.' pattern without 'pick' keyword."""
        result = _extract_draft_claim(
            "Makai Lemon will be selected by the Eagles at No. 20 in the 2026 draft"
        )
        assert result.get("pick_number") == 20

    def test_at_no_dot_overall_by(self):
        """'at No. 11 overall by' — 'No. N overall by' pattern."""
        result = _extract_draft_claim(
            "Caleb Downs was selected at No. 11 overall by the Dallas Cowboys"
        )
        assert result.get("pick_number") == 11

    def test_no_dot_in_the(self):
        """'No. 5 in the' — pattern without overall/pick."""
        result = _extract_draft_claim("Player selected No. 5 in the 2026 draft")
        assert result.get("pick_number") == 5


# ---------------------------------------------------------------------------
# expire_stale_predictions
# ---------------------------------------------------------------------------


class TestExpireStale:
    @patch("src.resolve_daily.void_prediction")
    def test_voids_all_stale_predictions(self, mock_void, mock_db):
        """3 stale predictions returned by DB are all voided with past_resolution_horizon."""
        stale_hashes = [f"{'c' * 60}{i:04d}" for i in range(3)]
        mock_db.fetch_df.return_value = pd.DataFrame({"prediction_hash": stale_hashes})

        count = expire_stale_predictions(mock_db, dry_run=False)

        assert count == 3
        assert mock_void.call_count == 3
        for call, phash in zip(mock_void.call_args_list, stale_hashes):
            args, kwargs = call
            assert args[0] == phash
            assert args[1] == "past_resolution_horizon"

    @patch("src.resolve_daily.void_prediction")
    def test_dry_run_does_not_void(self, mock_void, mock_db):
        """dry_run=True counts stale predictions but does not call void_prediction."""
        mock_db.fetch_df.return_value = pd.DataFrame(
            {"prediction_hash": ["a" * 64, "b" * 64]}
        )

        count = expire_stale_predictions(mock_db, dry_run=True)

        assert count == 2
        mock_void.assert_not_called()

    @patch("src.resolve_daily.void_prediction")
    def test_returns_zero_when_no_stale(self, mock_void, mock_db):
        """Returns 0 and calls no voids when DB returns empty DataFrame."""
        mock_db.fetch_df.return_value = pd.DataFrame(columns=["prediction_hash"])

        count = expire_stale_predictions(mock_db, dry_run=False)

        assert count == 0
        mock_void.assert_not_called()

    @patch("src.resolve_daily.void_prediction")
    def test_returns_zero_on_db_error(self, mock_void, mock_db):
        """Returns 0 gracefully when the DB query raises an exception."""
        mock_db.fetch_df.side_effect = Exception("BQ unavailable")

        count = expire_stale_predictions(mock_db, dry_run=False)

        assert count == 0
        mock_void.assert_not_called()


# ---------------------------------------------------------------------------
# Dual-write helpers (Issue #615)
# ---------------------------------------------------------------------------


class TestSilverV2ResolutionMethodId:
    """_silver_v2_resolution_method_id maps outcome_source → resolution_method_id."""

    def test_sportsdataio_maps_to_draft_pick(self):
        assert (
            _silver_v2_resolution_method_id("sportsdataio")
            == "nfl_draft_pick_sportsdataio"
        )

    def test_draft_board_maps_to_draft_pick(self):
        assert (
            _silver_v2_resolution_method_id("draft_board")
            == "nfl_draft_pick_sportsdataio"
        )

    def test_scores_maps_to_game_outcome(self):
        assert (
            _silver_v2_resolution_method_id("sportsdataio_scores")
            == "nfl_game_outcome_scores"
        )

    def test_nflverse_maps_to_player_perf(self):
        assert (
            _silver_v2_resolution_method_id("nflverse_player_stats")
            == "nfl_player_perf_nflverse"
        )

    def test_awards_config_maps_to_award(self):
        assert (
            _silver_v2_resolution_method_id("nfl_awards_config") == "nfl_award_config"
        )

    def test_rosters_maps_to_fa_signing(self):
        assert (
            _silver_v2_resolution_method_id("sportsdataio_rosters")
            == "nfl_fa_signing_rosters"
        )

    def test_unknown_source_returns_default(self):
        assert _silver_v2_resolution_method_id("unknown_source").startswith("nfl_")

    def test_none_returns_default(self):
        assert _silver_v2_resolution_method_id(None).startswith("nfl_")


class TestDualWriteSilverV2Resolution:
    """_dual_write_silver_v2_resolution writes to silver_v2_claims.resolution."""

    def _make_mock_db(self):
        db = MagicMock()
        # chain query returns empty (first resolution in chain)
        db.fetch_df.return_value = pd.DataFrame()
        db.execute.return_value = None
        return db

    def test_writes_true_outcome(self, monkeypatch):
        monkeypatch.setenv("GCP_PROJECT_ID", "test-project")
        db = self._make_mock_db()
        _dual_write_silver_v2_resolution(
            prediction_hash="a" * 64,
            outcome="true",
            outcome_confidence=1.0,
            evidence={"source": "sportsdataio"},
            resolution_method_id="nfl_draft_pick_sportsdataio",
            db=db,
        )
        db.execute.assert_called_once()
        # Verify the INSERT statement was constructed
        call_sql = db.execute.call_args[0][0]
        assert "INSERT INTO" in call_sql
        assert "silver_v2_claims.resolution" in call_sql

    def test_writes_false_outcome(self, monkeypatch):
        monkeypatch.setenv("GCP_PROJECT_ID", "test-project")
        db = self._make_mock_db()
        _dual_write_silver_v2_resolution(
            prediction_hash="b" * 64,
            outcome="false",
            outcome_confidence=0.9,
            evidence={"source": "nflverse_player_stats"},
            resolution_method_id="nfl_player_perf_nflverse",
            db=db,
        )
        db.execute.assert_called_once()

    def test_does_not_raise_on_db_error(self, monkeypatch):
        """v2 failure must not raise — issue #615 AC #4."""
        monkeypatch.setenv("GCP_PROJECT_ID", "test-project")
        db = self._make_mock_db()
        db.execute.side_effect = RuntimeError("BigQuery unavailable")
        # Should NOT raise
        _dual_write_silver_v2_resolution(
            prediction_hash="c" * 64,
            outcome="true",
            outcome_confidence=1.0,
            evidence={},
            resolution_method_id="nfl_draft_pick_sportsdataio",
            db=db,
        )

    def test_skips_when_no_project_id(self, monkeypatch):
        """When GCP_PROJECT_ID is unset, skip silently."""
        monkeypatch.delenv("GCP_PROJECT_ID", raising=False)
        db = self._make_mock_db()
        _dual_write_silver_v2_resolution(
            prediction_hash="d" * 64,
            outcome="unresolvable",
            outcome_confidence=1.0,
            evidence={},
            resolution_method_id="nfl_draft_pick_sportsdataio",
            db=db,
        )
        db.execute.assert_not_called()

    def test_uses_prev_hash_from_chain(self, monkeypatch):
        """When a prior resolution exists, prev_hash must be set from that row."""
        monkeypatch.setenv("GCP_PROJECT_ID", "test-project")
        db = self._make_mock_db()
        db.fetch_df.return_value = pd.DataFrame({"this_hash": ["abc123"]})
        _dual_write_silver_v2_resolution(
            prediction_hash="e" * 64,
            outcome="true",
            outcome_confidence=1.0,
            evidence={},
            resolution_method_id="nfl_draft_pick_sportsdataio",
            db=db,
        )
        # The query_parameters passed to execute should include prev_hash=abc123
        call_kwargs = db.execute.call_args[1]
        params = call_kwargs.get("query_parameters", [])
        prev_hash_param = next((p for p in params if p.name == "prev_hash"), None)
        assert prev_hash_param is not None
        assert prev_hash_param.value == "abc123"


class TestResolveBinaryWithDualWrite:
    """_resolve_binary_with_dual_write calls v1 then dual-writes v2."""

    def test_calls_resolve_binary(self, monkeypatch):
        monkeypatch.setenv("GCP_PROJECT_ID", "test-project")
        db = MagicMock()
        db.fetch_df.return_value = pd.DataFrame()
        db.execute.return_value = None

        with patch("src.resolve_daily.resolve_binary") as mock_rb:
            _resolve_binary_with_dual_write(
                prediction_hash="f" * 64,
                correct=True,
                outcome_source="sportsdataio",
                db=db,
            )
            mock_rb.assert_called_once()

    def test_dual_write_called_after_v1(self, monkeypatch):
        monkeypatch.setenv("GCP_PROJECT_ID", "test-project")
        db = MagicMock()
        db.fetch_df.return_value = pd.DataFrame()
        db.execute.return_value = None

        with patch("src.resolve_daily.resolve_binary"):
            with patch("src.resolve_daily._dual_write_silver_v2_resolution") as mock_dw:
                _resolve_binary_with_dual_write(
                    prediction_hash="g" * 64,
                    correct=False,
                    outcome_source="sportsdataio_scores",
                    db=db,
                )
                mock_dw.assert_called_once()
                call_kwargs = mock_dw.call_args[1]
                assert call_kwargs["outcome"] == "false"
                assert call_kwargs["resolution_method_id"] == "nfl_game_outcome_scores"


class TestVoidPredictionWithDualWrite:
    """_void_prediction_with_dual_write calls v1 then dual-writes v2 unresolvable."""

    def test_calls_void_prediction(self, monkeypatch):
        monkeypatch.setenv("GCP_PROJECT_ID", "test-project")
        db = MagicMock()
        db.fetch_df.return_value = pd.DataFrame()

        with patch("src.resolve_daily.void_prediction") as mock_vp:
            _void_prediction_with_dual_write(
                prediction_hash="h" * 64,
                reason="unparseable_draft_claim",
                db=db,
            )
            mock_vp.assert_called_once()

    def test_dual_write_outcome_is_unresolvable(self, monkeypatch):
        monkeypatch.setenv("GCP_PROJECT_ID", "test-project")
        db = MagicMock()
        db.fetch_df.return_value = pd.DataFrame()

        with patch("src.resolve_daily.void_prediction"):
            with patch("src.resolve_daily._dual_write_silver_v2_resolution") as mock_dw:
                _void_prediction_with_dual_write(
                    prediction_hash="i" * 64,
                    reason="no_player_name",
                    db=db,
                )
                mock_dw.assert_called_once()
                call_kwargs = mock_dw.call_args[1]
                assert call_kwargs["outcome"] == "unresolvable"
