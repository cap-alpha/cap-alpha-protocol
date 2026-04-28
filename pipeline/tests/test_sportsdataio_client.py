"""
Unit tests for sportsdataio_client.py — scores and player_season_stats ingestion.

These tests use mocks so they run without a live SportsData.io API key or BigQuery
connection.  Integration tests that hit the real API or BQ are gated on env vars.
"""

import os
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Helpers / sample fixtures
# ---------------------------------------------------------------------------

SAMPLE_SCORES = [
    {
        "GameKey": "202510100",
        "Season": 2025,
        "Week": 1,
        "HomeTeam": "KC",
        "AwayTeam": "BAL",
        "HomeScore": 27,
        "AwayScore": 20,
        "IsPlayoffGame": False,
        "Stadium": "Arrowhead Stadium",
    },
    {
        "GameKey": "202510200",
        "Season": 2025,
        "Week": 2,
        "HomeTeam": "SF",
        "AwayTeam": "DAL",
        "HomeScore": 31,
        "AwayScore": 14,
        "IsPlayoffGame": False,
        "Stadium": "Levi's Stadium",
    },
]

SAMPLE_PLAYER_STATS = [
    {
        "PlayerID": 17959,
        "Season": 2025,
        "Name": "Patrick Mahomes",
        "Team": "KC",
        "PassingYards": 4800,
        "PassingTouchdowns": 37,
        "Interceptions": 11,
        "RushingYards": 358,
        "RushingTouchdowns": 4,
        "ReceivingYards": 0,
        "ReceivingTouchdowns": 0,
        "Receptions": 0,
        "Sacks": 0.0,
        "Tackles": 0.0,
    },
    {
        "PlayerID": 22563,
        "Season": 2025,
        "Name": "Lamar Jackson",
        "Team": "BAL",
        "PassingYards": 4200,
        "PassingTouchdowns": 41,
        "Interceptions": 4,
        "RushingYards": 1012,
        "RushingTouchdowns": 7,
        "ReceivingYards": 0,
        "ReceivingTouchdowns": 0,
        "Receptions": 0,
        "Sacks": 0.0,
        "Tackles": 0.0,
    },
]


# ---------------------------------------------------------------------------
# SportsDataIOCoreClient tests
# ---------------------------------------------------------------------------


class TestSportsDataIOCoreClient:
    def test_init_raises_without_api_key(self, monkeypatch):
        monkeypatch.delenv("SPORTS_DATA_IO_API_KEY", raising=False)
        from src.sportsdataio_client import SportsDataIOCoreClient

        with pytest.raises(EnvironmentError, match="SPORTS_DATA_IO_API_KEY"):
            SportsDataIOCoreClient()

    def test_init_sets_base_url(self, monkeypatch):
        monkeypatch.setenv("SPORTS_DATA_IO_API_KEY", "test-key")
        from src.sportsdataio_client import SportsDataIOCoreClient

        client = SportsDataIOCoreClient()
        assert client.base_url == "https://api.sportsdata.io/v3/nfl/scores/json"
        assert client.headers["Ocp-Apim-Subscription-Key"] == "test-key"

    @patch("src.sportsdataio_client.requests.get")
    def test_fetch_scores_success(self, mock_get, monkeypatch):
        monkeypatch.setenv("SPORTS_DATA_IO_API_KEY", "test-key")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = SAMPLE_SCORES
        mock_get.return_value = mock_response

        from src.sportsdataio_client import SportsDataIOCoreClient

        client = SportsDataIOCoreClient()
        result = client.fetch_scores(2025)

        assert len(result) == 2
        assert result[0]["HomeTeam"] == "KC"
        mock_get.assert_called_once_with(
            "https://api.sportsdata.io/v3/nfl/scores/json/Scores/2025",
            headers={"Ocp-Apim-Subscription-Key": "test-key"},
        )

    @patch("src.sportsdataio_client.requests.get")
    def test_fetch_scores_http_error(self, mock_get, monkeypatch):
        monkeypatch.setenv("SPORTS_DATA_IO_API_KEY", "test-key")
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_response.raise_for_status.side_effect = Exception("401 Unauthorized")
        mock_get.return_value = mock_response

        from src.sportsdataio_client import SportsDataIOCoreClient

        client = SportsDataIOCoreClient()
        with pytest.raises(Exception, match="401"):
            client.fetch_scores(2025)

    @patch("src.sportsdataio_client.requests.get")
    def test_fetch_player_season_stats_success(self, mock_get, monkeypatch):
        monkeypatch.setenv("SPORTS_DATA_IO_API_KEY", "test-key")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = SAMPLE_PLAYER_STATS
        mock_get.return_value = mock_response

        from src.sportsdataio_client import SportsDataIOCoreClient

        client = SportsDataIOCoreClient()
        result = client.fetch_player_season_stats(2025)

        assert len(result) == 2
        assert result[0]["Name"] == "Patrick Mahomes"
        mock_get.assert_called_once_with(
            "https://api.sportsdata.io/v3/nfl/scores/json/PlayerSeasonStats/2025",
            headers={"Ocp-Apim-Subscription-Key": "test-key"},
        )


