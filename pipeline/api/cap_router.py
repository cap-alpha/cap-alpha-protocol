"""
B2B Cap Intelligence API — /v1/cap/ endpoints (SP30-1 / GH-#108)

All endpoints require a valid B2B API key in the X-API-Key header.
Rate limit: B2B_RATE_LIMIT_RPH env var (default 1000 requests/hour per key).

Endpoints:
  GET /v1/cap/players             — Paginated list of players with cap & FMV data
  GET /v1/cap/players/{name}      — Single player cap profile (all contract columns)
  GET /v1/cap/teams               — Per-team cap summary (total, dead cap, positional)
  GET /v1/cap/fmv/{name}          — Fair Market Value trajectory for a player (all years)

Data sources: fact_player_efficiency, team_finance_summary (pre-computed Gold layer).
"""

import logging
import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from google.cloud.bigquery import QueryJobConfig, ScalarQueryParameter

from api.api_key_auth import require_api_key
from api.schemas import (
    CapPlayerProfileResponse,
    CapPlayersResponse,
    FmvTrajectoryResponse,
    TeamCapResponse,
)
from src.db_manager import DBManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/cap", tags=["b2b-cap-intelligence"])

FACT_TABLE = "gold_layer.fact_player_efficiency"
TEAM_SUMMARY_TABLE = "gold_layer.team_finance_summary"


def get_db() -> DBManager:
    db = DBManager()
    try:
        yield db
    finally:
        db.close()


def _full(table: str) -> str:
    project_id = os.environ.get("GCP_PROJECT_ID")
    return f"`{project_id}.{table}`"


def _pq(db: DBManager, sql: str, params):
    """Execute a parameterized BigQuery query."""
    job_config = QueryJobConfig(query_parameters=params)
    job = db.client.query(sql, job_config=job_config)
    return job.to_dataframe()


# ---------------------------------------------------------------------------
# GET /v1/cap/players
# ---------------------------------------------------------------------------


@router.get(
    "/players",
    summary="Paginated list of players with cap and FMV data",
    response_model=CapPlayersResponse,
    response_model_exclude_none=True,
)
def list_players(
    year: Optional[int] = Query(default=None, description="Filter by season year"),
    position: Optional[str] = Query(default=None, description="Filter by position (e.g. QB)"),
    team: Optional[str] = Query(default=None, description="Filter by team abbreviation"),
    limit: int = Query(default=50, ge=1, le=500),
    page: int = Query(default=1, ge=1),
    db: DBManager = Depends(get_db),
    _auth: dict = Depends(require_api_key),
) -> Dict[str, Any]:
    """
    Returns paginated player cap data from the Gold layer.
    Sorted by cap_hit_millions descending (highest earners first).
    """
    try:
        offset = (page - 1) * limit
        where_clauses = ["1=1"]
        params = [
            ScalarQueryParameter("lim", "INT64", limit),
            ScalarQueryParameter("off", "INT64", offset),
        ]

        if year is not None:
            where_clauses.append("year = @year")
            params.append(ScalarQueryParameter("year", "INT64", year))
        if position:
            where_clauses.append("UPPER(position) = UPPER(@position)")
            params.append(ScalarQueryParameter("position", "STRING", position))
        if team:
            where_clauses.append("UPPER(team) = UPPER(@team)")
            params.append(ScalarQueryParameter("team", "STRING", team))

        where_sql = " AND ".join(where_clauses)

        query = f"""
            SELECT
                player_name, team, year, position,
                cap_hit_millions, dead_cap_millions,
                signing_bonus_millions, guaranteed_money_millions,
                fair_market_value, ml_risk_score,
                edce_risk, availability_rating, games_played
            FROM {_full(FACT_TABLE)}
            WHERE {where_sql}
            ORDER BY cap_hit_millions DESC NULLS LAST
            LIMIT @lim OFFSET @off
        """
        df = _pq(db, query, params)

        count_query = f"""
            SELECT COUNT(*) AS total FROM {_full(FACT_TABLE)} WHERE {where_sql}
        """
        count_df = _pq(db, count_query, params)
        total = int(count_df.iloc[0]["total"]) if not count_df.empty else 0

        return {
            "players": df.where(df.notna(), None).to_dict(orient="records"),
            "page": page,
            "limit": limit,
            "total": total,
        }
    except Exception as e:
        logger.error(f"Cap players list error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch cap players")


# ---------------------------------------------------------------------------
# GET /v1/cap/players/{player_name}
# ---------------------------------------------------------------------------


