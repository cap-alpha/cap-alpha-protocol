"""
Tests for Cap Intelligence API endpoints (SP30-1, Issue #108).
Uses FastAPI TestClient with mocked DBManager and mocked API key validation.
"""

import hashlib
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient

with patch("src.db_manager.DBManager._initialize_connection"):
    from api.main import app
    from api.cap_router import get_db, require_api_key

VALID_KEY_META = {"owner": "acme_corp", "tier": "standard", "daily_limit": 1000}

PLAYER_ROW = {
    "player_name": "Patrick Mahomes",
    "team": "KC",
    "position": "QB",
    "year": 2025,
    "age": 29,
    "games_played": 17,
    "cap_hit_millions": 45.0,
    "dead_cap_millions": 0.0,
    "risk_score": 0.12,
    "fair_market_value": 52.0,
    "edce_risk": 1.1,
    "risk_tier": "SAFE",
    "computed_at": "2026-04-01T00:00:00Z",
}

TEAM_ROW = {
    "team": "KC",
    "player_count": 53,
    "total_cap": 220.5,
    "risk_cap": 40.0,
    "avg_age": 26.2,
    "avg_risk_score": 0.35,
    "total_dead_cap": 5.0,
    "total_surplus_value": 180.0,
    "computed_at": "2026-04-01T00:00:00Z",
}


@pytest.fixture
def mock_db():
    db = MagicMock()
    mock_job = MagicMock()
    mock_job.result.return_value = None
    db.client.load_table_from_dataframe.return_value = mock_job
    return db


@pytest.fixture
def client(mock_db):
    # Override both the DB dependency and the API key validation
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[require_api_key] = lambda: VALID_KEY_META
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def client_no_key(mock_db):
    """Client without API key override — tests authentication enforcement."""
    app.dependency_overrides[get_db] = lambda: mock_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# GET /v1/cap/players
# ---------------------------------------------------------------------------


class TestListPlayers:
    def test_returns_200(self, client, mock_db):
        mock_db.fetch_df.return_value = pd.DataFrame([PLAYER_ROW])
        resp = client.get("/v1/cap/players")
        assert resp.status_code == 200

    def test_response_has_players_key(self, client, mock_db):
        mock_db.fetch_df.return_value = pd.DataFrame([PLAYER_ROW])
        data = client.get("/v1/cap/players").json()
        assert "players" in data
        assert "has_more" in data
        assert "next_cursor" in data

    def test_empty_result(self, client, mock_db):
        mock_db.fetch_df.return_value = pd.DataFrame(columns=PLAYER_ROW.keys())
        data = client.get("/v1/cap/players").json()
        assert data["players"] == []
        assert data["has_more"] is False

    def test_team_filter_passed_to_query(self, client, mock_db):
        mock_db.fetch_df.return_value = pd.DataFrame([PLAYER_ROW])
        client.get("/v1/cap/players?team=KC")
        sql = mock_db.fetch_df.call_args[0][0]
        assert "KC" in sql

    def test_risk_tier_filter_uppercased(self, client, mock_db):
        mock_db.fetch_df.return_value = pd.DataFrame([PLAYER_ROW])
        client.get("/v1/cap/players?risk_tier=safe")
        sql = mock_db.fetch_df.call_args[0][0]
        assert "SAFE" in sql

    def test_keyset_cursor_in_query(self, client, mock_db):
        mock_db.fetch_df.return_value = pd.DataFrame([PLAYER_ROW])
        client.get("/v1/cap/players?before=Patrick+Mahomes")
        sql = mock_db.fetch_df.call_args[0][0]
        assert "player_name > " in sql


# ---------------------------------------------------------------------------
# GET /v1/cap/players/{player_name}
# ---------------------------------------------------------------------------


class TestGetPlayer:
    def test_returns_200_for_known_player(self, client, mock_db):
        mock_db.fetch_df.return_value = pd.DataFrame([PLAYER_ROW])
        resp = client.get("/v1/cap/players/Patrick%20Mahomes")
        assert resp.status_code == 200

    def test_returns_404_for_unknown_player(self, client, mock_db):
        mock_db.fetch_df.return_value = pd.DataFrame(columns=PLAYER_ROW.keys())
        resp = client.get("/v1/cap/players/Fake%20Player")
        assert resp.status_code == 404

    def test_response_has_player_key(self, client, mock_db):
        mock_db.fetch_df.return_value = pd.DataFrame([PLAYER_ROW])
        data = client.get("/v1/cap/players/Patrick%20Mahomes").json()
        assert "player" in data
        assert data["player"]["player_name"] == "Patrick Mahomes"


# ---------------------------------------------------------------------------
# GET /v1/cap/teams
# ---------------------------------------------------------------------------


class TestListTeams:
    def test_returns_200(self, client, mock_db):
        mock_db.fetch_df.return_value = pd.DataFrame([TEAM_ROW])
        resp = client.get("/v1/cap/teams")
        assert resp.status_code == 200

    def test_response_has_teams_key(self, client, mock_db):
        mock_db.fetch_df.return_value = pd.DataFrame([TEAM_ROW])
        data = client.get("/v1/cap/teams").json()
        assert "teams" in data
        assert "count" in data

    def test_db_error_returns_500(self, client, mock_db):
        mock_db.fetch_df.side_effect = Exception("BQ error")
        resp = client.get("/v1/cap/teams")
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# GET /v1/cap/teams/{team}
# ---------------------------------------------------------------------------


class TestGetTeam:
    def test_returns_200_for_known_team(self, client, mock_db):
        mock_db.fetch_df.side_effect = [
            pd.DataFrame([TEAM_ROW]),
            pd.DataFrame([PLAYER_ROW]),
        ]
        resp = client.get("/v1/cap/teams/KC")
        assert resp.status_code == 200

    def test_returns_404_for_unknown_team(self, client, mock_db):
        mock_db.fetch_df.return_value = pd.DataFrame(columns=TEAM_ROW.keys())
        resp = client.get("/v1/cap/teams/INVALID")
        assert resp.status_code == 404

    def test_response_has_team_and_roster(self, client, mock_db):
        mock_db.fetch_df.side_effect = [
            pd.DataFrame([TEAM_ROW]),
            pd.DataFrame([PLAYER_ROW]),
        ]
        data = client.get("/v1/cap/teams/KC").json()
        assert "team" in data
        assert "roster" in data
        assert data["team"]["team"] == "KC"


# ---------------------------------------------------------------------------
# Authentication enforcement
# ---------------------------------------------------------------------------


class TestApiKeyAuth:
    def test_missing_key_rejected(self, client_no_key, mock_db):
        # FastAPI returns 422 for a missing required header (validation error
        # before the dependency runs); both 401 and 422 indicate rejection.
        mock_db.fetch_df.return_value = pd.DataFrame()
        resp = client_no_key.get("/v1/cap/players")
        assert resp.status_code in (401, 422)

    def test_invalid_key_returns_401(self, client_no_key, mock_db):
        mock_db.fetch_df.return_value = pd.DataFrame()  # empty = key not found
        resp = client_no_key.get(
            "/v1/cap/players", headers={"X-API-Key": "notarealkey"}
        )
        assert resp.status_code == 401

    def test_revoked_key_returns_403(self, client_no_key, mock_db):
        mock_db.fetch_df.return_value = pd.DataFrame(
            [{"owner": "x", "tier": "free", "is_active": False, "daily_limit": 100}]
        )
        key_hash = hashlib.sha256(b"testkey").hexdigest()
        resp = client_no_key.get(
            "/v1/cap/players", headers={"X-API-Key": "testkey"}
        )
        assert resp.status_code == 403