# ---------------------------------------------------------------------------
# ingest_bronze_scores tests
# ---------------------------------------------------------------------------


class TestIngestBronzeScores:
    @patch("src.sportsdataio_client.DBManager")
    @patch("src.sportsdataio_client.SportsDataIOCoreClient")
    def test_ingest_scores_writes_to_bq(
        self, mock_client_cls, mock_db_cls, monkeypatch
    ):
        monkeypatch.setenv("SPORTS_DATA_IO_API_KEY", "test-key")

        # Mock API client
        mock_client = MagicMock()
        mock_client.fetch_scores.return_value = SAMPLE_SCORES
        mock_client_cls.return_value = mock_client

        # Mock DBManager context manager
        mock_db = MagicMock()
        mock_db.project_id = "test-project"
        mock_db.dataset_id = "nfl_dead_money"
        mock_db_cls.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_db_cls.return_value.__exit__ = MagicMock(return_value=False)

        mock_job = MagicMock()
        mock_db.client.load_table_from_dataframe.return_value = mock_job

        from src.sportsdataio_client import ingest_bronze_scores

        result = ingest_bronze_scores(seasons=[2025])

        assert result["total_rows"] == 2
        assert result["seasons_fetched"] == 1
        mock_client.fetch_scores.assert_called_once_with(2025)
        mock_db.client.load_table_from_dataframe.assert_called_once()

        # Verify the table ref used
        call_args = mock_db.client.load_table_from_dataframe.call_args
        assert "bronze_sportsdataio_scores" in call_args[0][1]

    @patch("src.sportsdataio_client.DBManager")
    @patch("src.sportsdataio_client.SportsDataIOCoreClient")
    def test_ingest_scores_multiple_seasons(
        self, mock_client_cls, mock_db_cls, monkeypatch
    ):
        monkeypatch.setenv("SPORTS_DATA_IO_API_KEY", "test-key")

        mock_client = MagicMock()
        mock_client.fetch_scores.side_effect = lambda s: SAMPLE_SCORES
        mock_client_cls.return_value = mock_client

        mock_db = MagicMock()
        mock_db.project_id = "test-project"
        mock_db.dataset_id = "nfl_dead_money"
        mock_db_cls.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_db_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_db.client.load_table_from_dataframe.return_value = MagicMock()

        from src.sportsdataio_client import ingest_bronze_scores

        result = ingest_bronze_scores(seasons=[2024, 2025])

        assert result["seasons_fetched"] == 2
        assert result["total_rows"] == 4  # 2 games × 2 seasons

    @patch("src.sportsdataio_client.SportsDataIOCoreClient")
    def test_ingest_scores_empty_response(self, mock_client_cls, monkeypatch):
        monkeypatch.setenv("SPORTS_DATA_IO_API_KEY", "test-key")

        mock_client = MagicMock()
        mock_client.fetch_scores.return_value = []
        mock_client_cls.return_value = mock_client

        from src.sportsdataio_client import ingest_bronze_scores

        result = ingest_bronze_scores(seasons=[2025])

        assert result["seasons_fetched"] == 0
        assert result["total_rows"] == 0

    @patch("src.sportsdataio_client.DBManager")
    @patch("src.sportsdataio_client.SportsDataIOCoreClient")
    def test_ingest_scores_contains_required_columns(
        self, mock_client_cls, mock_db_cls, monkeypatch
    ):
        """Verify the DataFrame written to BQ contains all columns resolve_daily.py needs."""
        monkeypatch.setenv("SPORTS_DATA_IO_API_KEY", "test-key")

        mock_client = MagicMock()
        mock_client.fetch_scores.return_value = SAMPLE_SCORES
        mock_client_cls.return_value = mock_client

        mock_db = MagicMock()
        mock_db.project_id = "test-project"
        mock_db.dataset_id = "nfl_dead_money"
        mock_db_cls.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_db_cls.return_value.__exit__ = MagicMock(return_value=False)

        captured_df = {}

        def capture_load(df, table_ref, job_config=None):
            captured_df["df"] = df
            return MagicMock()

        mock_db.client.load_table_from_dataframe.side_effect = capture_load

        from src.sportsdataio_client import ingest_bronze_scores

        ingest_bronze_scores(seasons=[2025])

        df = captured_df["df"]
        required_cols = {
            "Season",
            "Week",
            "HomeTeam",
            "AwayTeam",
            "HomeScore",
            "AwayScore",
            "IsPlayoffGame",
        }
        assert required_cols.issubset(set(df.columns)), (
            f"Missing columns: {required_cols - set(df.columns)}"
        )


