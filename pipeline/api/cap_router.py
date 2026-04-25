"""
Cap Intelligence API — B2B REST Endpoints (SP30-1, Issue #108)

All routes under /v1/cap/ require a valid B2B API key passed as the
`X-API-Key` request header.  Keys are stored as SHA-256 hashes in
gold_layer.api_keys; the raw key is never persisted.

Endpoints:
  GET /v1/cap/players           — paginated player cap roster (all teams)
  GET /v1/cap/players/{name}    — single player cap detail
  GET /v1/cap/teams             — team cap summary (all 32 teams)
  GET /v1/cap/teams/{team}      — single team cap summary + roster
"""

import hashlib
import logging
import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from src.db_manager import DBManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/cap", tags=["cap-intelligence"])

API_KEYS_TABLE = "gold_layer.api_keys"
PLAYER_RISK_TABLE = "gold_layer.player_risk_tiers"
TEAM_CAP_TABLE = "gold_layer.team_cap_summary"


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


def get_db() -> DBManager:
    db = DBManager()
    try:
        yield db
    finally:
        db.close()


def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


def _full(table: str) -> str:
    project_id = os.environ.get("GCP_PROJECT_ID")
    return f"`{project_id}.{table}`"


def require_api_key(
    x_api_key: str = Header(
        ...,
        alias="X-API-Key",
        description="B2B API key issued by Cap Alpha Protocol",
    ),
    db: DBManager = Depends(get_db),
) -> Dict[str, Any]:
    """
    FastAPI dependency that validates the X-API-Key header.

    Hashes the incoming key and looks it up in gold_layer.api_keys.
    Returns the key metadata dict on success; raises 401/403 on failure.
    """
    if not x_api_key:
        raise HTTPException(status_code=401, detail="X-API-Key header is required")

    key_hash = _hash_key(x_api_key)

    try:
        query = f"""
            SELECT owner, tier, is_active, daily_limit
            FROM {_full(API_KEYS_TABLE)}
            WHERE key_hash = '{key_hash}'
            LIMIT 1
        """
        df = db.fetch_df(query)
    except Exception as exc:
        logger.error(f"API key lookup failed: {exc}")
        raise HTTPException(status_code=500, detail="Key validation service unavailable")

    if df.empty:
        raise HTTPException(status_code=401, detail="Invalid API key")

    row = df.iloc[0]
    if not row.get("is_active", False):
        raise HTTPException(status_code=403, detail="API key has been revoked")

    return {
        "owner": row["owner"],
        "tier": row["tier"],
        "daily_limit": int(row["daily_limit"]),
    }


# ---------------------------------------------------------------------------
# GET /v1/cap/players
# ---------------------------------------------------------------------------


@router.get("/players", summary="Paginated cap roster across all NFL teams")
def list_players(
    team: Optional[str] = Query(default=None, description="Filter by team abbreviation"),
    position: Optional[str] = Query(default=None, description="Filter by position"),
    risk_tier: Optional[str] = Query(
        default=None,
        description="Filter by risk tier: SAFE | MODERATE | HIGH",
    ),
    page_size: int = Query(default=25, ge=1, le=200),
    before: Optional[str] = Query(
        default=None,
        description="Keyset cursor: player_name of the last row seen",
    ),
    db: DBManager = Depends(get_db),
    _key: Dict = Depends(require_api_key),
) -> Dict[str, Any]:
    """
    Returns the pre-computed player_risk_tiers Gold table, filtered and paginated.
    Keyset pagination on player_name (alphabetical).
    """
    try:
        filters = ["cap_hit_millions IS NOT NULL"]
        if team:
            filters.append(f"team = '{team}'")
        if position:
            filters.append(f"position = '{position}'")
        if risk_tier:
            filters.append(f"risk_tier = '{risk_tier.upper()}'")
        if before:
            filters.append(f"player_name > '{before}'")

        where = "WHERE " + " AND ".join(filters)

        query = f"""
            SELECT
                player_name, team, position, year, age, games_played,
                cap_hit_millions, dead_cap_millions, risk_score,
                fair_market_value, edce_risk, risk_tier, computed_at
            FROM {_full(PLAYER_RISK_TABLE)}
            {where}
            ORDER BY player_name ASC
            LIMIT {page_size + 1}
        """
        df = db.fetch_df(query)

        has_more = len(df) > page_size
        rows = df.head(page_size)
        next_cursor = None
        if has_more and not rows.empty:
            next_cursor = str(rows.iloc[-1]["player_name"])

        return {
            "players": rows.where(rows.notna(), None).to_dict(orient="records"),
            "page_size": page_size,
            "has_more": has_more,
            "next_cursor": next_cursor,
        }
    except Exception as exc:
        logger.error(f"List players error: {exc}")
        raise HTTPException(status_code=500, detail="Failed to fetch player data")


