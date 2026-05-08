"""
Pydantic Input/Output models for the MCP Phase 1 tool suite (issue #814).

Each tool has:
  - {Name}Input  — JSON Schema for arguments
  - {Name}Output — structured response

All outputs include a `disclaimer` field with the required compliance string.
"""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

DISCLAIMER = "Statistical patterns only. Not financial advice."

# Phase 1 windows / claim types — kept loose so we don't fight the existing
# claim_category vocabulary in the ledger.  `any` means no filter.
Window = Literal["30d", "90d", "season", "last_season", "career", "any"]
Domain = Literal["nfl", "nba", "mlb", "any"]


# ---------------------------------------------------------------------------
# get_pundit_reliability
# ---------------------------------------------------------------------------


class PunditReliabilityInput(BaseModel):
    pundit_id: str = Field(
        ..., description="Canonical pundit_id, or pundit_name substring"
    )
    domain: Domain = Field("nfl", description="Sport domain")
    claim_type: Optional[str] = Field(
        None, description="claim_category filter (e.g. 'game_outcome'); omit for all"
    )
    window: Window = Field(
        "last_season", description="Time window for the rolling stats"
    )


class PunditReliabilityOutput(BaseModel):
    pundit_id: Optional[str] = None
    pundit_name: Optional[str] = None
    domain: str
    claim_type: Optional[str] = None
    window: str
    n_total: int = 0
    n_resolved: int = 0
    n_correct: int = 0
    accuracy_rate: Optional[float] = None
    brier_score: Optional[float] = None
    weighted_score: Optional[float] = None
    confidence_interval: Optional[Dict[str, float]] = None
    disclaimer: str = DISCLAIMER


# ---------------------------------------------------------------------------
# get_active_predictions
# ---------------------------------------------------------------------------


class ActivePrediction(BaseModel):
    prediction_hash: str
    pundit_id: Optional[str] = None
    pundit_name: Optional[str] = None
    claim_category: Optional[str] = None
    extracted_claim: Optional[str] = None
    target_player_name: Optional[str] = None
    target_team: Optional[str] = None
    ingestion_timestamp: Optional[str] = None
    resolution_horizon: Optional[str] = None
    source_url: Optional[str] = None


class ActivePredictionsInput(BaseModel):
    entity: Optional[str] = Field(
        None, description="player_name, team_abbr, or pundit_id substring"
    )
    domain: Domain = Field("nfl", description="Sport domain")
    limit: int = Field(50, ge=1, le=200)


class ActivePredictionsOutput(BaseModel):
    entity: Optional[str] = None
    domain: str
    n_pending: int = 0
    predictions: List[ActivePrediction] = []
    disclaimer: str = DISCLAIMER


# ---------------------------------------------------------------------------
# search_claims
# ---------------------------------------------------------------------------


class ClaimSearchHit(BaseModel):
    prediction_hash: str
    pundit_id: Optional[str] = None
    pundit_name: Optional[str] = None
    claim_category: Optional[str] = None
    extracted_claim: Optional[str] = None
    raw_assertion_text: Optional[str] = None
    resolution_status: Optional[str] = None
    ingestion_timestamp: Optional[str] = None
    source_url: Optional[str] = None


class SearchClaimsInput(BaseModel):
    query: str = Field(..., min_length=2, max_length=500)
    domain: Domain = Field("nfl")
    claim_type: Optional[str] = Field(
        None, description="claim_category filter (e.g. 'game_outcome')"
    )
    pundit_id: Optional[str] = None
    limit: int = Field(25, ge=1, le=100)


class SearchClaimsOutput(BaseModel):
    query: str
    n_results: int = 0
    results: List[ClaimSearchHit] = []
    search_mode: str = "lexical"
    disclaimer: str = DISCLAIMER


# ---------------------------------------------------------------------------
# compare_pundits
# ---------------------------------------------------------------------------


class PunditStatBlock(BaseModel):
    pundit_id: Optional[str] = None
    pundit_name: Optional[str] = None
    n_total: int = 0
    n_resolved: int = 0
    n_correct: int = 0
    accuracy_rate: Optional[float] = None
    brier_score: Optional[float] = None
    weighted_score: Optional[float] = None


class ComparePunditsInput(BaseModel):
    pundit_ids: List[str] = Field(..., min_length=2, max_length=10)
    domain: Domain = Field("nfl")
    claim_type: Optional[str] = None


class ComparePunditsOutput(BaseModel):
    domain: str
    claim_type: Optional[str] = None
    pundits: List[PunditStatBlock] = []
    recommendation: Optional[str] = Field(
        None,
        description="pundit_id of strongest by weighted_score, or 'insufficient_data'",
    )
    disclaimer: str = DISCLAIMER


# ---------------------------------------------------------------------------
# trace_claim_chain
# ---------------------------------------------------------------------------


class ClaimChainNode(BaseModel):
    prediction_hash: str
    prev_hash: Optional[str] = None
    chain_hash: Optional[str] = None
    pundit_id: Optional[str] = None
    pundit_name: Optional[str] = None
    extracted_claim: Optional[str] = None
    ingestion_timestamp: Optional[str] = None
    resolution_status: Optional[str] = None


class TraceClaimChainInput(BaseModel):
    prediction_hash: str = Field(..., min_length=8, max_length=128)
    depth: int = Field(5, ge=1, le=50, description="How many predecessors to walk back")


class TraceClaimChainOutput(BaseModel):
    prediction_hash: str
    chain: List[ClaimChainNode] = []
    verified: Optional[bool] = None
    verification_status: str = "UNVERIFIED"
    disclaimer: str = DISCLAIMER


# ---------------------------------------------------------------------------
# get_leaderboard
# ---------------------------------------------------------------------------


class LeaderboardEntry(BaseModel):
    rank: int
    pundit_id: Optional[str] = None
    pundit_name: Optional[str] = None
    n_resolved: int = 0
    accuracy_rate: Optional[float] = None
    brier_score: Optional[float] = None
    weighted_score: Optional[float] = None
    composite_score: Optional[float] = None


class LeaderboardInput(BaseModel):
    domain: Domain = Field("nfl")
    claim_type: Optional[str] = None
    window: Window = Field("last_season")
    limit: int = Field(25, ge=1, le=100)


class LeaderboardOutput(BaseModel):
    domain: str
    claim_type: Optional[str] = None
    window: str
    leaderboard: List[LeaderboardEntry] = []
    total: int = 0
    disclaimer: str = DISCLAIMER


# ---------------------------------------------------------------------------
# Common error envelope (returned as an MCP "result" so we don't break the
# JSON-RPC channel; clients should branch on the presence of "error" key).
# ---------------------------------------------------------------------------


def upgrade_required_error(
    tool: str,
    user_tier: str,
    minimum_tier: str = "agent_growth",
) -> Dict[str, Any]:
    return {
        "error": "UPGRADE_REQUIRED",
        "code": -32001,
        "tool": tool,
        "user_tier": user_tier,
        "minimum_tier": minimum_tier,
        "upgrade_url": "https://cap-alpha.co/pricing",
        "disclaimer": DISCLAIMER,
    }


def rate_limited_error(
    tool: str,
    user_tier: str,
    retry_after_seconds: int,
) -> Dict[str, Any]:
    return {
        "error": "RATE_LIMITED",
        "code": -32002,
        "tool": tool,
        "user_tier": user_tier,
        "retry_after_seconds": retry_after_seconds,
        "disclaimer": DISCLAIMER,
    }
