"""
OpenAPI response schemas for the NFL Dead Money / Pundit Prediction Ledger API.

Three named vendor payloads are surfaced through these models:

  PUNDIT INDEX       — Cryptographically-verified pundit accuracy scores with Brier
                       scoring. Endpoints: /v1/leaderboard, /v1/pundits/
  FMV TRAJECTORY     — Fair Market Value trajectory signal (improving / declining / flat)
                       showing whether a player's market compensation is diverging from
                       on-field production value. Endpoint: /v1/cap/fmv/{player_name}
  INJURY LAG         — availability_rating × games_played overlay exposing contracts
                       where dead-cap exposure has not yet repriced for injury-adjusted
                       market value. Endpoint: /v1/cap/players/{player_name}
"""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Shared primitives
# ---------------------------------------------------------------------------


class PaginationMeta(BaseModel):
    page: int = Field(..., description="Current page number (1-indexed)", example=1)
    limit: int = Field(..., description="Records per page", example=50)
    total: int = Field(..., description="Total matching records", example=312)


# ---------------------------------------------------------------------------
# VENDOR PAYLOAD 1 — PUNDIT INDEX
# Endpoints: GET /v1/leaderboard  |  GET /v1/pundits/  |  GET /v1/pundits/{id}
# ---------------------------------------------------------------------------


class PunditSummary(BaseModel):
    """
    Aggregate accuracy record for a single pundit.
    Forms the core of the **Pundit Index** vendor payload.

    Brier score (0–1, lower is better) measures probabilistic calibration.
    Weighted score adjusts for recency and claim difficulty.
    """

    pundit_id: str = Field(..., description="Unique pundit identifier", example="mcafee_pat")
    pundit_name: str = Field(..., description="Display name", example="Pat McAfee")
    sport: Optional[str] = Field("NFL", description="Sport scope", example="NFL")
    total_predictions: int = Field(..., description="All-time prediction count", example=847)
    resolved_count: int = Field(
        ..., description="Predictions with a final CORRECT/INCORRECT verdict", example=631
    )
    correct_count: int = Field(..., description="Correctly resolved predictions", example=384)
    accuracy_rate: Optional[float] = Field(
        None,
        description="correct_count / resolved_count (null if no resolved predictions)",
        example=0.608,
    )
    avg_brier_score: Optional[float] = Field(
        None,
        description=(
            "Mean Brier score across resolved predictions. "
            "0 = perfect, 1 = perfectly wrong. "
            "**Pundit Index** primary calibration metric."
        ),
        example=0.24,
    )
    avg_weighted_score: Optional[float] = Field(
        None,
        description=(
            "Recency- and difficulty-adjusted score. "
            "Used for Pundit Index leaderboard ranking."
        ),
        example=0.71,
    )


class LeaderboardEntry(PunditSummary):
    """Pundit Index leaderboard row — same fields as PunditSummary."""
    pass


class LeaderboardResponse(BaseModel):
    """Response for GET /v1/leaderboard — the **Pundit Index** vendor payload."""

    leaderboard: List[LeaderboardEntry] = Field(
        ..., description="Pundits ranked by avg_weighted_score descending"
    )
    total: int = Field(..., description="Total pundits in the database", example=42)


class PunditsListResponse(BaseModel):
    """Response for GET /v1/pundits/"""

    pundits: List[PunditSummary]
    total: int


class AccuracyByCategory(BaseModel):
    claim_category: str = Field(
        ..., description="Prediction category (e.g. injury, contract, draft_pick)", example="injury"
    )
    total: int = Field(..., description="Predictions in this category", example=120)
    resolved: int = Field(..., description="Resolved predictions", example=95)
    correct: int = Field(..., description="Correct predictions", example=58)
    accuracy_rate: Optional[float] = Field(None, example=0.611)
    avg_weighted_score: Optional[float] = Field(None, example=0.68)


class PunditDetailResponse(BaseModel):
    """Response for GET /v1/pundits/{pundit_id}"""

    pundit: PunditSummary
    accuracy_by_category: List[AccuracyByCategory]


# ---------------------------------------------------------------------------
# Prediction records
# ---------------------------------------------------------------------------


