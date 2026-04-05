"""
Tests for Pundit Scorecard API endpoints (Issue #113).
Uses FastAPI TestClient with mocked DBManager — no BigQuery required.
"""

import os
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient

# Patch DB before importing the app so startup doesn't attempt BQ connection
with patch("src.db_manager.DBManager._initialize_connection"):
    from api.main import app
    from api.pundit_router import get_db

FAKE_HASH = "a" * 64
FAKE_HASH2 = "b" * 64


@pytest.fixture
def mock_db():
    db = MagicMock()
    mock_job = MagicMock()
    mock_job.result.return_value = None
    db.client.load_table_from_dataframe.return_value = mock_job
    return db


@pytest.fixture
def client(mock_db):
    app.dependency_overrides[get_db] = lambda: mock_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def make_summary_df():
    return pd.DataFrame(
        [
            {
                "pundit_id": "adam_schefter",
                "pundit_name": "Adam Schefter",
                "total_predictions": 100,
                "resolved_count": 80,
                "correct_count": 60,
                "accuracy_rate": 0.75,
                "avg_brier_score": 0.18,
                "avg_weighted_score": 0.9,
            },
            {
                "pundit_id": "pat_mcafee",
                "pundit_name": "Pat McAfee",
                "total_predictions": 50,
                "resolved_count": 40,
                "correct_count": 25,
                "accuracy_rate": 0.625,
                "avg_brier_score": 0.25,
                "avg_weighted_score": 0.7,
            },
        ]
    )


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


