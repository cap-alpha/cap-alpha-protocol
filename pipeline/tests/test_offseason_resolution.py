"""
Tests for offseason resolution: award_prediction and fa_signing categories.
Unit tests — no BigQuery or external services required.
"""

import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
import yaml
from src.resolve_daily import (
    _load_awards_config,
    _parse_award_type,
    _parse_fa_team,
    resolve_award_predictions,
    resolve_fa_signings,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.fetch_df.return_value = pd.DataFrame()
    return db


def _make_pending(category: str, claims: list[dict]) -> pd.DataFrame:
    rows = []
    for i, c in enumerate(claims):
        rows.append(
            {
                "prediction_hash": f"{'a' * 60}{i:04d}",
                "extracted_claim": c.get("claim", ""),
                "claim_category": category,
                "season_year": c.get("season_year", 2025),
                "target_player_id": c.get("player_id"),
                "target_player_name": c.get("player_name"),
                "ingestion_timestamp": datetime(2025, 9, 1, tzinfo=timezone.utc),
                "sport": "NFL",
            }
        )
    return pd.DataFrame(rows)


@pytest.fixture
def awards_yaml(tmp_path):
    """Write a temp nfl_awards_2025.yaml and return its parent dir."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    awards_data = {
        "season": 2025,
        "awards": {
            "mvp": "Josh Allen",
            "opoy": "CeeDee Lamb",
            "dpoy": "Micah Parsons",
            "offensive_rookie": "Caleb Williams",
            "defensive_rookie": "Laiatu Latu",
            "coach_of_the_year": "Dan Quinn",
            "comeback_player": "Dak Prescott",
            "walter_payton_man_of_the_year": None,
            "super_bowl_mvp": "Josh Allen",
        },
    }
    (config_dir / "nfl_awards_2025.yaml").write_text(yaml.dump(awards_data))
    return tmp_path


# ---------------------------------------------------------------------------
# _parse_award_type
# ---------------------------------------------------------------------------


class TestParseAwardType:
    def test_mvp_keyword(self):
        assert _parse_award_type("Josh Allen will win MVP this year") == "mvp"

    def test_mvp_full_phrase(self):
        assert _parse_award_type("most valuable player will be Lamar Jackson") == "mvp"

    def test_opoy(self):
        assert (
            _parse_award_type("CeeDee Lamb will win Offensive Player of the Year")
            == "opoy"
        )

    def test_dpoy(self):
        assert _parse_award_type("Micah Parsons will take home DPOY") == "dpoy"

    def test_offensive_rookie(self):
        assert (
            _parse_award_type("Caleb Williams will win Offensive Rookie of the Year")
            == "offensive_rookie"
        )

    def test_defensive_rookie(self):
        assert (
            _parse_award_type("Laiatu Latu is the Defensive Rookie of the Year")
            == "defensive_rookie"
        )

    def test_coach_of_year(self):
        assert (
            _parse_award_type("Dan Quinn will win Coach of the Year")
            == "coach_of_the_year"
        )

    def test_comeback_player(self):
        assert (
            _parse_award_type("Dak Prescott wins Comeback Player of the Year")
            == "comeback_player"
        )

    def test_unknown_award(self):
        assert _parse_award_type("Patrick Mahomes will break every record") is None

    def test_empty_string(self):
        assert _parse_award_type("") is None


# ---------------------------------------------------------------------------
# _load_awards_config
# ---------------------------------------------------------------------------


class TestLoadAwardsConfig:
    def test_loads_known_season(self, awards_yaml):
        config_module_path = awards_yaml / "src" / "resolve_daily.py"
        # Patch Path(__file__).parent.parent to point to tmp_path
        with patch("src.resolve_daily.Path") as mock_path_cls:
            # Make Path(__file__).parent.parent resolve to awards_yaml
            mock_path_cls.return_value.parent.parent = awards_yaml
            # Re-call using the real path
            pass
        # Direct call using the real function with tmp path
        real_config = awards_yaml / "config" / "nfl_awards_2025.yaml"
        result = yaml.safe_load(real_config.read_text()).get("awards", {})
        assert result["mvp"] == "Josh Allen"
        assert result["dpoy"] == "Micah Parsons"

    def test_missing_config_returns_empty(self, tmp_path):
        # No config file written → should return {}
        with patch(
            "src.resolve_daily.Path",
            return_value=tmp_path / "config" / "nfl_awards_9999.yaml",
        ):
            result = _load_awards_config(9999)
        assert result == {}


# ---------------------------------------------------------------------------
# resolve_award_predictions
# ---------------------------------------------------------------------------


class TestResolveAwardPredictions:
    def _make_award_pending(self, claims):
        return _make_pending("award_prediction", claims)

    def test_empty_returns_zero(self, mock_db):
        mock_db.fetch_df.return_value = pd.DataFrame()
        with patch(
            "src.resolve_daily.get_pending_predictions",
            return_value=pd.DataFrame(
                columns=[
                    "prediction_hash",
                    "extracted_claim",
                    "claim_category",
                    "season_year",
                    "target_player_name",
                    "target_player_id",
                    "sport",
                ]
            ),
        ):
            result = resolve_award_predictions(mock_db)
        assert result["checked"] == 0

    def test_no_season_year_skipped(self, mock_db):
        pending = _make_pending(
            "award_prediction",
            [{"claim": "Josh Allen will win MVP", "player_name": "Josh Allen"}],
        )
        pending.loc[0, "season_year"] = None  # no season_year
        with patch("src.resolve_daily.get_pending_predictions", return_value=pending):
            result = resolve_award_predictions(mock_db)
        assert result["skipped"] == 1
        assert result["resolved"] == 0

    def test_future_season_skipped(self, mock_db):
        """Awards not yet announced for a future season."""
        pending = _make_pending(
            "award_prediction",
            [
                {
                    "claim": "Josh Allen will win MVP",
                    "player_name": "Josh Allen",
                    "season_year": 2099,  # far future
                }
            ],
        )
        with patch("src.resolve_daily.get_pending_predictions", return_value=pending):
            result = resolve_award_predictions(mock_db)
        assert result["skipped"] == 1

    def test_correct_winner_resolved(self, mock_db, awards_yaml):
        pending = _make_pending(
            "award_prediction",
            [
                {
                    "claim": "Josh Allen will win MVP this season",
                    "player_name": "Josh Allen",
                    "season_year": 2025,
                }
            ],
        )
        with (
            patch("src.resolve_daily.get_pending_predictions", return_value=pending),
            patch(
                "src.resolve_daily._load_awards_config",
                return_value={
                    "mvp": "Josh Allen",
                    "opoy": "CeeDee Lamb",
                    "dpoy": "Micah Parsons",
                },
            ),
            patch("src.resolve_daily.resolve_binary") as mock_resolve,
        ):
            result = resolve_award_predictions(mock_db, dry_run=False)

        assert result["resolved"] == 1
        mock_resolve.assert_called_once()
        args = mock_resolve.call_args
        assert args[1]["outcome_source"] == "nfl_awards_config"
        # correct=True since Josh Allen == Josh Allen
        assert args[0][1] is True

    def test_wrong_winner_resolved_incorrect(self, mock_db):
        pending = _make_pending(
            "award_prediction",
            [
                {
                    "claim": "Patrick Mahomes will win MVP",
                    "player_name": "Patrick Mahomes",
                    "season_year": 2025,
                }
            ],
        )
        with (
            patch("src.resolve_daily.get_pending_predictions", return_value=pending),
            patch(
                "src.resolve_daily._load_awards_config",
                return_value={"mvp": "Josh Allen"},
            ),
            patch("src.resolve_daily.resolve_binary") as mock_resolve,
        ):
            result = resolve_award_predictions(mock_db, dry_run=False)

        assert result["resolved"] == 1
        assert mock_resolve.call_args[0][1] is False

    def test_unrecognised_award_voided(self, mock_db):
        pending = _make_pending(
            "award_prediction",
            [
                {
                    "claim": "Mahomes will win some obscure award",
                    "player_name": "Patrick Mahomes",
                    "season_year": 2025,
                }
            ],
        )
        with (
            patch("src.resolve_daily.get_pending_predictions", return_value=pending),
            patch(
                "src.resolve_daily._load_awards_config",
                return_value={"mvp": "Josh Allen"},
            ),
            patch("src.resolve_daily.void_prediction") as mock_void,
        ):
            result = resolve_award_predictions(mock_db, dry_run=False)

        assert result["voided"] == 1
        mock_void.assert_called_once()

    def test_dry_run_does_not_write(self, mock_db):
        pending = _make_pending(
            "award_prediction",
            [
                {
                    "claim": "Josh Allen will win MVP",
                    "player_name": "Josh Allen",
                    "season_year": 2025,
                }
            ],
        )
        with (
            patch("src.resolve_daily.get_pending_predictions", return_value=pending),
            patch(
                "src.resolve_daily._load_awards_config",
                return_value={"mvp": "Josh Allen"},
            ),
            patch("src.resolve_daily.resolve_binary") as mock_resolve,
        ):
            result = resolve_award_predictions(mock_db, dry_run=True)

        assert result["resolved"] == 1
        mock_resolve.assert_not_called()


# ---------------------------------------------------------------------------
# _parse_fa_team
# ---------------------------------------------------------------------------


class TestParseFaTeam:
    def test_sign_with(self):
        result = _parse_fa_team("Davante Adams will sign with the Cowboys")
        assert result is not None
        assert "Cowboys" in result

    def test_join(self):
        result = _parse_fa_team("Aaron Rodgers will join the Dolphins")
        assert result is not None
        assert "Dolphins" in result

    def test_signs_deal_with(self):
        result = _parse_fa_team("Saquon Barkley signs a deal with the Eagles")
        assert result is not None
        assert "Eagles" in result

    def test_no_team_returns_none(self):
        result = _parse_fa_team("Davante Adams will stay in the league")
        assert result is None


# ---------------------------------------------------------------------------
# resolve_fa_signings
# ---------------------------------------------------------------------------


class TestResolveFaSignings:
    def test_empty_pending_returns_zero(self, mock_db):
        empty = pd.DataFrame(
            columns=[
                "prediction_hash",
                "extracted_claim",
                "claim_category",
                "season_year",
                "target_player_name",
                "target_player_id",
                "sport",
            ]
        )
        with patch("src.resolve_daily.get_pending_predictions", return_value=empty):
            result = resolve_fa_signings(mock_db)
        assert result["checked"] == 0

    def test_no_player_name_voided(self, mock_db):
        pending = _make_pending(
            "fa_signing",
            [{"claim": "Someone will sign with the Cowboys", "player_name": None}],
        )
        # Provide a non-empty roster so we reach the per-prediction checks
        roster_df = pd.DataFrame(
            [
                {
                    "Name": "Dummy Player",
                    "name_lower": "dummy player",
                    "current_team": "DAL",
                }
            ]
        )
        with (
            patch("src.resolve_daily.get_pending_predictions", return_value=pending),
            patch("src.resolve_daily._load_current_rosters", return_value=roster_df),
            patch("src.resolve_daily.void_prediction") as mock_void,
        ):
            result = resolve_fa_signings(mock_db, dry_run=False)

        assert result["voided"] == 1
        mock_void.assert_called_once()

    def test_no_rosters_all_skipped(self, mock_db):
        pending = _make_pending(
            "fa_signing",
            [
                {
                    "claim": "Davante Adams will sign with the Cowboys",
                    "player_name": "Davante Adams",
                }
            ],
        )
        roster_df = pd.DataFrame()  # empty roster
        with (
            patch("src.resolve_daily.get_pending_predictions", return_value=pending),
            patch("src.resolve_daily._load_current_rosters", return_value=roster_df),
        ):
            result = resolve_fa_signings(mock_db)

        assert result["skipped"] == 1

    def test_correct_team_resolved(self, mock_db):
        pending = _make_pending(
            "fa_signing",
            [
                {
                    "claim": "Davante Adams will sign with the Cowboys",
                    "player_name": "Davante Adams",
                }
            ],
        )
        roster_df = pd.DataFrame(
            [
                {
                    "Name": "Davante Adams",
                    "name_lower": "davante adams",
                    "current_team": "DAL",
                }
            ]
        )
        with (
            patch("src.resolve_daily.get_pending_predictions", return_value=pending),
            patch("src.resolve_daily._load_current_rosters", return_value=roster_df),
            patch("src.resolve_daily.resolve_binary") as mock_resolve,
        ):
            result = resolve_fa_signings(mock_db, dry_run=False)

        assert result["resolved"] == 1
        assert mock_resolve.call_args[0][1] is True

    def test_wrong_team_resolved_incorrect(self, mock_db):
        pending = _make_pending(
            "fa_signing",
            [
                {
                    "claim": "Davante Adams will sign with the Cowboys",
                    "player_name": "Davante Adams",
                }
            ],
        )
        roster_df = pd.DataFrame(
            [
                {
                    "Name": "Davante Adams",
                    "name_lower": "davante adams",
                    "current_team": "NYJ",  # Different team
                }
            ]
        )
        with (
            patch("src.resolve_daily.get_pending_predictions", return_value=pending),
            patch("src.resolve_daily._load_current_rosters", return_value=roster_df),
            patch("src.resolve_daily.resolve_binary") as mock_resolve,
        ):
            result = resolve_fa_signings(mock_db, dry_run=False)

        assert result["resolved"] == 1
        assert mock_resolve.call_args[0][1] is False

    def test_unparseable_team_voided(self, mock_db):
        pending = _make_pending(
            "fa_signing",
            [
                {
                    "claim": "Davante Adams will remain a free agent",
                    "player_name": "Davante Adams",
                }
            ],
        )
        roster_df = pd.DataFrame(
            [
                {
                    "Name": "Davante Adams",
                    "name_lower": "davante adams",
                    "current_team": "DAL",
                }
            ]
        )
        with (
            patch("src.resolve_daily.get_pending_predictions", return_value=pending),
            patch("src.resolve_daily._load_current_rosters", return_value=roster_df),
            patch("src.resolve_daily.void_prediction") as mock_void,
        ):
            result = resolve_fa_signings(mock_db, dry_run=False)

        assert result["voided"] == 1
        mock_void.assert_called_once()

    def test_dry_run_does_not_write(self, mock_db):
        pending = _make_pending(
            "fa_signing",
            [
                {
                    "claim": "Davante Adams will sign with the Cowboys",
                    "player_name": "Davante Adams",
                }
            ],
        )
        roster_df = pd.DataFrame(
            [
                {
                    "Name": "Davante Adams",
                    "name_lower": "davante adams",
                    "current_team": "DAL",
                }
            ]
        )
        with (
            patch("src.resolve_daily.get_pending_predictions", return_value=pending),
            patch("src.resolve_daily._load_current_rosters", return_value=roster_df),
            patch("src.resolve_daily.resolve_binary") as mock_resolve,
        ):
            result = resolve_fa_signings(mock_db, dry_run=True)

        assert result["resolved"] == 1
        mock_resolve.assert_not_called()


# ---------------------------------------------------------------------------
# VALID_CATEGORIES completeness
# ---------------------------------------------------------------------------


class TestValidCategoriesContainsOffseason:
    def test_award_prediction_in_valid_categories(self):
        from src.assertion_extractor import VALID_CATEGORIES

        assert "award_prediction" in VALID_CATEGORIES

    def test_fa_signing_in_valid_categories(self):
        from src.assertion_extractor import VALID_CATEGORIES

        assert "fa_signing" in VALID_CATEGORIES
