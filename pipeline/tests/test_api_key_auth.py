"""
Tests for API key authentication middleware (api/api_key_auth.py).
Uses FastAPI TestClient with mocked DBManager and BigQuery client.
No BigQuery connection required.
"""

import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Patch DB initialisation before importing the app
with patch("src.db_manager.DBManager._initialize_connection"):
    from api.main import app
    from api.api_key_auth import _hash_key, verify_api_key, get_db_for_auth
    from api.pundit_router import get_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_bq_row(
    key_id="capk_live_test",
    user_id="user_123",
    tier="free",
    status="active",
    scopes=None,
    name="Test Key",
    created_at=None,
    revoked_at=None,
    last_used_at=None,
    key_last_four="abcd",
):
    """Return a plain dict that behaves like a BigQuery Row (has .items())."""
    return {
        "key_id": key_id,
        "user_id": user_id,
        "tier": tier,
        "status": status,
        "scopes": scopes,
        "name": name,
        "created_at": created_at,
        "revoked_at": revoked_at,
        "last_used_at": last_used_at,
        "key_last_four": key_last_four,
    }


def _mock_query_result(rows):
    """Return a mock BQ job whose .result() yields the given rows."""
    job = MagicMock()
    job.result.return_value = rows
    return job


@pytest.fixture
def mock_auth_db():
    db = MagicMock()
    db.project_id = "test-project"
    db.dataset_id = "nfl_dead_money"
    return db


@pytest.fixture
def mock_pundit_db():
    db = MagicMock()
    db.project_id = "test-project"
    db.dataset_id = "nfl_dead_money"
    return db


@pytest.fixture
def client(mock_auth_db, mock_pundit_db):
    app.dependency_overrides[get_db_for_auth] = lambda: mock_auth_db
    app.dependency_overrides[get_db] = lambda: mock_pundit_db
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Unit tests — _hash_key
# ---------------------------------------------------------------------------


class TestHashKey:
    def test_returns_64_char_hex(self):
        h = _hash_key("capk_live_abc123")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_same_key_same_hash(self):
        assert _hash_key("capk_live_abc") == _hash_key("capk_live_abc")

    def test_different_keys_different_hashes(self):
        assert _hash_key("capk_live_abc") != _hash_key("capk_live_xyz")

    def test_pepper_changes_hash(self):
        with patch.dict(os.environ, {"API_KEY_PEPPER": "pepper1"}):
            h1 = _hash_key("mykey")
        with patch.dict(os.environ, {"API_KEY_PEPPER": "pepper2"}):
            h2 = _hash_key("mykey")
        assert h1 != h2


# ---------------------------------------------------------------------------
# Integration tests — auth middleware via TestClient
# ---------------------------------------------------------------------------


class TestAuthMiddleware:
    def test_missing_key_returns_401(self, client, mock_auth_db):
        # No X-API-Key header — FastAPI will return 422 for missing required header
        resp = client.get("/v1/leaderboard")
        assert resp.status_code in (401, 422)

    def test_invalid_key_returns_401(self, client, mock_auth_db):
        mock_auth_db.client.query.return_value = _mock_query_result([])
        resp = client.get("/v1/leaderboard", headers={"X-API-Key": "capk_live_invalid"})
        assert resp.status_code == 401

    def test_revoked_key_returns_403(self, client, mock_auth_db):
        revoked_row = _make_bq_row(status="revoked")
        mock_auth_db.client.query.return_value = _mock_query_result([revoked_row])
        resp = client.get("/v1/leaderboard", headers={"X-API-Key": "capk_live_revoked"})
        assert resp.status_code == 403

    def test_valid_key_passes_through(self, client, mock_auth_db, mock_pundit_db):
        import pandas as pd

        active_row = _make_bq_row(status="active")
        # first call = auth lookup; second = update last_used_at (fire-and-forget)
        mock_auth_db.client.query.return_value = _mock_query_result([active_row])
        mock_pundit_db.fetch_df.return_value = pd.DataFrame()
        resp = client.get("/v1/leaderboard", headers={"X-API-Key": "capk_live_valid"})
        # 200 or 500 (BQ mock), not 401/403
        assert resp.status_code not in (401, 403)

    def test_health_check_requires_no_key(self, client):
        """/ health check must remain public."""
        resp = client.get("/")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /v1/me
# ---------------------------------------------------------------------------


class TestMeEndpoint:
    def test_returns_key_metadata(self, client, mock_auth_db):
        active_row = _make_bq_row(
            key_id="capk_live_me_test",
            tier="pro",
            status="active",
            key_last_four="1234",
        )
        mock_auth_db.client.query.return_value = _mock_query_result([active_row])
        resp = client.get("/v1/me", headers={"X-API-Key": "capk_live_valid"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["key_id"] == "capk_live_me_test"
        assert data["tier"] == "pro"
        assert data["status"] == "active"
        assert data["key_last_four"] == "1234"

    def test_rate_limit_present(self, client, mock_auth_db):
        active_row = _make_bq_row(tier="api_growth", status="active")
        mock_auth_db.client.query.return_value = _mock_query_result([active_row])
        resp = client.get("/v1/me", headers={"X-API-Key": "capk_live_valid"})
        data = resp.json()
        assert data["rate_limit_per_minute"] == 300

    def test_free_tier_rate_limit(self, client, mock_auth_db):
        active_row = _make_bq_row(tier="free", status="active")
        mock_auth_db.client.query.return_value = _mock_query_result([active_row])
        resp = client.get("/v1/me", headers={"X-API-Key": "capk_live_valid"})
        data = resp.json()
        assert data["rate_limit_per_minute"] == 10

    def test_me_without_key_returns_401_or_422(self, client, mock_auth_db):
        resp = client.get("/v1/me")
        assert resp.status_code in (401, 422)
