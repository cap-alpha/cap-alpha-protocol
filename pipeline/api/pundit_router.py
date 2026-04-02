"""
Pundit Scorecard API — Public REST Endpoints (Issue #113)

Endpoints:
  GET /v1/pundits/                          — List all tracked pundits with summary scores
  GET /v1/pundits/{pundit_id}               — Pundit detail with accuracy breakdown by category
  GET /v1/pundits/{pundit_id}/predictions   — Paginated prediction history with resolution status
  GET /v1/predictions/recent                — Latest resolved predictions across all pundits
  GET /v1/leaderboard                       — Ranked pundits by weighted score / accuracy
  GET /v1/integrity/verify                  — Hash chain integrity check (tamper detection)
"""

import logging
import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from src.cryptographic_ledger import verify_chain_integrity
from src.db_manager import DBManager
from src.resolution_engine import get_pundit_accuracy_summary

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["pundit-ledger"])

LEDGER_TABLE = "gold_layer.prediction_ledger"
RESOLUTIONS_TABLE = "gold_layer.prediction_resolutions"


def get_db() -> DBManager:
    """FastAPI dependency — yields a DBManager, closes on teardown."""
    db = DBManager()
    try:
        yield db
    finally:
        db.close()


def _full(table: str) -> str:
    project_id = os.environ.get("GCP_PROJECT_ID")
    return f"`{project_id}.{table}`"


# ---------------------------------------------------------------------------
# GET /v1/leaderboard
# ---------------------------------------------------------------------------

@router.get("/leaderboard", summary="Ranked pundits by accuracy")
def leaderboard(
    limit: int = Query(default=25, ge=1, le=100),
    db: DBManager = Depends(get_db),
) -> Dict[str, Any]:
    """
    Returns pundits ranked by weighted accuracy score (accuracy × timeliness).
    5-minute cache TTL.
    """
    try:
        df = get_pundit_accuracy_summary(db=db)
        if df.empty:
            return {"leaderboard": [], "total": 0}

        top = df.head(limit)
        return {
            "leaderboard": top.where(top.notna(), None).to_dict(orient="records"),
            "total": len(df),
        }
    except Exception as e:
        logger.error(f"Leaderboard error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch leaderboard")


# ---------------------------------------------------------------------------
# GET /v1/pundits/
# ---------------------------------------------------------------------------

@router.get("/pundits/", summary="List all tracked pundits")
def list_pundits(
    db: DBManager = Depends(get_db),
) -> Dict[str, Any]:
    """
    Returns all pundits with aggregate accuracy stats.
    """
    try:
        df = get_pundit_accuracy_summary(db=db)
        return {
            "pundits": df.where(df.notna(), None).to_dict(orient="records"),
            "total": len(df),
        }
    except Exception as e:
        logger.error(f"List pundits error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch pundits")


# ---------------------------------------------------------------------------
# GET /v1/pundits/{pundit_id}
# ---------------------------------------------------------------------------

