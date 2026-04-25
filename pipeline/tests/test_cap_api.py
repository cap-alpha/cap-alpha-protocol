"""
Tests for the B2B Cap Intelligence API (SP30-1 / GH-#108).
All endpoints require X-API-Key; uses FastAPI TestClient with mocked DBManager.
"""

import os
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient

# Patch DB before importing the app
with patch("src.db_manager.DBManager._initialize_connection"):
    from api.main import app
    from api.cap_router import get_db


VALID_KEY = "test-api-key-abc123"
INVALID_KEY = "bad-key"


def _mock_bq_job(df):
    job = MagicMock()
    job.to_dataframe.return_value = df
    return job


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.project_id = "test-project"
    db.dataset_id = "nfl_dead_money"
    return db


@pytest.fixture
def client(mock_db):
    app.dependency_overrides[get_db] = lambda: mock_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _cap_df():
    return pd.DataFrame([{
        "player_name": "Patrick Mahomes",
        "team": "KAN",
        "year": 2024,
        "position": "QB",
        "cap_hit_millions": 45.0,
        "dead_cap_millions": 10.0,
        "signing_bonus_millions": 20.0,
        "guaranteed_money_millions": 210.0,
        "fair_market_value": 48.0,
        "ml_risk_score": 0.15,
        "edce_risk": 5.2,
        "availability_rating": 1.0,
        "games_played": 17,
    }])


def _team_df():
    return pd.DataFrame([{
        "team": "KAN",
        "year": 2024,
        "total_cap": 230.0,
        "cap_space": 25.4,
        "risk_cap": 30.0,
        "qb_spending": 45.0,
        "wr_spending": 20.0,
        "rb_spending": 5.0,
        "te_spending": 15.0,
        "dl_spending": 10.0,
        "lb_spending": 8.0,
        "db_spending": 12.0,
        "ol_spending": 35.0,
        "k_spending": 1.0,
        "p_spending": 1.0,
        "win_pct": 0.824,
        "win_total": 14.0,
        "conference": "AFC",
    }])


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


class TestApiKeyAuth:
    def test_missing_key_returns_422(self, client, monkeypatch):
        monkeypatch.setenv("B2B_API_KEYS", VALID_KEY)
        resp = client.get("/v1/cap/teams")
        # Missing header → FastAPI validation error (422 Unprocessable Entity)
        assert resp.status_code == 422

    def test_invalid_key_returns_401(self, client, mock_db, monkeypatch):
        monkeypatch.setenv("B2B_API_KEYS", VALID_KEY)
        mock_db.client.query.return_value = _mock_bq_job(_team_df())
        resp = client.get("/v1/cap/teams", headers={"X-API-Key": INVALID_KEY})
        assert resp.status_code == 401

    def test_valid_key_returns_200(self, client, mock_db, monkeypatch):
        monkeypatch.setenv("B2B_API_KEYS", VALID_KEY)
        mock_db.client.query.return_value = _mock_bq_job(_team_df())
        resp = client.get("/v1/cap/teams", headers={"X-API-Key": VALID_KEY})
        assert resp.status_code == 200

    def test_no_keys_configured_allows_access(self, client, mock_db, monkeypatch):
        # When B2B_API_KEYS is not set, auth is disabled (dev mode)
        monkeypatch.delenv("B2B_API_KEYS", raising=False)
        mock_db.client.query.return_value = _mock_bq_job(_team_df())
        resp = client.get("/v1/cap/teams", headers={"X-API-Key": "anything"})
        assert resp.status_code == 200

    def test_multiple_valid_keys(self, client, mock_db, monkeypatch):
        monkeypatch.setenv("B2B_API_KEYS", f"{VALID_KEY},second-key-xyz")
        mock_db.client.query.return_value = _mock_bq_job(_team_df())
        resp = client.get("/v1/cap/teams", headers={"X-API-Key": "second-key-xyz"})
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /v1/cap/players
# ---------------------------------------------------------------------------