# ---------------------------------------------------------------------------
# ingest_bronze_player_season_stats tests
# ---------------------------------------------------------------------------


class TestIngestBronzePlayerSeasonStats:
    @patch("src.sportsdataio_client.DBManager")
    @patch("src.sportsdataio_client.SportsDataIOCoreClient")
    def test_ingest_player_stats_writes_to_bq(
        self, mock_client_cls, mock_db_cls, monkeypatch
    ):
        monkeypatch.setenv("SPORTS_DATA_IO_API_KEY", "test-key")

        mock_client = MagicMock()
        mock_client.fetch_player_season_stats.return_value = SAMPLE_PLAYER_STATS
        mock_client_cls.return_value = mock_client

        mock_db = MagicMock()
        mock_db.project_id = "test-project"
        mock_db.dataset_id = "nfl_dead_money"
        mock_db_cls.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_db_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_db.client.load_table_from_dataframe.return_value = MagicMock()

        from src.sportsdataio_client import ingest_bronze_player_season_stats

        result = ingest_bronze_player_season_stats(seasons=[2025])

        assert result["total_rows"] == 2
        assert result["seasons_fetched"] == 1
        mock_client.fetch_player_season_stats.assert_called_once_with(2025)

        call_args = mock_db.client.load_table_from_dataframe.call_args
        assert "bronze_sportsdataio_player_season_stats" in call_args[0][1]

    @patch("src.sportsdataio_client.SportsDataIOCoreClient")
    def test_ingest_player_stats_empty_response(self, mock_client_cls, monkeypatch):
        monkeypatch.setenv("SPORTS_DATA_IO_API_KEY", "test-key")

        mock_client = MagicMock()
        mock_client.fetch_player_season_stats.return_value = []
        mock_client_cls.return_value = mock_client

        from src.sportsdataio_client import ingest_bronze_player_season_stats

        result = ingest_bronze_player_season_stats(seasons=[2025])

        assert result["seasons_fetched"] == 0
        assert result["total_rows"] == 0

    @patch("src.sportsdataio_client.DBManager")
    @patch("src.sportsdataio_client.SportsDataIOCoreClient")
    def test_ingest_player_stats_contains_required_columns(
        self, mock_client_cls, mock_db_cls, monkeypatch
    ):
        """Verify the DataFrame written to BQ contains all columns resolve_daily.py needs."""
        monkeypatch.setenv("SPORTS_DATA_IO_API_KEY", "test-key")

        mock_client = MagicMock()
        mock_client.fetch_player_season_stats.return_value = SAMPLE_PLAYER_STATS
        mock_client_cls.return_value = mock_client

        mock_db = MagicMock()
        mock_db.project_id = "test-project"
        mock_db.dataset_id = "nfl_dead_money"
        mock_db_cls.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_db_cls.return_value.__exit__ = MagicMock(return_value=False)

        captured_df = {}

        def capture_load(df, table_ref, job_config=None):
            captured_df["df"] = df
            return MagicMock()

        mock_db.client.load_table_from_dataframe.side_effect = capture_load

        from src.sportsdataio_client import ingest_bronze_player_season_stats

        ingest_bronze_player_season_stats(seasons=[2025])

        df = captured_df["df"]
        required_cols = {
            "Season",
            "Name",
            "PassingYards",
            "PassingTouchdowns",
            "Interceptions",
            "RushingYards",
            "RushingTouchdowns",
            "ReceivingYards",
            "ReceivingTouchdowns",
            "Receptions",
            "Sacks",
            "Tackles",
        }
        assert required_cols.issubset(set(df.columns)), (
            f"Missing columns: {required_cols - set(df.columns)}"
        )

    @patch("src.sportsdataio_client.DBManager")
    @patch("src.sportsdataio_client.SportsDataIOCoreClient")
    def test_ingest_player_stats_api_error_skips_season(
        self, mock_client_cls, mock_db_cls, monkeypatch
    ):
        """If one season fails, others still proceed."""
        monkeypatch.setenv("SPORTS_DATA_IO_API_KEY", "test-key")

        mock_client = MagicMock()
        mock_client.fetch_player_season_stats.side_effect = [
            Exception("API error"),
            SAMPLE_PLAYER_STATS,
        ]
        mock_client_cls.return_value = mock_client

        mock_db = MagicMock()
        mock_db.project_id = "test-project"
        mock_db.dataset_id = "nfl_dead_money"
        mock_db_cls.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_db_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_db.client.load_table_from_dataframe.return_value = MagicMock()

        from src.sportsdataio_client import ingest_bronze_player_season_stats

        result = ingest_bronze_player_season_stats(seasons=[2024, 2025])

        # Only 2025 succeeded
        assert result["seasons_fetched"] == 1
        assert result["total_rows"] == 2