@router.get("/pundits/{pundit_id}", summary="Pundit detail with accuracy breakdown")
def pundit_detail(
    pundit_id: str,
    db: DBManager = Depends(get_db),
) -> Dict[str, Any]:
    """
    Returns a single pundit's accuracy broken down by claim category.
    """
    try:
        project_id = os.environ.get("GCP_PROJECT_ID")
        query = f"""
            SELECT
                l.claim_category,
                COUNT(*) AS total,
                COUNTIF(r.resolution_status IN ('CORRECT', 'INCORRECT')) AS resolved,
                COUNTIF(r.resolution_status = 'CORRECT') AS correct,
                SAFE_DIVIDE(
                    COUNTIF(r.resolution_status = 'CORRECT'),
                    COUNTIF(r.resolution_status IN ('CORRECT', 'INCORRECT'))
                ) AS accuracy_rate,
                AVG(r.weighted_score) AS avg_weighted_score
            FROM {_full(LEDGER_TABLE)} l
            LEFT JOIN {_full(RESOLUTIONS_TABLE)} r ON l.prediction_hash = r.prediction_hash
            WHERE l.pundit_id = '{pundit_id}'
            GROUP BY l.claim_category
            ORDER BY total DESC
        """
        breakdown_df = db.fetch_df(query)

        summary_df = get_pundit_accuracy_summary(db=db)
        pundit_row = summary_df[summary_df["pundit_id"] == pundit_id]
        if pundit_row.empty:
            raise HTTPException(status_code=404, detail=f"Pundit '{pundit_id}' not found")

        summary = pundit_row.iloc[0].where(pundit_row.iloc[0].notna(), None).to_dict()
        breakdown = breakdown_df.where(breakdown_df.notna(), None).to_dict(orient="records")

        return {"pundit": summary, "accuracy_by_category": breakdown}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Pundit detail error for {pundit_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch pundit detail")


# ---------------------------------------------------------------------------
# GET /v1/pundits/{pundit_id}/predictions
# ---------------------------------------------------------------------------

@router.get("/pundits/{pundit_id}/predictions", summary="Pundit prediction history")
def pundit_predictions(
    pundit_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: Optional[str] = Query(default=None, description="Filter by resolution_status"),
    db: DBManager = Depends(get_db),
) -> Dict[str, Any]:
    """
    Paginated prediction history for a pundit with resolution status.
    """
    try:
        offset = (page - 1) * page_size
        status_filter = f"AND COALESCE(r.resolution_status, 'PENDING') = '{status}'" if status else ""

        project_id = os.environ.get("GCP_PROJECT_ID")
        query = f"""
            SELECT
                l.prediction_hash,
                l.ingestion_timestamp,
                l.source_url,
                l.raw_assertion_text,
                l.extracted_claim,
                l.claim_category,
                l.season_year,
                l.target_player_id,
                l.target_team,
                COALESCE(r.resolution_status, 'PENDING') AS resolution_status,
                r.resolved_at,
                r.binary_correct,
                r.brier_score,
                r.weighted_score,
                r.outcome_notes
            FROM {_full(LEDGER_TABLE)} l
            LEFT JOIN {_full(RESOLUTIONS_TABLE)} r ON l.prediction_hash = r.prediction_hash
            WHERE l.pundit_id = '{pundit_id}'
            {status_filter}
            ORDER BY l.ingestion_timestamp DESC
            LIMIT {page_size} OFFSET {offset}
        """
        df = db.fetch_df(query)

        count_query = f"""
            SELECT COUNT(*) AS total
            FROM {_full(LEDGER_TABLE)} l
            LEFT JOIN {_full(RESOLUTIONS_TABLE)} r ON l.prediction_hash = r.prediction_hash
            WHERE l.pundit_id = '{pundit_id}'
            {status_filter}
        """
        count_df = db.fetch_df(count_query)
        total = int(count_df.iloc[0]["total"]) if not count_df.empty else 0

        return {
            "pundit_id": pundit_id,
            "predictions": df.where(df.notna(), None).to_dict(orient="records"),
            "page": page,
            "page_size": page_size,
            "total": total,
            "pages": (total + page_size - 1) // page_size,
        }
    except Exception as e:
        logger.error(f"Pundit predictions error for {pundit_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch predictions")


# ---------------------------------------------------------------------------
# GET /v1/predictions/recent
# ---------------------------------------------------------------------------

@router.get("/predictions/recent", summary="Latest resolved predictions across all pundits")
def recent_predictions(
    limit: int = Query(default=20, ge=1, le=100),
    db: DBManager = Depends(get_db),
) -> Dict[str, Any]:
    """
    Returns the most recently resolved predictions across all pundits.
    1-hour cache TTL for historical data.
    """
    try:
        project_id = os.environ.get("GCP_PROJECT_ID")
        query = f"""
            SELECT
                l.prediction_hash,
                l.pundit_id,
                l.pundit_name,
                l.ingestion_timestamp,
                l.extracted_claim,
                l.claim_category,
                l.season_year,
                l.target_player_id,
                l.target_team,
                r.resolution_status,
                r.resolved_at,
                r.binary_correct,
                r.brier_score,
                r.weighted_score,
                r.outcome_notes
            FROM {_full(LEDGER_TABLE)} l
            INNER JOIN {_full(RESOLUTIONS_TABLE)} r ON l.prediction_hash = r.prediction_hash
            WHERE r.resolution_status IN ('CORRECT', 'INCORRECT')
            ORDER BY r.resolved_at DESC
            LIMIT {limit}
        """
        df = db.fetch_df(query)
        return {
            "predictions": df.where(df.notna(), None).to_dict(orient="records"),
            "count": len(df),
        }
    except Exception as e:
        logger.error(f"Recent predictions error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch recent predictions")


# ---------------------------------------------------------------------------
# GET /v1/integrity/verify
# ---------------------------------------------------------------------------

@router.get("/integrity/verify", summary="Hash chain integrity check")
def integrity_check(
    db: DBManager = Depends(get_db),
) -> Dict[str, Any]:
    """
    Walks the full prediction ledger and verifies the hash chain is intact.
    Returns verified=True if no records have been tampered with.
    """
    try:
        result = verify_chain_integrity(db=db)
        return result
    except Exception as e:
        logger.error(f"Integrity check error: {e}")
        raise HTTPException(status_code=500, detail="Failed to run integrity check")
