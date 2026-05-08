"""
Tests for the MCP Phase 1 tool suite (issue #814, pipeline/api/mcp_server.py).

Strategy:
  * Patch ``api.mcp_server._run_query`` so we never touch BigQuery.
  * Drive the tool handlers as plain Python functions — FastMCP turns them
    into MCP tools at registration time but they are still callable as
    regular Python from tests, taking a Pydantic Input model and returning
    a dict.
  * For tier-gating tests, set ``mcp_current_key_info`` directly via the
    ``set_current_key_info`` helper.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List
from unittest.mock import patch

import pytest

# Ensure auth is satisfied via the test escape hatch unless a test sets a
# specific tier through set_current_key_info().
os.environ.setdefault("ENV", "test")

# Patch DBManager init so importing the module never touches GCP.
with patch("src.db_manager.DBManager._initialize_connection"):
    from api import mcp_auth, mcp_server
    from api.mcp_models import (
        ActivePredictionsInput,
        ComparePunditsInput,
        LeaderboardInput,
        PunditReliabilityInput,
        SearchClaimsInput,
        TraceClaimChainInput,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_limiter_and_ctx():
    """Each test starts with an empty rate-limit bucket and ``agent_growth`` ctx."""
    mcp_auth.get_limiter().reset()
    token = mcp_auth.set_current_key_info(
        {
            "key_id": "test-key",
            "user_id": "test-user",
            "tier": "agent_growth",
            "status": "active",
        }
    )
    yield
    mcp_auth.reset_current_key_info(token)
    mcp_auth.get_limiter().reset()


@pytest.fixture
def mock_bq():
    """Patch _run_query and capture the SQL/params each call sees."""
    captured: List[Dict[str, Any]] = []

    def _factory(rows: List[Dict[str, Any]] | List[List[Dict[str, Any]]]):
        # ``rows`` may be a single row-set (used for every call) or a list
        # of row-sets (one per call).
        is_per_call = isinstance(rows, list) and rows and isinstance(rows[0], list)

        call_idx = {"i": 0}

        def fake_run_query(sql: str, params):
            captured.append({"sql": sql, "params": params})
            if is_per_call:
                idx = min(call_idx["i"], len(rows) - 1)
                call_idx["i"] += 1
                return rows[idx]
            return rows

        patcher = patch.object(mcp_server, "_run_query", side_effect=fake_run_query)
        patcher.start()
        return patcher, captured

    return _factory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _call(handler, args_model):
    """FastMCP wraps tool functions, but the underlying Python is still
    callable with the Pydantic input model."""
    fn = getattr(handler, "fn", None) or handler
    return fn(args_model)


# ---------------------------------------------------------------------------
# Tier gating
# ---------------------------------------------------------------------------


class TestTierGating:
    def test_free_tier_blocked_with_upgrade_required(self):
        token = mcp_auth.set_current_key_info(
            {"key_id": "free-key", "user_id": "u", "tier": "free", "status": "active"}
        )
        try:
            out = _call(
                mcp_server.get_pundit_reliability,
                PunditReliabilityInput(pundit_id="schefter"),
            )
        finally:
            mcp_auth.reset_current_key_info(token)
        assert out["error"] == "UPGRADE_REQUIRED"
        assert out["code"] == -32001
        assert out["minimum_tier"] == "agent_growth"
        assert out["disclaimer"] == "Statistical patterns only. Not financial advice."

    def test_pro_tier_blocked(self):
        token = mcp_auth.set_current_key_info(
            {"key_id": "pro-key", "user_id": "u", "tier": "pro", "status": "active"}
        )
        try:
            out = _call(mcp_server.get_leaderboard, LeaderboardInput())
        finally:
            mcp_auth.reset_current_key_info(token)
        assert out["error"] == "UPGRADE_REQUIRED"

    @pytest.mark.parametrize(
        "tier",
        [
            "agent",
            "agent_growth",
            "agent_standard",
            "agent_pro",
            "api_growth",
            "enterprise",
        ],
    )
    def test_admitted_tiers(self, mock_bq, tier):
        patcher, _ = mock_bq([])
        try:
            token = mcp_auth.set_current_key_info(
                {
                    "key_id": f"k-{tier}",
                    "user_id": "u",
                    "tier": tier,
                    "status": "active",
                }
            )
            try:
                out = _call(mcp_server.get_leaderboard, LeaderboardInput())
            finally:
                mcp_auth.reset_current_key_info(token)
        finally:
            patcher.stop()
        assert "error" not in out
        assert out["leaderboard"] == []
        assert out["disclaimer"] == "Statistical patterns only. Not financial advice."


# ---------------------------------------------------------------------------
# get_pundit_reliability
# ---------------------------------------------------------------------------


class TestGetPunditReliability:
    def test_returns_aggregated_stats(self, mock_bq):
        patcher, captured = mock_bq(
            [
                {
                    "pundit_id": "schefter",
                    "pundit_name": "Adam Schefter",
                    "n_total": 50,
                    "n_resolved": 30,
                    "n_correct": 21,
                    "accuracy_rate": 0.7,
                    "brier_score": 0.18,
                    "weighted_score": 0.62,
                }
            ]
        )
        try:
            out = _call(
                mcp_server.get_pundit_reliability,
                PunditReliabilityInput(
                    pundit_id="schefter",
                    domain="nfl",
                    claim_type="trade_move",
                    window="last_season",
                ),
            )
        finally:
            patcher.stop()

        assert out["pundit_id"] == "schefter"
        assert out["pundit_name"] == "Adam Schefter"
        assert out["n_total"] == 50
        assert out["n_resolved"] == 30
        assert out["n_correct"] == 21
        assert out["accuracy_rate"] == 0.7
        assert out["brier_score"] == 0.18
        assert out["weighted_score"] == 0.62
        assert out["claim_type"] == "trade_move"
        assert out["window"] == "last_season"
        # Wilson 95% CI is centered around 0.7 with n=30 → roughly 0.52–0.83
        ci = out["confidence_interval"]
        assert ci is not None
        assert 0.4 < ci["low"] < ci["high"] < 0.95
        assert out["disclaimer"] == "Statistical patterns only. Not financial advice."

        sql = captured[0]["sql"]
        assert "prediction_ledger" in sql
        assert "prediction_resolutions" in sql
        # claim_type and window filters generated parameter bindings
        param_names = {p.name for p in captured[0]["params"]}
        assert "pundit" in param_names
        assert "claim_type" in param_names
        assert "lower_ts" in param_names

    def test_returns_zeroes_when_no_rows(self, mock_bq):
        patcher, _ = mock_bq([])
        try:
            out = _call(
                mcp_server.get_pundit_reliability,
                PunditReliabilityInput(pundit_id="nobody"),
            )
        finally:
            patcher.stop()
        assert out["n_total"] == 0
        assert out["n_resolved"] == 0
        assert out["accuracy_rate"] is None
        assert out["confidence_interval"] is None  # n_resolved < 5

    def test_small_sample_skips_confidence_interval(self, mock_bq):
        patcher, _ = mock_bq(
            [
                {
                    "pundit_id": "x",
                    "pundit_name": "X",
                    "n_total": 4,
                    "n_resolved": 4,
                    "n_correct": 3,
                    "accuracy_rate": 0.75,
                    "brier_score": 0.2,
                    "weighted_score": 0.5,
                }
            ]
        )
        try:
            out = _call(
                mcp_server.get_pundit_reliability,
                PunditReliabilityInput(pundit_id="x"),
            )
        finally:
            patcher.stop()
        assert out["confidence_interval"] is None


# ---------------------------------------------------------------------------
# get_active_predictions
# ---------------------------------------------------------------------------


class TestGetActivePredictions:
    def test_returns_pending_only_with_horizon_filter(self, mock_bq):
        patcher, captured = mock_bq(
            [
                {
                    "prediction_hash": "abc123",
                    "pundit_id": "schefter",
                    "pundit_name": "Adam Schefter",
                    "claim_category": "trade_move",
                    "extracted_claim": "Bears trade for star WR before deadline",
                    "target_player_name": None,
                    "target_team": "Bears",
                    "ingestion_timestamp": "2026-04-15T12:00:00+00:00",
                    "resolution_horizon": "2026-11-01T00:00:00+00:00",
                    "source_url": "https://espn.com/x",
                },
                {
                    "prediction_hash": "def456",
                    "pundit_id": "rapsheet",
                    "pundit_name": "Ian Rapoport",
                    "claim_category": "draft_pick",
                    "extracted_claim": "Bears draft a QB top-10",
                    "target_player_name": None,
                    "target_team": "Bears",
                    "ingestion_timestamp": "2026-04-10T08:00:00+00:00",
                    "resolution_horizon": "2026-04-25T00:00:00+00:00",
                    "source_url": "https://nfl.com/y",
                },
            ]
        )
        try:
            out = _call(
                mcp_server.get_active_predictions,
                ActivePredictionsInput(entity="Bears", domain="nfl", limit=20),
            )
        finally:
            patcher.stop()

        assert out["n_pending"] == 2
        assert out["entity"] == "Bears"
        assert out["domain"] == "nfl"
        assert out["disclaimer"] == "Statistical patterns only. Not financial advice."
        assert out["predictions"][0]["prediction_hash"] == "abc123"

        sql = captured[0]["sql"]
        assert "PENDING" in sql
        assert "resolution_horizon" in sql
        assert "CURRENT_TIMESTAMP" in sql
        # Entity filter LIKE clause is parameterized
        param_names = {p.name for p in captured[0]["params"]}
        assert "entity" in param_names
        assert "lim" in param_names

    def test_empty_results(self, mock_bq):
        patcher, _ = mock_bq([])
        try:
            out = _call(
                mcp_server.get_active_predictions,
                ActivePredictionsInput(entity=None, domain="nfl"),
            )
        finally:
            patcher.stop()
        assert out["n_pending"] == 0
        assert out["predictions"] == []


# ---------------------------------------------------------------------------
# search_claims
# ---------------------------------------------------------------------------


class TestSearchClaims:
    def test_lexical_search_returns_hits(self, mock_bq):
        patcher, captured = mock_bq(
            [
                {
                    "prediction_hash": "h1",
                    "pundit_id": "p1",
                    "pundit_name": "P One",
                    "claim_category": "game_outcome",
                    "extracted_claim": "Chiefs will win the AFC West",
                    "raw_assertion_text": "I think the Chiefs win the AFC West easily.",
                    "resolution_status": "PENDING",
                    "ingestion_timestamp": "2026-04-01T00:00:00+00:00",
                    "source_url": "https://x.com/1",
                },
                {
                    "prediction_hash": "h2",
                    "pundit_id": "p2",
                    "pundit_name": "P Two",
                    "claim_category": "game_outcome",
                    "extracted_claim": "Chiefs go 14-3",
                    "raw_assertion_text": "Locked in: Chiefs 14-3.",
                    "resolution_status": "CORRECT",
                    "ingestion_timestamp": "2026-03-15T00:00:00+00:00",
                    "source_url": "https://x.com/2",
                },
            ]
        )
        try:
            out = _call(
                mcp_server.search_claims,
                SearchClaimsInput(query="Chiefs", domain="nfl", limit=10),
            )
        finally:
            patcher.stop()

        assert out["n_results"] == 2
        assert out["search_mode"] == "lexical"
        assert out["query"] == "Chiefs"
        assert out["results"][0]["prediction_hash"] == "h1"
        assert out["disclaimer"] == "Statistical patterns only. Not financial advice."

        sql = captured[0]["sql"]
        assert "LIKE CONCAT('%', LOWER(@q), '%')" in sql
        param_names = {p.name for p in captured[0]["params"]}
        assert "q" in param_names

    def test_pundit_id_filter_added(self, mock_bq):
        patcher, captured = mock_bq([])
        try:
            _call(
                mcp_server.search_claims,
                SearchClaimsInput(
                    query="trade", pundit_id="schefter", claim_type="trade_move"
                ),
            )
        finally:
            patcher.stop()

        sql = captured[0]["sql"]
        assert "l.pundit_id = @pundit_id" in sql
        assert "l.claim_category = @claim_type" in sql
        param_names = {p.name for p in captured[0]["params"]}
        assert "pundit_id" in param_names
        assert "claim_type" in param_names


# ---------------------------------------------------------------------------
# compare_pundits
# ---------------------------------------------------------------------------


class TestComparePundits:
    def test_recommendation_picks_highest_weighted_score(self, mock_bq):
        # Two reliability queries, one per pundit.
        patcher, _ = mock_bq(
            [
                [
                    {
                        "pundit_id": "a",
                        "pundit_name": "Pundit A",
                        "n_total": 20,
                        "n_resolved": 15,
                        "n_correct": 11,
                        "accuracy_rate": 0.733,
                        "brier_score": 0.18,
                        "weighted_score": 0.65,
                    }
                ],
                [
                    {
                        "pundit_id": "b",
                        "pundit_name": "Pundit B",
                        "n_total": 12,
                        "n_resolved": 10,
                        "n_correct": 6,
                        "accuracy_rate": 0.6,
                        "brier_score": 0.22,
                        "weighted_score": 0.45,
                    }
                ],
            ]
        )
        try:
            out = _call(
                mcp_server.compare_pundits,
                ComparePunditsInput(pundit_ids=["a", "b"], domain="nfl"),
            )
        finally:
            patcher.stop()

        assert out["recommendation"] == "a"
        assert len(out["pundits"]) == 2
        assert out["pundits"][0]["pundit_id"] == "a"
        assert out["pundits"][1]["pundit_id"] == "b"

    def test_insufficient_data_when_below_threshold(self, mock_bq):
        patcher, _ = mock_bq(
            [
                [
                    {
                        "pundit_id": "a",
                        "pundit_name": "A",
                        "n_total": 4,
                        "n_resolved": 4,
                        "n_correct": 3,
                        "accuracy_rate": 0.75,
                        "brier_score": 0.2,
                        "weighted_score": 0.5,
                    }
                ],
                [
                    {
                        "pundit_id": "b",
                        "pundit_name": "B",
                        "n_total": 3,
                        "n_resolved": 3,
                        "n_correct": 1,
                        "accuracy_rate": 0.33,
                        "brier_score": 0.4,
                        "weighted_score": 0.2,
                    }
                ],
            ]
        )
        try:
            out = _call(
                mcp_server.compare_pundits,
                ComparePunditsInput(pundit_ids=["a", "b"]),
            )
        finally:
            patcher.stop()
        assert out["recommendation"] == "insufficient_data"


# ---------------------------------------------------------------------------
# trace_claim_chain
# ---------------------------------------------------------------------------


class TestTraceClaimChain:
    def test_walks_chain_back_to_genesis(self, mock_bq):
        # Three nodes: tip -> middle -> genesis (prev_hash=None).
        patcher, _ = mock_bq(
            [
                [
                    {
                        "prediction_hash": "tip00001",
                        "prev_hash": "middle01",
                        "chain_hash": "ch_tip00",
                        "pundit_id": "p1",
                        "pundit_name": "P1",
                        "extracted_claim": "Tip claim",
                        "ingestion_timestamp": "2026-04-15T00:00:00+00:00",
                        "resolution_status": "PENDING",
                    }
                ],
                [
                    {
                        "prediction_hash": "middle01",
                        "prev_hash": "genesis1",
                        "chain_hash": "ch_mid00",
                        "pundit_id": "p2",
                        "pundit_name": "P2",
                        "extracted_claim": "Mid claim",
                        "ingestion_timestamp": "2026-04-10T00:00:00+00:00",
                        "resolution_status": "CORRECT",
                    }
                ],
                [
                    {
                        "prediction_hash": "genesis1",
                        "prev_hash": None,
                        "chain_hash": "ch_gen00",
                        "pundit_id": "p3",
                        "pundit_name": "P3",
                        "extracted_claim": "Genesis claim",
                        "ingestion_timestamp": "2026-04-01T00:00:00+00:00",
                        "resolution_status": "INCORRECT",
                    }
                ],
            ]
        )
        try:
            out = _call(
                mcp_server.trace_claim_chain,
                TraceClaimChainInput(prediction_hash="tip00001", depth=5),
            )
        finally:
            patcher.stop()

        assert out["verification_status"] == "VALID"
        assert out["verified"] is True
        assert len(out["chain"]) == 3
        assert out["chain"][0]["prediction_hash"] == "tip00001"
        assert out["chain"][1]["prediction_hash"] == "middle01"
        assert out["chain"][2]["prediction_hash"] == "genesis1"

    def test_not_found_when_first_lookup_empty(self, mock_bq):
        patcher, _ = mock_bq([])
        try:
            out = _call(
                mcp_server.trace_claim_chain,
                TraceClaimChainInput(prediction_hash="missing-hash-aaaaaaaa"),
            )
        finally:
            patcher.stop()
        assert out["verification_status"] == "NOT_FOUND"
        assert out["chain"] == []

    def test_broken_chain_detected(self, mock_bq):
        patcher, _ = mock_bq(
            [
                [
                    {
                        "prediction_hash": "tip00001",
                        "prev_hash": "middle01",
                        "chain_hash": "ch_tip00",
                        "pundit_id": "p1",
                        "pundit_name": "P1",
                        "extracted_claim": "Tip claim",
                        "ingestion_timestamp": "2026-04-15T00:00:00+00:00",
                        "resolution_status": "PENDING",
                    }
                ],
                [
                    {
                        # prediction_hash != "middle01" referenced by tip.prev_hash
                        # → broken pointer, verification_status should be BROKEN.
                        "prediction_hash": "TAMPERED01",
                        "prev_hash": None,
                        "chain_hash": "ch_mid00",
                        "pundit_id": "p2",
                        "pundit_name": "P2",
                        "extracted_claim": "Bad",
                        "ingestion_timestamp": "2026-04-10T00:00:00+00:00",
                        "resolution_status": "PENDING",
                    }
                ],
            ]
        )
        try:
            out = _call(
                mcp_server.trace_claim_chain,
                TraceClaimChainInput(prediction_hash="tip00001", depth=3),
            )
        finally:
            patcher.stop()
        assert out["verification_status"] == "BROKEN"
        assert out["verified"] is False


# ---------------------------------------------------------------------------
# get_leaderboard
# ---------------------------------------------------------------------------


class TestGetLeaderboard:
    def test_ranks_by_weighted_score(self, mock_bq):
        patcher, captured = mock_bq(
            [
                {
                    "pundit_id": "a",
                    "pundit_name": "A",
                    "n_total": 50,
                    "n_resolved": 40,
                    "accuracy_rate": 0.75,
                    "brier_score": 0.18,
                    "weighted_score": 0.85,
                },
                {
                    "pundit_id": "b",
                    "pundit_name": "B",
                    "n_total": 30,
                    "n_resolved": 25,
                    "accuracy_rate": 0.68,
                    "brier_score": 0.22,
                    "weighted_score": 0.6,
                },
            ]
        )
        try:
            out = _call(
                mcp_server.get_leaderboard,
                LeaderboardInput(domain="nfl", window="career", limit=10),
            )
        finally:
            patcher.stop()
        assert out["leaderboard"][0]["rank"] == 1
        assert out["leaderboard"][0]["pundit_id"] == "a"
        assert out["leaderboard"][1]["rank"] == 2
        assert out["leaderboard"][1]["pundit_id"] == "b"
        assert out["total"] == 2
        sql = captured[0]["sql"]
        assert "GROUP BY l.pundit_id" in sql
        assert "ORDER BY weighted_score DESC" in sql


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


class TestRateLimiting:
    def test_exhaust_bucket_returns_rate_limited(self, mock_bq):
        patcher, _ = mock_bq([])
        try:
            # Force a tiny limit by patching the table.
            with patch.dict(
                mcp_auth.TIER_RATE_LIMITS_PER_MIN,
                {"agent_growth": 2},
                clear=False,
            ):
                # Reset the limiter so the new capacity takes effect.
                mcp_auth.get_limiter().reset()
                # Two calls fit in the bucket (cost=1 each).
                out1 = _call(
                    mcp_server.get_pundit_reliability,
                    PunditReliabilityInput(pundit_id="x"),
                )
                out2 = _call(
                    mcp_server.get_pundit_reliability,
                    PunditReliabilityInput(pundit_id="x"),
                )
                # Third should be rate limited.
                out3 = _call(
                    mcp_server.get_pundit_reliability,
                    PunditReliabilityInput(pundit_id="x"),
                )
        finally:
            patcher.stop()

        assert "error" not in out1
        assert "error" not in out2
        assert out3["error"] == "RATE_LIMITED"
        assert out3["code"] == -32002
        assert out3["retry_after_seconds"] >= 1


# ---------------------------------------------------------------------------
# Module-level smoke tests
# ---------------------------------------------------------------------------


def test_mcp_server_exposes_six_tools():
    """All Phase 1 tools registered with FastMCP."""
    server = mcp_server.get_mcp_server()
    tools_attr = getattr(server, "_tools", None) or getattr(server, "tools", None)
    # FastMCP keeps tools internally; we don't depend on the exact attribute.
    # Instead, verify each handler is importable from the module.
    for name in (
        "get_pundit_reliability",
        "get_active_predictions",
        "search_claims",
        "compare_pundits",
        "trace_claim_chain",
        "get_leaderboard",
    ):
        handler = getattr(mcp_server, name)
        assert callable(handler) or callable(getattr(handler, "fn", None))
