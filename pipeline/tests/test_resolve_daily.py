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
    _infer_season_year_from_ingestion,
    _load_draft_data,
    _normalize_name,
    _normalize_team,
    _resolve_binary_with_dual_write,
    _resolve_team_claim,
    _silver_v2_resolution_method_id,
    _void_prediction_with_dual_write,
    expire_stale_predictions,
    resolve_all,
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
                "ingestion_timestamp": c.get(
                    "ingestion_timestamp", datetime(2024, 9, 1, tzinfo=timezone.utc)
                ),
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
# _infer_season_year_from_ingestion (Issue #1167)
# ---------------------------------------------------------------------------


class TestInferSeasonYearFromIngestion:
    def test_none_returns_none(self):
        assert _infer_season_year_from_ingestion(None) is None

    def test_nat_returns_none(self):
        assert _infer_season_year_from_ingestion(pd.NaT) is None

    def test_march_through_december_maps_to_same_year(self):
        """Ingested outside Jan/Feb -> discussing the season starting that year."""
        assert (
            _infer_season_year_from_ingestion(
                datetime(2026, 4, 24, tzinfo=timezone.utc)
            )
            == 2026
        )
        assert (
            _infer_season_year_from_ingestion(
                datetime(2026, 12, 31, tzinfo=timezone.utc)
            )
            == 2026
        )

    def test_january_february_is_ambiguous_returns_none(self):
        """
        Issue #1167 MEDIUM-6 (adversarial review): Jan/Feb could mean "still
        wrapping up last season" or "an early look at next season" — that's
        a real coin flip, not a safe inference. Previously this guessed
        year-1 unconditionally; it must now return None (skip) instead.
        """
        assert (
            _infer_season_year_from_ingestion(
                datetime(2026, 1, 15, tzinfo=timezone.utc)
            )
            is None
        )
        assert (
            _infer_season_year_from_ingestion(
                datetime(2026, 2, 28, tzinfo=timezone.utc)
            )
            is None
        )

    def test_prefers_content_published_at_over_ingestion_timestamp(self):
        """
        MEDIUM-6: when a content/article publish date is available it wins
        over ingestion_timestamp — ingestion only tells us when our pipeline
        scraped the claim, which can lag the pundit's actual statement.
        """
        # Ingested in September (would infer 2026) but actually published in
        # December of the prior year (should infer 2025).
        assert (
            _infer_season_year_from_ingestion(
                datetime(2026, 9, 1, tzinfo=timezone.utc),
                content_published_at=datetime(2025, 12, 1, tzinfo=timezone.utc),
            )
            == 2025
        )

    def test_falls_back_to_ingestion_when_no_content_date(self):
        """content_published_at=None falls back to ingestion_timestamp unchanged."""
        assert (
            _infer_season_year_from_ingestion(
                datetime(2026, 9, 1, tzinfo=timezone.utc),
                content_published_at=None,
            )
            == 2026
        )

    def test_ambiguous_content_date_ignores_unambiguous_ingestion(self):
        """
        A Jan/Feb content publish date is ambiguous even when
        ingestion_timestamp (which is not preferred once a content date
        exists) would have given an unambiguous month.
        """
        assert (
            _infer_season_year_from_ingestion(
                datetime(2026, 9, 1, tzinfo=timezone.utc),
                content_published_at=datetime(2026, 1, 20, tzinfo=timezone.utc),
            )
            is None
        )


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

    @patch("src.resolve_daily._load_game_scores")
    @patch("src.resolve_daily.get_pending_predictions")
    @patch("src.resolve_daily._resolve_binary_with_dual_write")
    def test_infers_season_year_from_ingestion_when_null(
        self, mock_resolve, mock_pending, mock_load, mock_db
    ):
        """
        Issue #1167: NULL season_year no longer hard-skips forever — infer it
        from ingestion_timestamp (read-time fallback) so a completed season
        can still enter the normal resolution gate.
        """
        preds = _make_pending_df(
            "game_outcome",
            [
                {
                    "claim": "Chiefs beat Eagles",
                    "season_year": None,
                    "ingestion_timestamp": datetime(2024, 9, 1, tzinfo=timezone.utc),
                }
            ],
        )
        mock_pending.return_value = preds
        mock_load.return_value = _SCORES_2024

        summary = resolve_game_outcomes(mock_db, dry_run=False)

        assert summary["resolved"] == 1
        assert summary["skipped"] == 0
        mock_load.assert_called_once_with(mock_db, 2024)

    @patch("src.resolve_daily.get_pending_predictions")
    def test_null_season_year_inferred_as_current_season_still_skips(
        self, mock_pending, mock_db
    ):
        """
        Issue #1167: the inference must not force-resolve predictions whose
        season hasn't completed. A NULL season_year ingested this spring
        infers to the current (still in-progress) season and must keep
        waiting, same as an explicit season_year=<current year> would.
        """
        current_year = pd.Timestamp.now().year
        preds = _make_pending_df(
            "game_outcome",
            [
                {
                    "claim": "Chiefs beat Eagles",
                    "season_year": None,
                    "ingestion_timestamp": datetime(
                        current_year, 4, 24, tzinfo=timezone.utc
                    ),
                }
            ],
        )
        mock_pending.return_value = preds

        summary = resolve_game_outcomes(mock_db, dry_run=False)

        assert summary["skipped"] == 1
        assert summary["resolved"] == 0

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

    @patch("src.resolve_daily._load_player_season_stats")
    @patch("src.resolve_daily.get_pending_predictions")
    @patch("src.resolve_daily._resolve_binary_with_dual_write")
    def test_infers_season_year_from_ingestion_when_null(
        self, mock_resolve, mock_pending, mock_load, mock_db
    ):
        """
        Issue #1167: NULL season_year no longer hard-skips forever — infer it
        from ingestion_timestamp (read-time fallback) so a completed season
        can still enter the normal resolution gate.
        """
        preds = _make_pending_df(
            "player_performance",
            [
                {
                    "claim": "Patrick Mahomes throws 5000+ passing yards",
                    "season_year": None,
                    "player_name": "Patrick Mahomes",
                    "ingestion_timestamp": datetime(2024, 9, 1, tzinfo=timezone.utc),
                }
            ],
        )
        mock_pending.return_value = preds
        mock_load.return_value = _MAHOMES_STATS_2024

        summary = resolve_player_performance(mock_db, dry_run=False)

        assert summary["resolved"] == 1
        assert summary["skipped"] == 0
        mock_load.assert_called_once_with(mock_db, 2024)

    @patch("src.resolve_daily.get_pending_predictions")
    def test_null_season_year_inferred_as_current_season_still_skips(
        self, mock_pending, mock_db
    ):
        """
        Issue #1167: the inference must not force-resolve predictions whose
        season hasn't completed. A NULL season_year ingested this spring
        infers to the current (still in-progress) season and must keep
        waiting, same as an explicit season_year=<current year> would.
        """
        current_year = pd.Timestamp.now().year
        preds = _make_pending_df(
            "player_performance",
            [
                {
                    "claim": "Patrick Mahomes throws 5000+ passing yards",
                    "season_year": None,
                    "player_name": "Patrick Mahomes",
                    "ingestion_timestamp": datetime(
                        current_year, 4, 24, tzinfo=timezone.utc
                    ),
                }
            ],
        )
        mock_pending.return_value = preds

        summary = resolve_player_performance(mock_db, dry_run=False)

        assert summary["skipped"] == 1
        assert summary["resolved"] == 0

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

    # -----------------------------------------------------------------------
    # Cardinal number words (Issue #1167) — previously only ordinals
    # ("fifth", "seventh") were understood; cardinal phrasing like "five
    # overall" or "pick number seven" fell through to unparseable.
    # -----------------------------------------------------------------------

    def test_cardinal_word_five_overall(self):
        result = _extract_draft_claim(
            "Prospect will go five overall in the 2026 NFL Draft"
        )
        assert result["pick_number"] == 5

    def test_cardinal_pick_number_seven_word(self):
        result = _extract_draft_claim("Player will be pick number seven in 2026")
        assert result["pick_number"] == 7

    def test_cardinal_pick_number_seven_digit(self):
        result = _extract_draft_claim("Player will be pick number 7 in 2026")
        assert result["pick_number"] == 7

    def test_cardinal_word_three_pick(self):
        result = _extract_draft_claim("Drake Maye is the three pick in 2024")
        assert result["pick_number"] == 3

    # -----------------------------------------------------------------------
    # HIGH-4 (Issue #1167 adversarial review) — cardinal misfire GUARD tests.
    # The previous substring-based cardinal matching produced wrong pick
    # numbers (not just missed matches); these lock in the fixed behavior.
    # -----------------------------------------------------------------------

    def test_cardinal_no_word_boundary_seventeen_not_misread_as_seven(self):
        """
        "pick number seventeen" must resolve to 17 (a real supported
        cardinal), not 7 — the old substring check matched "seven" as a
        prefix of "seventeen" and returned the wrong pick number entirely.
        """
        result = _extract_draft_claim("Player will be pick number seventeen in 2026")
        assert result["pick_number"] == 17

    def test_cardinal_plural_picks_does_not_set_pick_number(self):
        """
        "four picks in the top 100" describes a team's pick *count*, not a
        single pick-number claim — the plural "picks" must not satisfy the
        singular pick-number pattern the way "four pick" (substring of
        "four picks") previously did.
        """
        result = _extract_draft_claim(
            "The Broncos will have four picks in the top 100 in 2026"
        )
        assert "pick_number" not in result

    def test_cardinal_hyphen_compound_not_misread(self):
        """
        "twenty-five overall" must not be misread as pick_number=5 — "five"
        is a hyphen-compound suffix of the unsupported number 25, not a
        standalone cardinal, and must be rejected rather than guessed.
        """
        result = _extract_draft_claim(
            "Prospect will go twenty-five overall in the 2026 NFL Draft"
        )
        assert "pick_number" not in result

    # -----------------------------------------------------------------------
    # MEDIUM-8 (Issue #1167 adversarial review) — draft_year should prefer a
    # year mentioned next to "draft", not just the first 4-digit year found.
    # -----------------------------------------------------------------------

    def test_draft_year_prefers_year_near_draft_keyword(self):
        """
        A claim mentioning an unrelated year (e.g. a recruiting class) ahead
        of the real draft year must extract the draft-adjacent year, not the
        first 20xx substring encountered.
        """
        result = _extract_draft_claim(
            "The 2021 recruiting class standout is the No. 3 pick in the 2024 NFL Draft"
        )
        assert result["draft_year"] == 2024


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