@router.get(
    "/players/{player_name}",
    summary="Single player cap profile — Injury Lag vendor payload",
    response_model=CapPlayerProfileResponse,
    response_model_exclude_none=True,
)
def player_cap_profile(
    player_name: str,
    db: DBManager = Depends(get_db),
    _auth: dict = Depends(require_api_key),
) -> Dict[str, Any]:
    """
    Returns the full cap profile for a player — all available years and all
    financial columns from fact_player_efficiency.
    """
    try:
        query = f"""
            SELECT *
            FROM {_full(FACT_TABLE)}
            WHERE LOWER(player_name) = LOWER(@player_name)
            ORDER BY year DESC
        """
        params = [ScalarQueryParameter("player_name", "STRING", player_name)]
        df = _pq(db, query, params)

        if df.empty:
            raise HTTPException(
                status_code=404,
                detail=f"Player '{player_name}' not found in cap database",
            )

        return {
            "player_name": player_name,
            "seasons": df.where(df.notna(), None).to_dict(orient="records"),
            "season_count": len(df),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Player cap profile error for '{player_name}': {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch player cap profile")


# ---------------------------------------------------------------------------
# GET /v1/cap/teams
# ---------------------------------------------------------------------------


@router.get(
    "/teams",
    summary="Per-team cap summary",
    response_model=TeamCapResponse,
    response_model_exclude_none=True,
)
def team_cap_summary(
    year: Optional[int] = Query(default=None, description="Filter by season year"),
    conference: Optional[str] = Query(default=None, description="'AFC' or 'NFC'"),
    db: DBManager = Depends(get_db),
    _auth: dict = Depends(require_api_key),
) -> Dict[str, Any]:
    """
    Returns pre-computed per-team cap aggregations from team_finance_summary.
    Includes total cap committed, positional spending breakdowns, cap space,
    risk cap (dead money), win totals, and conference.
    Sorted by cap_space descending (most room first).
    """
    try:
        where_clauses = ["1=1"]
        params = []

        if year is not None:
            where_clauses.append("year = @year")
            params.append(ScalarQueryParameter("year", "INT64", year))
        if conference:
            where_clauses.append("UPPER(conference) = UPPER(@conference)")
            params.append(ScalarQueryParameter("conference", "STRING", conference))

        where_sql = " AND ".join(where_clauses)
        query = f"""
            SELECT *
            FROM {_full(TEAM_SUMMARY_TABLE)}
            WHERE {where_sql}
            ORDER BY cap_space DESC
        """
        df = _pq(db, query, params)

        return {
            "teams": df.where(df.notna(), None).to_dict(orient="records"),
            "total": len(df),
        }
    except Exception as e:
        logger.error(f"Team cap summary error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch team cap summary")


# ---------------------------------------------------------------------------
# GET /v1/cap/fmv/{player_name}
# ---------------------------------------------------------------------------


@router.get(
    "/fmv/{player_name}",
    summary="Fair Market Value trajectory — FMV Trajectory vendor payload",
    response_model=FmvTrajectoryResponse,
    response_model_exclude_none=True,
)
def player_fmv_trajectory(
    player_name: str,
    db: DBManager = Depends(get_db),
    _auth: dict = Depends(require_api_key),
) -> Dict[str, Any]:
    """
    Returns the year-over-year Fair Market Value (FMV) trajectory for a player.
    Includes cap hit, FMV score, EDCE risk, efficiency ratio, and ML risk score.

    The 'Pundit Index' vendor payload surfaces this endpoint to identify players
    whose market compensation is diverging from on-field production value.
    """
    try:
        query = f"""
            SELECT
                year,
                team,
                position,
                cap_hit_millions,
                dead_cap_millions,
                fair_market_value,
                edce_risk,
                efficiency_ratio,
                true_bust_variance,
                ytd_performance_value,
                ml_risk_score,
                availability_rating,
                games_played
            FROM {_full(FACT_TABLE)}
            WHERE LOWER(player_name) = LOWER(@player_name)
            ORDER BY year ASC
        """
        params = [ScalarQueryParameter("player_name", "STRING", player_name)]
        df = _pq(db, query, params)

        if df.empty:
            raise HTTPException(
                status_code=404,
                detail=f"Player '{player_name}' not found in FMV database",
            )

        # Compute trajectory direction: positive = improving efficiency
        trajectory = "unknown"
        if len(df) >= 2 and "fair_market_value" in df.columns:
            fmv_series = df["fair_market_value"].dropna()
            if len(fmv_series) >= 2:
                delta = float(fmv_series.iloc[-1]) - float(fmv_series.iloc[-2])
                trajectory = "improving" if delta > 0 else "declining" if delta < 0 else "flat"

        return {
            "player_name": player_name,
            "trajectory": trajectory,
            "seasons": df.where(df.notna(), None).to_dict(orient="records"),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"FMV trajectory error for '{player_name}': {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch FMV trajectory")