class PredictionRecord(BaseModel):
    prediction_hash: str = Field(
        ...,
        description=(
            "SHA-256 hash of the prediction content. "
            "Part of the tamper-evident append-only ledger."
        ),
        example="a3f2e1d0c9b8a7...",
    )
    pundit_id: Optional[str] = None
    pundit_name: Optional[str] = None
    ingestion_timestamp: Optional[Any] = Field(
        None, description="UTC timestamp when the prediction was ingested"
    )
    source_url: Optional[str] = Field(None, description="Source article or video URL")
    raw_assertion_text: Optional[str] = Field(
        None, description="Original verbatim quote from the source"
    )
    extracted_claim: Optional[str] = Field(
        None, description="NLP-normalised structured claim"
    )
    claim_category: Optional[str] = Field(
        None, description="Category: injury / contract / draft_pick / performance / trade"
    )
    season_year: Optional[int] = Field(None, example=2024)
    target_player_id: Optional[str] = None
    target_player_name: Optional[str] = None
    target_team: Optional[str] = Field(None, example="KAN")
    resolution_status: Optional[str] = Field(
        None,
        description="CORRECT | INCORRECT | PENDING",
        example="CORRECT",
    )
    resolved_at: Optional[Any] = None
    binary_correct: Optional[bool] = None
    brier_score: Optional[float] = Field(None, example=0.18)
    weighted_score: Optional[float] = Field(None, example=0.74)
    outcome_notes: Optional[str] = None


class PredictionsPageResponse(BaseModel):
    predictions: List[PredictionRecord]
    page: int
    page_size: int
    total: int
    pages: int


class PredictionsSearchResponse(BaseModel):
    predictions: List[PredictionRecord]
    page: int
    limit: int
    total: int
    pages: int


class RecentPredictionsResponse(BaseModel):
    predictions: List[PredictionRecord]
    count: int


# ---------------------------------------------------------------------------
# Draft endpoints
# ---------------------------------------------------------------------------


class DraftSummaryResponse(BaseModel):
    year: int
    total: int
    resolved: int
    pending: int
    predictions: List[PredictionRecord]


class PunditDraftAccuracy(BaseModel):
    pundit_id: str
    pundit_name: str
    total_predictions: int
    resolved_count: int
    correct_count: int
    accuracy_rate: Optional[float] = None
    avg_weighted_score: Optional[float] = None


class DraftResultsResponse(BaseModel):
    year: int
    total: int
    by_status: Dict[str, List[PredictionRecord]]
    pundit_accuracy: List[PunditDraftAccuracy]


# ---------------------------------------------------------------------------
# VENDOR PAYLOAD 2 — FMV TRAJECTORY
# Endpoint: GET /v1/cap/fmv/{player_name}
# ---------------------------------------------------------------------------


class FmvSeasonRecord(BaseModel):
    """
    Single-season slice of a player's Fair Market Value computation.
    Part of the **FMV Trajectory** vendor payload.
    """

    year: int = Field(..., description="NFL season year", example=2024)
    team: Optional[str] = Field(None, example="KAN")
    position: Optional[str] = Field(None, example="QB")
    cap_hit_millions: Optional[float] = Field(
        None, description="Actual cap charge (millions USD)", example=45.0
    )
    dead_cap_millions: Optional[float] = Field(
        None, description="Dead cap obligation if released (millions USD)", example=10.0
    )
    fair_market_value: Optional[float] = Field(
        None,
        description=(
            "Model-derived fair market value (millions USD). "
            "Divergence from cap_hit_millions is the FMV signal. "
            "**FMV Trajectory** core metric."
        ),
        example=48.0,
    )
    edce_risk: Optional[float] = Field(
        None,
        description=(
            "Expected Dead Cap Exposure risk score. "
            "Composite of dead money + contract tail risk."
        ),
        example=5.2,
    )
    efficiency_ratio: Optional[float] = Field(
        None,
        description="fair_market_value / cap_hit_millions — values > 1.0 indicate surplus value",
        example=1.07,
    )
    true_bust_variance: Optional[float] = Field(
        None,
        description="Variance in performance outcomes that could trigger contract bust",
        example=0.0,
    )
    ytd_performance_value: Optional[float] = Field(
        None, description="Year-to-date production value (millions USD)", example=48.0
    )
    ml_risk_score: Optional[float] = Field(
        None,
        description="XGBoost dead-cap risk probability [0, 1]. Lower = safer contract.",
        example=0.15,
    )
    availability_rating: Optional[float] = Field(
        None,
        description=(
            "games_played / max_games for the season [0, 1]. "
            "Used in **Injury Lag** payload to detect availability-repricing lag."
        ),
        example=1.0,
    )
    games_played: Optional[int] = Field(None, example=17)


class FmvTrajectoryResponse(BaseModel):
    """
    Response for GET /v1/cap/fmv/{player_name} — the **FMV Trajectory** vendor payload.

    The `trajectory` field is the primary signal for the vendor integration:
    - `improving` — FMV increased year-over-year (player value rising faster than cap hit)
    - `declining` — FMV decreased year-over-year (player value falling; contract at risk)
    - `flat`      — No meaningful change
    - `unknown`   — Insufficient history (fewer than 2 seasons)
    """

    player_name: str = Field(..., example="Patrick Mahomes")
    trajectory: Literal["improving", "declining", "flat", "unknown"] = Field(
        ...,
        description=(
            "Year-over-year FMV direction. "
            "**FMV Trajectory** vendor payload primary signal."
        ),
        example="improving",
    )
    seasons: List[FmvSeasonRecord] = Field(
        ..., description="Per-season FMV records sorted by year ascending"
    )