class TestCapPlayers:
    def test_returns_200(self, client, mock_db, monkeypatch):
        monkeypatch.delenv("B2B_API_KEYS", raising=False)
        mock_db.client.query.side_effect = [
            _mock_bq_job(_cap_df()),
            _mock_bq_job(pd.DataFrame([{"total": 1}])),
        ]
        resp = client.get("/v1/cap/players", headers={"X-API-Key": "dev"})
        assert resp.status_code == 200

    def test_response_structure(self, client, mock_db, monkeypatch):
        monkeypatch.delenv("B2B_API_KEYS", raising=False)
        mock_db.client.query.side_effect = [
            _mock_bq_job(_cap_df()),
            _mock_bq_job(pd.DataFrame([{"total": 1}])),
        ]
        data = client.get("/v1/cap/players", headers={"X-API-Key": "dev"}).json()
        assert "players" in data
        assert "page" in data
        assert "limit" in data
        assert "total" in data

    def test_year_filter_parameterized(self, client, mock_db, monkeypatch):
        monkeypatch.delenv("B2B_API_KEYS", raising=False)
        mock_db.client.query.side_effect = [
            _mock_bq_job(_cap_df()),
            _mock_bq_job(pd.DataFrame([{"total": 1}])),
        ]
        client.get("/v1/cap/players?year=2024", headers={"X-API-Key": "dev"})
        sql = mock_db.client.query.call_args_list[0][0][0]
        assert "@year" in sql

    def test_position_filter_parameterized(self, client, mock_db, monkeypatch):
        monkeypatch.delenv("B2B_API_KEYS", raising=False)
        mock_db.client.query.side_effect = [
            _mock_bq_job(_cap_df()),
            _mock_bq_job(pd.DataFrame([{"total": 1}])),
        ]
        client.get("/v1/cap/players?position=QB", headers={"X-API-Key": "dev"})
        sql = mock_db.client.query.call_args_list[0][0][0]
        assert "@position" in sql
        assert "QB" not in sql  # must not be string-interpolated

    def test_team_filter_parameterized(self, client, mock_db, monkeypatch):
        monkeypatch.delenv("B2B_API_KEYS", raising=False)
        mock_db.client.query.side_effect = [
            _mock_bq_job(_cap_df()),
            _mock_bq_job(pd.DataFrame([{"total": 1}])),
        ]
        client.get("/v1/cap/players?team=KAN", headers={"X-API-Key": "dev"})
        sql = mock_db.client.query.call_args_list[0][0][0]
        assert "@team" in sql

    def test_db_error_returns_500(self, client, mock_db, monkeypatch):
        monkeypatch.delenv("B2B_API_KEYS", raising=False)
        mock_db.client.query.side_effect = Exception("BQ down")
        resp = client.get("/v1/cap/players", headers={"X-API-Key": "dev"})
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# GET /v1/cap/players/{player_name}
# ---------------------------------------------------------------------------