def test_health_check(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# GET /v1/leaderboard
# ---------------------------------------------------------------------------


class TestLeaderboard:
    def test_returns_200(self, client, mock_db):
        mock_db.fetch_df.return_value = make_summary_df()
        resp = client.get("/v1/leaderboard")
        assert resp.status_code == 200

    def test_returns_leaderboard_list(self, client, mock_db):
        mock_db.fetch_df.return_value = make_summary_df()
        data = client.get("/v1/leaderboard").json()
        assert "leaderboard" in data
        assert len(data["leaderboard"]) == 2

    def test_total_field_present(self, client, mock_db):
        mock_db.fetch_df.return_value = make_summary_df()
        data = client.get("/v1/leaderboard").json()
        assert data["total"] == 2

    def test_empty_leaderboard(self, client, mock_db):
        mock_db.fetch_df.return_value = pd.DataFrame()
        data = client.get("/v1/leaderboard").json()
        assert data["leaderboard"] == []

    def test_limit_param(self, client, mock_db):
        mock_db.fetch_df.return_value = make_summary_df()
        data = client.get("/v1/leaderboard?limit=1").json()
        assert len(data["leaderboard"]) == 1

    def test_db_error_returns_500(self, client, mock_db):
        mock_db.fetch_df.side_effect = Exception("BQ down")
        resp = client.get("/v1/leaderboard")
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# GET /v1/pundits/
# ---------------------------------------------------------------------------


class TestListPundits:
    def test_returns_200(self, client, mock_db):
        mock_db.fetch_df.return_value = make_summary_df()
        resp = client.get("/v1/pundits/")
        assert resp.status_code == 200

    def test_contains_pundits_key(self, client, mock_db):
        mock_db.fetch_df.return_value = make_summary_df()
        data = client.get("/v1/pundits/").json()
        assert "pundits" in data
        assert data["total"] == 2


# ---------------------------------------------------------------------------
# GET /v1/pundits/{pundit_id}
# ---------------------------------------------------------------------------


class TestPunditDetail:
    def test_returns_200_for_known_pundit(self, client, mock_db):
        mock_db.fetch_df.side_effect = [
            pd.DataFrame(  # breakdown by category
                [
                    {
                        "claim_category": "player_performance",
                        "total": 50,
                        "resolved": 40,
                        "correct": 30,
                        "accuracy_rate": 0.75,
                        "avg_weighted_score": 0.9,
                    }
                ]
            ),
            make_summary_df(),  # summary for pundit lookup
        ]
        resp = client.get("/v1/pundits/adam_schefter")
        assert resp.status_code == 200
        data = resp.json()
        assert "pundit" in data
        assert "accuracy_by_category" in data

    def test_returns_404_for_unknown_pundit(self, client, mock_db):
        mock_db.fetch_df.side_effect = [
            pd.DataFrame(),  # empty breakdown
            make_summary_df(),  # summary (doesn't contain unknown_pundit)
        ]
        resp = client.get("/v1/pundits/unknown_pundit")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /v1/pundits/{pundit_id}/predictions
# ---------------------------------------------------------------------------


def make_predictions_df():
    return pd.DataFrame(
        [
            {
                "prediction_hash": FAKE_HASH,
                "pundit_id": "adam_schefter",
                "pundit_name": "Adam Schefter",
                "ingestion_timestamp": "2025-09-01T12:00:00Z",
                "source_url": "https://twitter.com/x/123",
                "raw_assertion_text": "Mahomes wins MVP",
                "extracted_claim": "Mahomes wins MVP",
                "claim_category": "player_performance",
                "season_year": 2025,
                "target_player_id": "P_MAHOMES",
                "target_team": "KC",
                "resolution_status": "CORRECT",
                "resolved_at": "2026-02-01T20:00:00Z",
                "binary_correct": True,
                "brier_score": None,
                "weighted_score": 1.5,
                "outcome_notes": "Mahomes won AP MVP",
            }
        ]
    )


class TestPunditPredictions:
    def test_returns_200(self, client, mock_db):
        mock_db.fetch_df.side_effect = [
            make_predictions_df(),
            pd.DataFrame([{"total": 1}]),
        ]
        resp = client.get("/v1/pundits/adam_schefter/predictions")
        assert resp.status_code == 200

    def test_pagination_fields_present(self, client, mock_db):
        mock_db.fetch_df.side_effect = [
            make_predictions_df(),
            pd.DataFrame([{"total": 1}]),
        ]
        data = client.get("/v1/pundits/adam_schefter/predictions").json()
        assert "page" in data
        assert "page_size" in data
        assert "total" in data
        assert "pages" in data
        assert "predictions" in data

    def test_status_filter_passed_to_query(self, client, mock_db):
        mock_db.fetch_df.side_effect = [
            make_predictions_df(),
            pd.DataFrame([{"total": 1}]),
        ]
        client.get("/v1/pundits/adam_schefter/predictions?status=CORRECT")
        query = mock_db.fetch_df.call_args_list[0][0][0]
        assert "CORRECT" in query


# ---------------------------------------------------------------------------
# GET /v1/predictions/recent
# ---------------------------------------------------------------------------


class TestRecentPredictions:
    def test_returns_200(self, client, mock_db):
        mock_db.fetch_df.return_value = make_predictions_df()
        resp = client.get("/v1/predictions/recent")
        assert resp.status_code == 200

    def test_count_field_present(self, client, mock_db):
        mock_db.fetch_df.return_value = make_predictions_df()
        data = client.get("/v1/predictions/recent").json()
        assert "count" in data
        assert data["count"] == 1

    def test_limit_param(self, client, mock_db):
        mock_db.fetch_df.return_value = pd.DataFrame()
        client.get("/v1/predictions/recent?limit=5")
        query = mock_db.fetch_df.call_args[0][0]
        assert "LIMIT 5" in query


# ---------------------------------------------------------------------------
# GET /v1/integrity/verify
# ---------------------------------------------------------------------------


class TestIntegrityCheck:
    def test_returns_verified_true_when_ok(self, client, mock_db):
        mock_db.fetch_df.return_value = pd.DataFrame()  # empty ledger → verified
        resp = client.get("/v1/integrity/verify")
        assert resp.status_code == 200
        data = resp.json()
        assert data["verified"] is True
        assert data["total_records"] == 0

    def test_returns_verified_false_when_tampered(self, client, mock_db):
        from src.cryptographic_ledger import HASH_SEED, compute_chain_hash

        h0 = "a" * 64
        mock_db.fetch_df.return_value = pd.DataFrame(
            [
                {
                    "prediction_hash": h0,
                    "chain_hash": "tampered" + "0" * 56,
                    "ingestion_timestamp": "2025-09-01T12:00:00Z",
                    "source_url": "https://x.com",
                    "pundit_id": "test",
                    "raw_assertion_text": "test",
                }
            ]
        )
        resp = client.get("/v1/integrity/verify")
        assert resp.status_code == 200
        data = resp.json()
        assert data["verified"] is False