# ---------------------------------------------------------------------------
# VENDOR PAYLOAD 3 — INJURY LAG
# Endpoint: GET /v1/cap/players/{player_name}  (availability_rating overlay)
# ---------------------------------------------------------------------------


class CapPlayerRecord(BaseModel):
    """
    Single-season cap record for a player.
    The `availability_rating` and `ml_risk_score` fields together form the
    **Injury Lag** vendor payload — identifying players whose contract has not
    yet repriced for declining injury-adjusted market value.
    """

    player_name: Optional[str] = None
    team: Optional[str] = Field(None, example="KAN")
    year: Optional[int] = Field(None, example=2024)
    position: Optional[str] = Field(None, example="QB")
    cap_hit_millions: Optional[float] = Field(None, example=45.0)
    dead_cap_millions: Optional[float] = Field(None, example=10.0)
    signing_bonus_millions: Optional[float] = Field(None, example=20.0)
    guaranteed_money_millions: Optional[float] = Field(None, example=210.0)
    fair_market_value: Optional[float] = Field(None, example=48.0)
    ml_risk_score: Optional[float] = Field(
        None,
        description=(
            "XGBoost dead-cap risk probability [0, 1]. "
            "**Injury Lag** payload: high risk_score + low availability_rating "
            "signals a contract that has not repriced for injury exposure."
        ),
        example=0.15,
    )
    edce_risk: Optional[float] = Field(None, example=5.2)
    availability_rating: Optional[float] = Field(
        None,
        description=(
            "games_played / max_games [0, 1]. "
            "**Injury Lag** payload: values below 0.75 with high cap_hit indicate "
            "an availability-repricing lag opportunity."
        ),
        example=1.0,
    )
    games_played: Optional[int] = Field(None, example=17)


class CapPlayersResponse(BaseModel):
    """Response for GET /v1/cap/players — paginated player cap data."""

    players: List[CapPlayerRecord]
    page: int
    limit: int
    total: int


class CapPlayerProfileResponse(BaseModel):
    """
    Response for GET /v1/cap/players/{player_name} — **Injury Lag** vendor payload.

    Cross-reference `availability_rating` with `ml_risk_score` across seasons
    to detect contracts where availability decline has not yet been priced in.
    """

    player_name: str = Field(..., example="Patrick Mahomes")
    seasons: List[CapPlayerRecord] = Field(
        ..., description="All available seasons, sorted by year descending"
    )
    season_count: int = Field(..., description="Number of seasons on record", example=7)


# ---------------------------------------------------------------------------
# Teams
# ---------------------------------------------------------------------------


class TeamCapRecord(BaseModel):
    team: Optional[str] = Field(None, example="KAN")
    year: Optional[int] = Field(None, example=2024)
    total_cap: Optional[float] = Field(
        None, description="Total cap committed (millions USD)", example=230.0
    )
    cap_space: Optional[float] = Field(
        None, description="Remaining cap space (millions USD)", example=25.4
    )
    risk_cap: Optional[float] = Field(
        None, description="Dead money / at-risk cap (millions USD)", example=30.0
    )
    qb_spending: Optional[float] = None
    wr_spending: Optional[float] = None
    rb_spending: Optional[float] = None
    te_spending: Optional[float] = None
    dl_spending: Optional[float] = None
    lb_spending: Optional[float] = None
    db_spending: Optional[float] = None
    ol_spending: Optional[float] = None
    k_spending: Optional[float] = None
    p_spending: Optional[float] = None
    win_pct: Optional[float] = Field(None, example=0.824)
    win_total: Optional[float] = Field(None, example=14.0)
    conference: Optional[str] = Field(None, example="AFC")


class TeamCapResponse(BaseModel):
    """Response for GET /v1/cap/teams"""

    teams: List[TeamCapRecord]
    total: int


# ---------------------------------------------------------------------------
# Integrity
# ---------------------------------------------------------------------------


class IntegrityCheckResponse(BaseModel):
    verified: bool = Field(
        ...,
        description="True if the full prediction hash chain is intact (no tampering detected)",
        example=True,
    )
    checked: int = Field(..., description="Number of records verified", example=847)
    broken_at: Optional[str] = Field(
        None,
        description="prediction_hash of the first broken link, null if verified=True",
    )
    message: Optional[str] = None
