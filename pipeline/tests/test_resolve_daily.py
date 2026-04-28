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
        assert "team_focus" not in result


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


# ---------------------------------------------------------------------------
# _extract_draft_claim
# ---------------------------------------------------------------------------


class TestExtractDraftClaim:
    def test_no_dot_pick_pattern(self):
        """'No. 1 overall pick' — baseline existing pattern."""
        result = _extract_draft_claim("Player will be the No. 1 overall pick in 2026")
        assert result.get("pick_number") == 1

    def test_hash_pick_pattern(self):
        """'#5 pick' — baseline existing pattern."""
        result = _extract_draft_claim("Player goes #5 pick in 2026 NFL Draft")
        assert result.get("pick_number") == 5

    def test_word_ordinal_first_overall(self):
        """'first overall' — word ordinal baseline."""
        result = _extract_draft_claim("Player will be the first overall pick in 2026")
        assert result.get("pick_number") == 1

    def test_word_ordinal_tenth_overall(self):
        """'tenth overall' — upper bound of original word ordinals."""
        result = _extract_draft_claim("Player will be the tenth overall pick in 2026")
        assert result.get("pick_number") == 10

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

    def test_draft_year_extracted(self):
        """Draft year parsed correctly alongside pick number."""
        result = _extract_draft_claim(
            "Player will be selected 16th overall in the 2026 NFL Draft"
        )
        assert result.get("draft_year") == 2026
        assert result.get("pick_number") == 16

    def test_round_number_extracted(self):
        """Round number parsed when present."""
        result = _extract_draft_claim("Player goes in Round 2 of the 2026 NFL Draft")
        assert result.get("round_number") == 2

    def test_top_n_extracted(self):
        """Top-N pattern parsed when present."""
        result = _extract_draft_claim("Player is a top-10 pick in 2026")
        assert result.get("top_n") == 10

    def test_no_pick_number_returns_empty_pick(self):
        """Claims with no pick indicator return no pick_number."""
        result = _extract_draft_claim(
            "Player will be drafted in the first round of 2026"
        )
        assert "pick_number" not in result