def _make_full_immutable_board(
    year: int, n: int = 205, extra_rows: "list[dict] | None" = None
) -> pd.DataFrame:
    """
    Build a synthetic bronze_nflverse_draft_picks-shaped board for `year`
    with `n` distinct synthetic picks (large enough to pass the
    _MIN_DRAFT_BOARD_SIZE guard) plus any `extra_rows` (e.g. a specific
    named player under test). Mirrors the columns _load_immutable_draft_board
    returns: draft_year, draft_round, draft_pick, draft_team, player_name,
    name_lower.
    """
    rows = [
        {
            "draft_year": year,
            "draft_round": (i // 32) + 1,
            "draft_pick": i + 1,
            "draft_team": "GB",
            "player_name": f"Depth Player {i}",
            "name_lower": f"depth player {i}",
        }
        for i in range(n)
    ]
    for extra in extra_rows or []:
        row = {"draft_year": year, **extra}
        row.setdefault("name_lower", row["player_name"].lower())
        rows.append(row)
    return pd.DataFrame(rows)


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

    @patch("src.resolve_daily._load_immutable_draft_board")
    @patch("src.resolve_daily._load_draft_data")
    @patch("src.resolve_daily.get_pending_predictions")
    @patch("src.resolve_daily._resolve_binary_with_dual_write")
    def test_terminal_incorrect_when_player_not_found_after_draft_concluded(
        self, mock_resolve, mock_pending, mock_load, mock_immutable, mock_db
    ):
        """
        Issue #1167 (reworked per adversarial review): once the draft year is
        in the past, a predicted-drafted player absent from BOTH the
        active-roster board AND the complete immutable nflverse draft-results
        record (which is large enough to trust — guards CRITICAL-1) is a
        terminal INCORRECT ("predicted drafted but wasn't"), not an infinite
        skip.
        """
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
        mock_immutable.return_value = _make_full_immutable_board(2024)

        summary = resolve_draft_picks(mock_db, dry_run=False)

        assert summary["resolved"] == 1
        assert summary["skipped"] == 0
        call_kwargs = mock_resolve.call_args[1]
        assert call_kwargs["correct"] is False

    @patch("src.resolve_daily._load_draft_data")
    @patch("src.resolve_daily.get_pending_predictions")
    def test_skip_player_not_found_when_draft_year_still_current(
        self, mock_pending, mock_load, mock_db
    ):
        """
        A not-found player is still a plain SKIP (not terminal) when the
        draft year is the current year — the draft hasn't necessarily
        "concluded" from the resolver's point of view yet, even though some
        results already exist for it.
        """
        current_year = pd.Timestamp.now().year
        current_year_draft_data = _DRAFT_DATA_2024.copy()
        current_year_draft_data["draft_year"] = current_year
        preds = _make_pending_df(
            "draft_pick",
            [
                {
                    "claim": f"John Nobody is the #5 pick in {current_year}",
                    "season_year": current_year,
                    "target_player_id": "John Nobody",
                }
            ],
        )
        mock_pending.return_value = preds
        mock_load.return_value = current_year_draft_data

        summary = resolve_draft_picks(mock_db, dry_run=False)

        assert summary["skipped"] == 1
        assert summary["resolved"] == 0

    @patch("src.resolve_daily._load_draft_data")
    @patch("src.resolve_daily.get_pending_predictions")
    @patch("src.resolve_daily._resolve_binary_with_dual_write")
    def test_terminal_incorrect_when_pick_is_null_after_draft_concluded(
        self, mock_resolve, mock_pending, mock_load, mock_db
    ):
        """
        Issue #1167: the player IS on the draft board for the (past) draft
        year but CollegeDraftPick is NULL (e.g. went undrafted) — terminal
        INCORRECT, not an infinite skip.
        """
        undrafted_row = pd.DataFrame(
            [
                {
                    "Name": "Undrafted Player",
                    "name_lower": "undrafted player",
                    "draft_year": 2024,
                    "draft_round": None,
                    "draft_pick": None,
                    "draft_team": None,
                    "current_team": "FA",
                    "undrafted": True,
                }
            ]
        )
        draft_data_with_undrafted = pd.concat(
            [undrafted_row, _DRAFT_DATA_2024], ignore_index=True
        )
        preds = _make_pending_df(
            "draft_pick",
            [
                {
                    "claim": "Undrafted Player is the #5 pick in 2024",
                    "season_year": 2024,
                    "target_player_id": "Undrafted Player",
                }
            ],
        )
        mock_pending.return_value = preds
        mock_load.return_value = draft_data_with_undrafted

        summary = resolve_draft_picks(mock_db, dry_run=False)

        assert summary["resolved"] == 1
        assert summary["skipped"] == 0
        call_kwargs = mock_resolve.call_args[1]
        assert call_kwargs["correct"] is False

    # -----------------------------------------------------------------------
    # Issue #1167 adversarial-review REWORK — false-INCORRECT GUARD tests.
    # -----------------------------------------------------------------------

    @patch("src.resolve_daily._load_draft_data")
    @patch("src.resolve_daily.get_pending_predictions")
    @patch("src.resolve_daily._resolve_binary_with_dual_write")
    def test_null_pick_without_undrafted_flag_stays_pending(
        self, mock_resolve, mock_pending, mock_load, mock_db
    ):
        """
        MEDIUM-7: a NULL CollegeDraftPick alone is not proof of "undrafted"
        — it could just be missing/delayed data. Only the explicit
        IsUndraftedFreeAgent=True flag is trusted as positive evidence; a
        NULL pick with the flag False/missing must stay pending, not
        terminal-resolve.
        """
        data_gap_row = pd.DataFrame(
            [
                {
                    "Name": "Data Gap Player",
                    "name_lower": "data gap player",
                    "draft_year": 2024,
                    "draft_round": None,
                    "draft_pick": None,
                    "draft_team": None,
                    "current_team": "FA",
                    "undrafted": False,
                }
            ]
        )
        draft_data = pd.concat([data_gap_row, _DRAFT_DATA_2024], ignore_index=True)
        preds = _make_pending_df(
            "draft_pick",
            [
                {
                    "claim": "Data Gap Player is the #5 pick in 2024",
                    "season_year": 2024,
                    "target_player_id": "Data Gap Player",
                }
            ],
        )
        mock_pending.return_value = preds
        mock_load.return_value = draft_data

        summary = resolve_draft_picks(mock_db, dry_run=False)

        assert summary["skipped"] == 1
        assert summary["resolved"] == 0
        mock_resolve.assert_not_called()

    @patch("src.resolve_daily._load_draft_data")
    @patch("src.resolve_daily.get_pending_predictions")
    @patch("src.resolve_daily._resolve_binary_with_dual_write")
    def test_cross_year_leak_does_not_override_same_year_match(
        self, mock_resolve, mock_pending, mock_load, mock_db
    ):
        """
        MEDIUM-7: a stale same-named row from an unrelated draft_year (a
        2019 record with no pick data and undrafted=True) must never be
        used to resolve a 2024 claim. Matching is now scoped to the claim's
        own draft_year, so the player's REAL 2024 pick is used instead of a
        leftover cross-year NULL-pick record that would otherwise fire a
        false terminal INCORRECT.
        """
        cross_year_leak = pd.DataFrame(
            [
                {
                    "Name": "Cross Year Player",
                    "name_lower": "cross year player",
                    "draft_year": 2019,
                    "draft_round": None,
                    "draft_pick": None,
                    "draft_team": None,
                    "current_team": None,
                    "undrafted": True,
                },
                {
                    "Name": "Cross Year Player",
                    "name_lower": "cross year player",
                    "draft_year": 2024,
                    "draft_round": 1,
                    "draft_pick": 10,
                    "draft_team": "SEA",
                    "current_team": "SEA",
                    "undrafted": False,
                },
            ]
        )
        preds = _make_pending_df(
            "draft_pick",
            [
                {
                    "claim": "Cross Year Player is the No. 10 overall pick in 2024",
                    "season_year": 2024,
                    "target_player_id": "Cross Year Player",
                }
            ],
        )
        mock_pending.return_value = preds
        mock_load.return_value = cross_year_leak

        summary = resolve_draft_picks(mock_db, dry_run=False)

        assert summary["resolved"] == 1
        call_kwargs = mock_resolve.call_args[1]
        assert call_kwargs["correct"] is True, (
            "must match the real 2024 pick #10 record, not the stale 2019 "
            "NULL-pick/undrafted=True row"
        )

    @patch("src.resolve_daily._load_immutable_draft_board")
    @patch("src.resolve_daily._load_draft_data")
    @patch("src.resolve_daily.get_pending_predictions")
    @patch("src.resolve_daily._resolve_binary_with_dual_write")
    def test_stale_immutable_board_size_guard_skips_instead_of_incorrect(
        self, mock_resolve, mock_pending, mock_load, mock_immutable, mock_db
    ):
        """
        CRITICAL-1: if the immutable nflverse draft-results board for a
        concluded year is too small (e.g. a failed/partial ingest), the
        resolver must SKIP rather than trust its absence signal — a
        dropped ingest must never mass-resolve a whole draft class
        INCORRECT in one pass.
        """
        preds = _make_pending_df(
            "draft_pick",
            [
                {
                    "claim": "Ghost Player is the #5 pick in 2024",
                    "season_year": 2024,
                    "target_player_id": "Ghost Player",
                }
            ],
        )
        mock_pending.return_value = preds
        mock_load.return_value = _DRAFT_DATA_2024
        mock_immutable.return_value = _make_full_immutable_board(2024, n=5)

        summary = resolve_draft_picks(mock_db, dry_run=False)

        assert summary["skipped"] == 1
        assert summary["resolved"] == 0
        mock_resolve.assert_not_called()

    @patch("src.resolve_daily._load_immutable_draft_board")
    @patch("src.resolve_daily._load_draft_data")
    @patch("src.resolve_daily.get_pending_predictions")
    @patch("src.resolve_daily._resolve_binary_with_dual_write")
    def test_departed_draftee_resolved_via_immutable_board_not_falsely_incorrect(
        self, mock_resolve, mock_pending, mock_load, mock_immutable, mock_db
    ):
        """
        CRITICAL-1 core regression: bronze_sportsdataio_players is an
        ACTIVE-roster snapshot — a real draftee who has since retired/been
        cut vanishes from it (e.g. the 2015 class has shrunk to ~135 of the
        original ~256 rows). A tiny/attrited active board for an old draft
        class must NOT produce a false terminal INCORRECT when the player
        is still on record in the immutable nflverse draft-results history
        — it must resolve CORRECT/INCORRECT from that record instead.
        """
        tiny_active_board = pd.DataFrame(
            [
                {
                    "Name": "Someone Else",
                    "name_lower": "someone else",
                    "draft_year": 2015,
                    "draft_round": 1,
                    "draft_pick": 1,
                    "draft_team": "TB",
                    "current_team": "TB",
                    "undrafted": False,
                }
            ]
        )
        full_immutable = _make_full_immutable_board(
            2015,
            extra_rows=[
                {
                    "draft_round": 1,
                    "draft_pick": 5,
                    "draft_team": "SEA",
                    "player_name": "Old Player",
                }
            ],
        )
        preds = _make_pending_df(
            "draft_pick",
            [
                {
                    "claim": "Old Player is the No. 5 overall pick in 2015",
                    "season_year": 2015,
                    "target_player_id": "Old Player",
                }
            ],
        )
        mock_pending.return_value = preds
        mock_load.return_value = tiny_active_board
        mock_immutable.return_value = full_immutable

        summary = resolve_draft_picks(mock_db, dry_run=False)

        assert summary["resolved"] == 1
        call_kwargs = mock_resolve.call_args[1]
        assert call_kwargs["correct"] is True
        assert call_kwargs["outcome_source"] == "nflverse_draft_picks"

    @patch("src.resolve_daily._load_draft_data")
    @patch("src.resolve_daily.get_pending_predictions")
    @patch("src.resolve_daily._resolve_binary_with_dual_write")
    def test_initials_name_matches_via_normalized_board(
        self, mock_resolve, mock_pending, mock_load, mock_db, monkeypatch
    ):
        """
        HIGH-3: "J.J. McCarthy" (claim, normalized to "jj mccarthy" by
        stripping periods) must match a board row whose raw Name also
        contains periods ("J.J. McCarthy") once the board side is
        normalized the same way at load time. Exercises the real
        `_load_draft_data` normalization path (not a hand-built fixture with
        a pre-normalized name_lower), since that's exactly where the
        asymmetry bug lived.
        """
        monkeypatch.setenv("GCP_PROJECT_ID", "test-project")

        class _FakeDB:
            def fetch_df(self, *_args, **_kwargs):
                return pd.DataFrame(
                    [
                        {
                            "Name": "J.J. McCarthy",
                            "draft_year": 2024,
                            "draft_round": 1,
                            "draft_pick": 10,
                            "draft_team": "MIN",
                            "current_team": "MIN",
                            "undrafted": False,
                        }
                    ]
                )

        real_draft_data = _load_draft_data(_FakeDB())
        preds = _make_pending_df(
            "draft_pick",
            [
                {
                    "claim": "J.J. McCarthy is the No. 10 overall pick in 2024",
                    "season_year": 2024,
                    "target_player_id": "J.J. McCarthy",
                }
            ],
        )
        mock_pending.return_value = preds
        mock_load.return_value = real_draft_data

        summary = resolve_draft_picks(mock_db, dry_run=False)

        assert summary["resolved"] == 1
        call_kwargs = mock_resolve.call_args[1]
        assert call_kwargs["correct"] is True

    @patch("src.resolve_daily._load_draft_data")
    @patch("src.resolve_daily.get_pending_predictions")
    @patch("src.resolve_daily._resolve_binary_with_dual_write")
    @patch("src.resolve_daily._void_prediction_with_dual_write")
    def test_misclassified_recruiting_recap_does_not_resolve(
        self, mock_void, mock_resolve, mock_pending, mock_load, mock_db
    ):
        """
        CRITICAL-2 (adversarial review, verified against prod BQ — this is
        THE false-INCORRECT that fired in the pre-rework code, 1 of 266
        pending draft_pick rows): a misclassified recruiting recap with no
        parseable pick/round/top-N structure must never reach the
        terminal-INCORRECT branch just because it names a player and
        mentions a year.
        """
        preds = _make_pending_df(
            "draft_pick",
            [
                {
                    "claim": (
                        "Harrison Wallace III was a three-star recruit and "
                        "71st-ranked receiver in the 2021 recruiting class, "
                        "according to composite rankings."
                    ),
                    "season_year": 2021,
                    "target_player_id": "Harrison Wallace III",
                }
            ],
        )
        mock_pending.return_value = preds
        mock_load.return_value = (
            _DRAFT_DATA_2024  # player absent from this board entirely
        )

        summary = resolve_draft_picks(mock_db, dry_run=False)

        assert summary["resolved"] == 0
        assert summary["skipped"] == 1
        mock_resolve.assert_not_called()
        mock_void.assert_not_called()

    @patch("src.resolve_daily._load_draft_data")
    @patch("src.resolve_daily._resolve_binary_with_dual_write")
    def test_re_resolve_voids_does_not_convert_unparseable_to_incorrect(
        self, mock_resolve, mock_load, mock_db
    ):
        """
        MEDIUM-9: the re-resolve-voids pass retries predictions previously
        VOID'd as UNPARSEABLE_CLAIM via `pending_override`. Those claims by
        definition have no pick/round/top-N structure — replaying them
        (e.g. against a board snapshot where the player no longer matches)
        must still SKIP rather than newly qualify for the terminal-
        INCORRECT branch just because the player is now absent from the
        board.
        """
        previously_voided = _make_pending_df(
            "draft_pick",
            [
                {
                    "claim": "Some Player will have an impact in 2024",
                    "season_year": 2024,
                    "target_player_id": "Some Player",
                }
            ],
        )
        mock_load.return_value = _DRAFT_DATA_2024  # "Some Player" not on this board

        summary = resolve_draft_picks(
            mock_db, dry_run=False, pending_override=previously_voided
        )

        assert summary["resolved"] == 0
        assert summary["skipped"] == 1
        mock_resolve.assert_not_called()

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


# ---------------------------------------------------------------------------
# resolve_all — combined-summary aggregation robustness (regression)
#
# resolve_all() sums checked/resolved/voided/skipped across a set of
# heterogeneous per-resolver summaries. run_llm_judge_pass() reports
# checked/resolved/skipped/errors but never "voided" (it resolves or skips,
# it never voids), and its exception fallback omits "voided" too. A bare
# s["voided"] therefore raised KeyError on every full pass, crashing the whole
# "Resolve predictions" pipeline step (observed red in pundit_pipeline.yml,
# 2026-07-21). These tests pin the .get(k, 0) fix.
# ---------------------------------------------------------------------------


class TestResolveAllSummaryAggregation:
    _PATCH_TARGETS = {
        "resolve_draft_picks": {"checked": 2, "resolved": 1, "voided": 1, "skipped": 0},
        "resolve_game_outcomes": {
            "checked": 3,
            "resolved": 2,
            "voided": 0,
            "skipped": 1,
        },
        "resolve_player_performance": {
            "checked": 1,
            "resolved": 0,
            "voided": 0,
            "skipped": 1,
        },
        "resolve_award_predictions": {
            "checked": 0,
            "resolved": 0,
            "voided": 0,
            "skipped": 0,
        },
        "resolve_fa_signings": {"checked": 1, "resolved": 1, "voided": 0, "skipped": 0},
    }

    def _run(self, judge_summary):
        db = MagicMock()
        db.fetch_df.return_value = pd.DataFrame()
        stack = []
        try:
            for name, summary in self._PATCH_TARGETS.items():
                p = patch(f"src.resolve_daily.{name}", return_value=summary)
                p.start()
                stack.append(p)
            # llm_judge is imported lazily inside resolve_all
            pj = patch(
                "src.resolvers.llm_judge.run_llm_judge_pass",
                return_value=judge_summary,
            )
            pj.start()
            stack.append(pj)
            pe = patch("src.resolve_daily.expire_stale_predictions", return_value=0)
            pe.start()
            stack.append(pe)
            return resolve_all(dry_run=True, db=db)
        finally:
            for p in reversed(stack):
                p.stop()

    def test_full_pass_does_not_crash_when_judge_summary_omits_voided(self):
        # run_llm_judge_pass success shape: no "voided" key.
        judge = {"checked": 5, "resolved": 2, "skipped": 3, "errors": 0}
        total = self._run(judge)
        # rule resolvers void exactly 1 (draft); judge contributes 0.
        assert total["voided"] == 1
        # checked/resolved/skipped sum across all summaries incl. judge.
        assert total["checked"] == 2 + 3 + 1 + 0 + 1 + 5
        assert total["resolved"] == 1 + 2 + 0 + 0 + 1 + 2
        assert total["skipped"] == 0 + 1 + 1 + 0 + 0 + 3

    def test_full_pass_does_not_crash_when_judge_summary_is_error_fallback(self):
        # Exception-fallback shape built in resolve_all: also omits "voided".
        judge = {"checked": 0, "resolved": 0, "skipped": 0, "errors": 1}
        total = self._run(judge)
        assert total["voided"] == 1
        assert total["checked"] == 2 + 3 + 1 + 0 + 1
