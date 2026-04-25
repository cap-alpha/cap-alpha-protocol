"""
Tests for Pundit Scorecard API endpoints (Issue #113, #198, #201).
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


def _mock_bq_job(df):
    """Create a mock BQ query job that returns a DataFrame via to_dataframe()."""
    job = MagicMock()
    job.to_dataframe.return_value = df
    return job


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.project_id = "test-project"
    db.dataset_id = "nfl_dead_money"
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
        # _parameterized_query uses db.client.query() for breakdown
        breakdown_df = pd.DataFrame(
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
        )
        mock_db.client.query.return_value = _mock_bq_job(breakdown_df)
        # get_pundit_accuracy_summary uses db.fetch_df
        mock_db.fetch_df.return_value = make_summary_df()
        resp = client.get("/v1/pundits/adam_schefter")
        assert resp.status_code == 200
        data = resp.json()
        assert "pundit" in data
        assert "accuracy_by_category" in data

    def test_returns_404_for_unknown_pundit(self, client, mock_db):
        mock_db.client.query.return_value = _mock_bq_job(pd.DataFrame())
        mock_db.fetch_df.return_value = make_summary_df()
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
        mock_db.client.query.side_effect = [
            _mock_bq_job(make_predictions_df()),
            _mock_bq_job(pd.DataFrame([{"total": 1}])),
        ]
        resp = client.get("/v1/pundits/adam_schefter/predictions")
        assert resp.status_code == 200

    def test_pagination_fields_present(self, client, mock_db):
        mock_db.fetch_df.side_effect = [
            make_predictions_df(),
        ]
        data = client.get("/v1/pundits/adam_schefter/predictions").json()
        assert "page_size" in data
        assert "has_more" in data
        assert "next_cursor" in data
        assert "predictions" in data

    def test_status_filter_uses_parameterized_query(self, client, mock_db):
        mock_db.client.query.side_effect = [
            _mock_bq_job(make_predictions_df()),
            _mock_bq_job(pd.DataFrame([{"total": 1}])),
        ]
        client.get("/v1/pundits/adam_schefter/predictions?status=CORRECT")
        # Verify parameterized query was used (no string interpolation of status)
        call_args = mock_db.client.query.call_args_list[0]
        sql = call_args[0][0]
        assert "@status" in sql
        # Verify CORRECT is not directly interpolated into SQL
        assert "= 'CORRECT'" not in sql


# ---------------------------------------------------------------------------
# GET /v1/predictions/  (filterable search)
# ---------------------------------------------------------------------------


class TestSearchPredictions:
    def test_returns_200(self, client, mock_db):
        mock_db.client.query.side_effect = [
            _mock_bq_job(make_predictions_df()),
            _mock_bq_job(pd.DataFrame([{"total": 1}])),
        ]
        resp = client.get("/v1/predictions/")
        assert resp.status_code == 200

    def test_pagination_fields(self, client, mock_db):
        mock_db.client.query.side_effect = [
            _mock_bq_job(make_predictions_df()),
            _mock_bq_job(pd.DataFrame([{"total": 1}])),
        ]
        data = client.get("/v1/predictions/").json()
        assert "predictions" in data
        assert "page" in data
        assert "limit" in data
        assert "total" in data
        assert "pages" in data

    def test_category_filter(self, client, mock_db):
        mock_db.client.query.side_effect = [
            _mock_bq_job(make_predictions_df()),
            _mock_bq_job(pd.DataFrame([{"total": 1}])),
        ]
        client.get("/v1/predictions/?category=draft_pick")
        sql = mock_db.client.query.call_args_list[0][0][0]
        assert "@category" in sql

    def test_player_filter(self, client, mock_db):
        mock_db.client.query.side_effect = [
            _mock_bq_job(make_predictions_df()),
            _mock_bq_job(pd.DataFrame([{"total": 1}])),
        ]
        client.get("/v1/predictions/?player=Mahomes")
        sql = mock_db.client.query.call_args_list[0][0][0]
        assert "@player" in sql

    def test_pundit_name_filter(self, client, mock_db):
        mock_db.client.query.side_effect = [
            _mock_bq_job(make_predictions_df()),
            _mock_bq_job(pd.DataFrame([{"total": 1}])),
        ]
        client.get("/v1/predictions/?pundit_name=Schefter")
        sql = mock_db.client.query.call_args_list[0][0][0]
        assert "@pundit_name" in sql

    def test_empty_results(self, client, mock_db):
        mock_db.client.query.side_effect = [
            _mock_bq_job(pd.DataFrame()),
            _mock_bq_job(pd.DataFrame([{"total": 0}])),
        ]
        data = client.get("/v1/predictions/").json()
        assert data["predictions"] == []
        assert data["total"] == 0


# ---------------------------------------------------------------------------
# GET /v1/predictions/recent
# ---------------------------------------------------------------------------


class TestRecentPredictions:
    def test_returns_200(self, client, mock_db):
        mock_db.client.query.return_value = _mock_bq_job(make_predictions_df())
        resp = client.get("/v1/predictions/recent")
        assert resp.status_code == 200

    def test_count_field_present(self, client, mock_db):
        mock_db.client.query.return_value = _mock_bq_job(make_predictions_df())
        data = client.get("/v1/predictions/recent").json()
        assert "count" in data
        assert data["count"] == 1

    def test_limit_param_uses_parameterized_query(self, client, mock_db):
        mock_db.client.query.return_value = _mock_bq_job(pd.DataFrame())
        client.get("/v1/predictions/recent?limit=5")
        sql = mock_db.client.query.call_args[0][0]
        assert "@lim" in sql


# ---------------------------------------------------------------------------
# GET /v1/draft/{year}
# ---------------------------------------------------------------------------


def make_draft_predictions_df():
    return pd.DataFrame(
        [
            {
                "prediction_hash": FAKE_HASH,
                "pundit_id": "adam_schefter",
                "pundit_name": "Adam Schefter",
                "ingestion_timestamp": "2026-04-01T12:00:00Z",
                "source_url": "https://twitter.com/x/456",
                "raw_assertion_text": "Shedeur Sanders goes #1 to Titans",
                "extracted_claim": "Shedeur Sanders picked #1 overall",
                "season_year": 2026,
                "target_player_name": "Shedeur Sanders",
                "target_team": "TEN",
                "resolution_status": "PENDING",
                "resolved_at": None,
                "binary_correct": None,
                "weighted_score": None,
                "outcome_notes": None,
            },
            {
                "prediction_hash": FAKE_HASH2,
                "pundit_id": "pat_mcafee",
                "pundit_name": "Pat McAfee",
                "ingestion_timestamp": "2026-04-02T12:00:00Z",
                "source_url": "https://youtube.com/watch?v=abc",
                "raw_assertion_text": "Cam Ward goes top 5",
                "extracted_claim": "Cam Ward drafted in top 5",
                "season_year": 2026,
                "target_player_name": "Cam Ward",
                "target_team": None,
                "resolution_status": "CORRECT",
                "resolved_at": "2026-04-24T20:00:00Z",
                "binary_correct": True,
                "weighted_score": 1.2,
                "outcome_notes": "Cam Ward picked #2 by CLE",
            },
        ]
    )


class TestDraftSummary:
    def test_returns_200(self, client, mock_db):
        mock_db.client.query.return_value = _mock_bq_job(make_draft_predictions_df())
        resp = client.get("/v1/draft/2026")
        assert resp.status_code == 200

    def test_summary_fields(self, client, mock_db):
        mock_db.client.query.return_value = _mock_bq_job(make_draft_predictions_df())
        data = client.get("/v1/draft/2026").json()
        assert data["year"] == 2026
        assert data["total"] == 2
        assert data["resolved"] == 1
        assert data["pending"] == 1
        assert "predictions" in data

    def test_empty_year(self, client, mock_db):
        mock_db.client.query.return_value = _mock_bq_job(pd.DataFrame())
        data = client.get("/v1/draft/2020").json()
        assert data["total"] == 0
        assert data["resolved"] == 0
        assert data["pending"] == 0

    def test_uses_parameterized_year(self, client, mock_db):
        mock_db.client.query.return_value = _mock_bq_job(pd.DataFrame())
        client.get("/v1/draft/2026")
        sql = mock_db.client.query.call_args[0][0]
        assert "@year" in sql
        assert "2026" not in sql


# ---------------------------------------------------------------------------
# GET /v1/draft/{year}/results
# ---------------------------------------------------------------------------


class TestDraftResults:
    def test_returns_200(self, client, mock_db):
        mock_db.client.query.side_effect = [
            _mock_bq_job(make_draft_predictions_df()),
            _mock_bq_job(
                pd.DataFrame(
                    [
                        {
                            "pundit_id": "adam_schefter",
                            "pundit_name": "Adam Schefter",
                            "total_predictions": 1,
                            "resolved_count": 0,
                            "correct_count": 0,
                            "accuracy_rate": None,
                            "avg_weighted_score": None,
                        }
                    ]
                )
            ),
        ]
        resp = client.get("/v1/draft/2026/results")
        assert resp.status_code == 200

    def test_result_fields(self, client, mock_db):
        mock_db.client.query.side_effect = [
            _mock_bq_job(make_draft_predictions_df()),
            _mock_bq_job(
                pd.DataFrame(
                    [
                        {
                            "pundit_id": "adam_schefter",
                            "pundit_name": "Adam Schefter",
                            "total_predictions": 1,
                            "resolved_count": 0,
                            "correct_count": 0,
                            "accuracy_rate": None,
                            "avg_weighted_score": None,
                        }
                    ]
                )
            ),
        ]
        data = client.get("/v1/draft/2026/results").json()
        assert data["year"] == 2026
        assert data["total"] == 2
        assert "by_status" in data
        assert "pundit_accuracy" in data

    def test_empty_results(self, client, mock_db):
        mock_db.client.query.side_effect = [
            _mock_bq_job(pd.DataFrame()),
            _mock_bq_job(pd.DataFrame()),
        ]
        data = client.get("/v1/draft/2026/results").json()
        assert data["total"] == 0
        assert data["by_status"] == {}
        assert data["pundit_accuracy"] == []


# ---------------------------------------------------------------------------
# GET /v1/integrity/verify
# ---------------------------------------------------------------------------


class TestIntegrityCheck:
    def test_returns_verified_true_when_ok(self, client, mock_db):
        mock_db.fetch_df.return_value = pd.DataFrame()  # empty ledger
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


# ---------------------------------------------------------------------------
# Trade engine endpoints — should return 503 when trade engine unavailable
# ---------------------------------------------------------------------------


class TestTradeEndpointsGuarded:
    @patch("api.main._TRADE_AVAILABLE", False)
    def test_evaluate_returns_503(self, client):
        resp = client.post(
            "/api/trade/evaluate",
            json={
                "team_a": "KC",
                "team_b": "LV",
                "team_a_assets": [],
                "team_b_assets": [],
            },
        )
        assert resp.status_code == 503

    @patch("api.main._TRADE_AVAILABLE", False)
    def test_counter_returns_503(self, client):
        resp = client.post(
            "/api/trade/counter",
            json={
                "team_a": "KC",
                "team_b": "LV",
                "team_a_assets": [],
                "team_b_assets": [],
            },
        )
        assert resp.status_code == 503

    @patch("api.main._TRADE_AVAILABLE", False)
    def test_vegas_returns_503(self, client):
        resp = client.post(
            "/api/analyze/vegas",
            json={
                "team_a": "KC",
                "team_b": "LV",
                "team_a_assets": [],
                "team_b_assets": [],
            },
        )
        assert resp.status_code == 503

    @patch("api.main._TRADE_AVAILABLE", False)
    def test_find_partner_returns_503(self, client):
        resp = client.get("/api/trade/find_partner/P_MAHOMES?cap_hit=45.0")
        assert resp.status_code == 503