class TestCapPlayerProfile:
    def test_returns_200_for_known_player(self, client, mock_db, monkeypatch):
        monkeypatch.delenv("B2B_API_KEYS", raising=False)
        mock_db.client.query.return_value = _mock_bq_job(_cap_df())
        resp = client.get(
            "/v1/cap/players/Patrick Mahomes", headers={"X-API-Key": "dev"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "player_name" in data
        assert "seasons" in data
        assert "season_count" in data

    def test_returns_404_for_unknown_player(self, client, mock_db, monkeypatch):
        monkeypatch.delenv("B2B_API_KEYS", raising=False)
        mock_db.client.query.return_value = _mock_bq_job(pd.DataFrame())
        resp = client.get("/v1/cap/players/Unknown Player", headers={"X-API-Key": "dev"})
        assert resp.status_code == 404

    def test_query_uses_parameterized_player_name(self, client, mock_db, monkeypatch):
        monkeypatch.delenv("B2B_API_KEYS", raising=False)
        mock_db.client.query.return_value = _mock_bq_job(_cap_df())
        client.get("/v1/cap/players/Patrick Mahomes", headers={"X-API-Key": "dev"})
        sql = mock_db.client.query.call_args[0][0]
        assert "@player_name" in sql
        # Player name must not be directly interpolated
        assert "Patrick Mahomes" not in sql


# ---------------------------------------------------------------------------
# GET /v1/cap/teams
# ---------------------------------------------------------------------------


class TestCapTeams:
    def test_returns_200(self, client, mock_db, monkeypatch):
        monkeypatch.delenv("B2B_API_KEYS", raising=False)
        mock_db.client.query.return_value = _mock_bq_job(_team_df())
        resp = client.get("/v1/cap/teams", headers={"X-API-Key": "dev"})
        assert resp.status_code == 200

    def test_response_has_teams_and_total(self, client, mock_db, monkeypatch):
        monkeypatch.delenv("B2B_API_KEYS", raising=False)
        mock_db.client.query.return_value = _mock_bq_job(_team_df())
        data = client.get("/v1/cap/teams", headers={"X-API-Key": "dev"}).json()
        assert "teams" in data
        assert "total" in data
        assert data["total"] == 1

    def test_year_filter_parameterized(self, client, mock_db, monkeypatch):
        monkeypatch.delenv("B2B_API_KEYS", raising=False)
        mock_db.client.query.return_value = _mock_bq_job(_team_df())
        client.get("/v1/cap/teams?year=2024", headers={"X-API-Key": "dev"})
        sql = mock_db.client.query.call_args[0][0]
        assert "@year" in sql

    def test_conference_filter_parameterized(self, client, mock_db, monkeypatch):
        monkeypatch.delenv("B2B_API_KEYS", raising=False)
        mock_db.client.query.return_value = _mock_bq_job(_team_df())
        client.get("/v1/cap/teams?conference=AFC", headers={"X-API-Key": "dev"})
        sql = mock_db.client.query.call_args[0][0]
        assert "@conference" in sql


# ---------------------------------------------------------------------------
# GET /v1/cap/fmv/{player_name}
# ---------------------------------------------------------------------------


class TestCapFmvTrajectory:
    def _make_multi_year_df(self):
        return pd.DataFrame([
            {
                "year": 2023, "team": "KAN", "position": "QB",
                "cap_hit_millions": 40.0, "dead_cap_millions": 8.0,
                "fair_market_value": 42.0, "edce_risk": 4.0,
                "efficiency_ratio": 1.1, "true_bust_variance": 0.0,
                "ytd_performance_value": 44.0, "ml_risk_score": 0.12,
                "availability_rating": 1.0, "games_played": 17,
            },
            {
                "year": 2024, "team": "KAN", "position": "QB",
                "cap_hit_millions": 45.0, "dead_cap_millions": 10.0,
                "fair_market_value": 48.0, "edce_risk": 5.2,
                "efficiency_ratio": 1.07, "true_bust_variance": 0.0,
                "ytd_performance_value": 48.0, "ml_risk_score": 0.15,
                "availability_rating": 1.0, "games_played": 17,
            },
        ])

    def test_returns_200(self, client, mock_db, monkeypatch):
        monkeypatch.delenv("B2B_API_KEYS", raising=False)
        mock_db.client.query.return_value = _mock_bq_job(self._make_multi_year_df())
        resp = client.get(
            "/v1/cap/fmv/Patrick Mahomes", headers={"X-API-Key": "dev"}
        )
        assert resp.status_code == 200

    def test_response_includes_trajectory(self, client, mock_db, monkeypatch):
        monkeypatch.delenv("B2B_API_KEYS", raising=False)
        mock_db.client.query.return_value = _mock_bq_job(self._make_multi_year_df())
        data = client.get(
            "/v1/cap/fmv/Patrick Mahomes", headers={"X-API-Key": "dev"}
        ).json()
        assert "trajectory" in data
        assert data["trajectory"] == "improving"  # FMV went 42 → 48

    def test_declining_trajectory(self, client, mock_db, monkeypatch):
        monkeypatch.delenv("B2B_API_KEYS", raising=False)
        df = self._make_multi_year_df()
        df.loc[df["year"] == 2024, "fair_market_value"] = 38.0  # dropped
        mock_db.client.query.return_value = _mock_bq_job(df)
        data = client.get(
            "/v1/cap/fmv/Patrick Mahomes", headers={"X-API-Key": "dev"}
        ).json()
        assert data["trajectory"] == "declining"

    def test_returns_404_for_unknown_player(self, client, mock_db, monkeypatch):
        monkeypatch.delenv("B2B_API_KEYS", raising=False)
        mock_db.client.query.return_value = _mock_bq_job(pd.DataFrame())
        resp = client.get("/v1/cap/fmv/Unknown Player", headers={"X-API-Key": "dev"})
        assert resp.status_code == 404

    def test_query_is_parameterized(self, client, mock_db, monkeypatch):
        monkeypatch.delenv("B2B_API_KEYS", raising=False)
        mock_db.client.query.return_value = _mock_bq_job(self._make_multi_year_df())
        client.get("/v1/cap/fmv/Patrick Mahomes", headers={"X-API-Key": "dev"})
        sql = mock_db.client.query.call_args[0][0]
        assert "@player_name" in sql


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


class TestRateLimiting:
    def test_rate_limit_enforced_after_quota(self, client, mock_db, monkeypatch):
        from api import api_key_auth

        monkeypatch.setenv("B2B_API_KEYS", "rate-test-key")
        monkeypatch.setenv("B2B_RATE_LIMIT_RPH", "2")

        # Clear in-memory state for this test key
        with api_key_auth._lock:
            api_key_auth._request_log.pop("rate-test-key", None)

        mock_db.client.query.return_value = _mock_bq_job(_team_df())

        # First 2 requests should succeed
        for _ in range(2):
            resp = client.get(
                "/v1/cap/teams", headers={"X-API-Key": "rate-test-key"}
            )
            assert resp.status_code == 200

        # 3rd request should be rate-limited
        resp = client.get("/v1/cap/teams", headers={"X-API-Key": "rate-test-key"})
        assert resp.status_code == 429
        assert "Rate limit exceeded" in resp.json()["detail"]

    def test_rate_limit_response_has_retry_after(self, client, mock_db, monkeypatch):
        from api import api_key_auth

        monkeypatch.setenv("B2B_API_KEYS", "retry-test-key")
        monkeypatch.setenv("B2B_RATE_LIMIT_RPH", "1")

        with api_key_auth._lock:
            api_key_auth._request_log.pop("retry-test-key", None)

        mock_db.client.query.return_value = _mock_bq_job(_team_df())

        client.get("/v1/cap/teams", headers={"X-API-Key": "retry-test-key"})
        resp = client.get("/v1/cap/teams", headers={"X-API-Key": "retry-test-key"})
        assert resp.status_code == 429
        assert "Retry-After" in resp.headers