# ---------------------------------------------------------------------------
# GET /v1/cap/players/{player_name}
# ---------------------------------------------------------------------------


@router.get("/players/{player_name}", summary="Single player cap detail")
def get_player(
    player_name: str,
    db: DBManager = Depends(get_db),
    _key: Dict = Depends(require_api_key),
) -> Dict[str, Any]:
    """Returns cap and risk details for a single player."""
    try:
        query = f"""
            SELECT
                player_name, team, position, year, age, games_played,
                cap_hit_millions, dead_cap_millions, risk_score,
                fair_market_value, edce_risk, risk_tier, computed_at
            FROM {_full(PLAYER_RISK_TABLE)}
            WHERE player_name = '{player_name}'
            ORDER BY year DESC
            LIMIT 1
        """
        df = db.fetch_df(query)

        if df.empty:
            raise HTTPException(
                status_code=404,
                detail=f"Player '{player_name}' not found in cap data",
            )

        row = df.iloc[0].where(df.iloc[0].notna(), None).to_dict()
        return {"player": row}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Get player error for {player_name}: {exc}")
        raise HTTPException(status_code=500, detail="Failed to fetch player data")


# ---------------------------------------------------------------------------
# GET /v1/cap/teams
# ---------------------------------------------------------------------------


@router.get("/teams", summary="Team cap summaries — all 32 NFL teams")
def list_teams(
    db: DBManager = Depends(get_db),
    _key: Dict = Depends(require_api_key),
) -> Dict[str, Any]:
    """Returns the pre-computed team_cap_summary Gold table."""
    try:
        query = f"""
            SELECT
                team, player_count, total_cap, risk_cap,
                avg_age, avg_risk_score, total_dead_cap,
                total_surplus_value, computed_at
            FROM {_full(TEAM_CAP_TABLE)}
            ORDER BY total_cap DESC
        """
        df = db.fetch_df(query)
        return {
            "teams": df.where(df.notna(), None).to_dict(orient="records"),
            "count": len(df),
        }
    except Exception as exc:
        logger.error(f"List teams error: {exc}")
        raise HTTPException(status_code=500, detail="Failed to fetch team data")


# ---------------------------------------------------------------------------
# GET /v1/cap/teams/{team}
# ---------------------------------------------------------------------------


@router.get("/teams/{team}", summary="Single team cap summary + roster")
def get_team(
    team: str,
    db: DBManager = Depends(get_db),
    _key: Dict = Depends(require_api_key),
) -> Dict[str, Any]:
    """Returns team-level cap summary plus the full player roster for that team."""
    try:
        # Team summary
        summary_query = f"""
            SELECT
                team, player_count, total_cap, risk_cap,
                avg_age, avg_risk_score, total_dead_cap,
                total_surplus_value, computed_at
            FROM {_full(TEAM_CAP_TABLE)}
            WHERE team = '{team}'
            LIMIT 1
        """
        summary_df = db.fetch_df(summary_query)

        if summary_df.empty:
            raise HTTPException(status_code=404, detail=f"Team '{team}' not found")

        # Roster
        roster_query = f"""
            SELECT
                player_name, position, year, age, cap_hit_millions,
                dead_cap_millions, risk_score, fair_market_value, risk_tier
            FROM {_full(PLAYER_RISK_TABLE)}
            WHERE team = '{team}'
            ORDER BY cap_hit_millions DESC
        """
        roster_df = db.fetch_df(roster_query)

        summary = summary_df.iloc[0].where(summary_df.iloc[0].notna(), None).to_dict()
        roster = roster_df.where(roster_df.notna(), None).to_dict(orient="records")

        return {"team": summary, "roster": roster}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Get team error for {team}: {exc}")
        raise HTTPException(status_code=500, detail="Failed to fetch team data")
