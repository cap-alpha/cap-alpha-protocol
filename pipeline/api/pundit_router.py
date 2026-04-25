"""
Pundit Scorecard API — Public REST Endpoints (Issue #113, #198, #201)

Endpoints:
  GET /v1/pundits/                          — List all tracked pundits with summary scores
  GET /v1/pundits/{pundit_id}               — Pundit detail with accuracy breakdown by category
  GET /v1/pundits/{pundit_id}/predictions   — Paginated prediction history with resolution status
  GET /v1/predictions/                      — Filterable prediction search with parameterized queries
  GET /v1/predictions/recent                — Latest resolved predictions across all pundits
  GET /v1/draft/{year}                      — Draft prediction summary for a given year
  GET /v1/draft/{year}/results              — Draft resolution scoreboard for a given year
  GET /v1/leaderboard                       — Ranked pundits by weighted score / accuracy
  GET /v1/integrity/verify                  — Hash chain integrity check (tamper detection)
"""

import logging
import math
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from google.cloud.bigquery import DatasetReference, QueryJobConfig, ScalarQueryParameter

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


def _parameterized_query(db: DBManager, sql: str, params: List[ScalarQueryParameter]):
    """Execute a parameterized BigQuery query and return a DataFrame."""
    dataset_ref = DatasetReference(db.project_id, db.dataset_id)
    job_config = QueryJobConfig(
        query_parameters=params,
        default_dataset=dataset_ref,
    )
    job = db.client.query(sql, job_config=job_config)
    return job.to_dataframe()


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
            LEFT JOIN {_full(RESOLUTIONS_TABLE)} r
                ON l.prediction_hash = r.prediction_hash
            WHERE l.pundit_id = @pundit_id
            GROUP BY l.claim_category
            ORDER BY total DESC
        """
        params = [ScalarQueryParameter("pundit_id", "STRING", pundit_id)]
        breakdown_df = _parameterized_query(db, query, params)

        summary_df = get_pundit_accuracy_summary(db=db)
        pundit_row = summary_df[summary_df["pundit_id"] == pundit_id]
        if pundit_row.empty:
            raise HTTPException(
                status_code=404, detail=f"Pundit '{pundit_id}' not found"
            )

        summary = pundit_row.iloc[0].where(pundit_row.iloc[0].notna(), None).to_dict()
        breakdown = breakdown_df.where(breakdown_df.notna(), None).to_dict(
            orient="records"
        )

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
    status: Optional[str] = Query(
        default=None, description="Filter by resolution_status"
    ),
    db: DBManager = Depends(get_db),
) -> Dict[str, Any]:
    """
    Paginated prediction history for a pundit with resolution status.
    """
    try:
        offset = (page - 1) * page_size
        status_clause = ""
        params: List[ScalarQueryParameter] = [
            ScalarQueryParameter("pundit_id", "STRING", pundit_id),
            ScalarQueryParameter("lim", "INT64", page_size),
            ScalarQueryParameter("off", "INT64", offset),
        ]
        if status:
            status_clause = "AND COALESCE(r.resolution_status, 'PENDING') = @status"
            params.append(ScalarQueryParameter("status", "STRING", status))

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
            LEFT JOIN {_full(RESOLUTIONS_TABLE)} r
                ON l.prediction_hash = r.prediction_hash
            WHERE l.pundit_id = @pundit_id
            {status_clause}
            ORDER BY l.ingestion_timestamp DESC
            LIMIT @lim OFFSET @off
        """
        df = _parameterized_query(db, query, params)

        count_query = f"""
            SELECT COUNT(*) AS total
            FROM {_full(LEDGER_TABLE)} l
            LEFT JOIN {_full(RESOLUTIONS_TABLE)} r
                ON l.prediction_hash = r.prediction_hash
            WHERE l.pundit_id = @pundit_id
            {status_clause}
        """
        count_df = _parameterized_query(db, count_query, params)
        total = int(count_df.iloc[0]["total"]) if not count_df.empty else 0

        return {
            "pundit_id": pundit_id,
            "predictions": df.where(df.notna(), None).to_dict(orient="records"),
            "page": page,
            "page_size": page_size,
            "total": total,
            "pages": max(1, math.ceil(total / page_size)),
        }
    except Exception as e:
        logger.error(f"Pundit predictions error for {pundit_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch predictions")


# ---------------------------------------------------------------------------
# GET /v1/predictions/recent
# ---------------------------------------------------------------------------


@router.get(
    "/predictions/recent", summary="Latest resolved predictions across all pundits"
)
def recent_predictions(
    limit: int = Query(default=20, ge=1, le=100),
    db: DBManager = Depends(get_db),
) -> Dict[str, Any]:
    """
    Returns the most recently resolved predictions across all pundits.
    """
    try:
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
            INNER JOIN {_full(RESOLUTIONS_TABLE)} r
                ON l.prediction_hash = r.prediction_hash
            WHERE r.resolution_status IN ('CORRECT', 'INCORRECT')
            ORDER BY r.resolved_at DESC
            LIMIT @lim
        """
        params = [ScalarQueryParameter("lim", "INT64", limit)]
        df = _parameterized_query(db, query, params)
        return {
            "predictions": df.where(df.notna(), None).to_dict(orient="records"),
            "count": len(df),
        }
    except Exception as e:
        logger.error(f"Recent predictions error: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to fetch recent predictions"
        )


# ---------------------------------------------------------------------------
# GET /v1/predictions/  (filterable search with parameterized queries)
# ---------------------------------------------------------------------------


@router.get("/predictions/", summary="Search predictions with filters")
def search_predictions(
    category: Optional[str] = Query(default=None, description="claim_category filter"),
    status: Optional[str] = Query(default=None, description="resolution_status filter"),
    player: Optional[str] = Query(
        default=None, description="target_player_name substring match"
    ),
    pundit_name: Optional[str] = Query(
        default=None, description="pundit_name substring match"
    ),
    limit: int = Query(default=50, ge=1, le=200),
    page: int = Query(default=1, ge=1),
    db: DBManager = Depends(get_db),
) -> Dict[str, Any]:
    """
    Filterable prediction search with parameterized BigQuery queries.
    Joins prediction_ledger LEFT JOIN prediction_resolutions.
    """
    try:
        offset = (page - 1) * limit
        where_clauses: List[str] = ["1=1"]
        params: List[ScalarQueryParameter] = [
            ScalarQueryParameter("lim", "INT64", limit),
            ScalarQueryParameter("off", "INT64", offset),
        ]

        if category:
            where_clauses.append("l.claim_category = @category")
            params.append(ScalarQueryParameter("category", "STRING", category))
        if status:
            where_clauses.append("COALESCE(r.resolution_status, 'PENDING') = @status")
            params.append(ScalarQueryParameter("status", "STRING", status))
        if player:
            where_clauses.append(
                "LOWER(COALESCE(l.target_player_name, '')) LIKE "
                "CONCAT('%', LOWER(@player), '%')"
            )
            params.append(ScalarQueryParameter("player", "STRING", player))
        if pundit_name:
            where_clauses.append(
                "LOWER(l.pundit_name) LIKE CONCAT('%', LOWER(@pundit_name), '%')"
            )
            params.append(ScalarQueryParameter("pundit_name", "STRING", pundit_name))

        where_sql = " AND ".join(where_clauses)

        query = f"""
            SELECT
                l.prediction_hash,
                l.pundit_id,
                l.pundit_name,
                l.ingestion_timestamp,
                l.source_url,
                l.raw_assertion_text,
                l.extracted_claim,
                l.claim_category,
                l.season_year,
                l.target_player_id,
                l.target_player_name,
                l.target_team,
                COALESCE(r.resolution_status, 'PENDING') AS resolution_status,
                r.resolved_at,
                r.binary_correct,
                r.brier_score,
                r.weighted_score,
                r.outcome_notes
            FROM {_full(LEDGER_TABLE)} l
            LEFT JOIN {_full(RESOLUTIONS_TABLE)} r
                ON l.prediction_hash = r.prediction_hash
            WHERE {where_sql}
            ORDER BY l.ingestion_timestamp DESC
            LIMIT @lim OFFSET @off
        """
        df = _parameterized_query(db, query, params)

        count_query = f"""
            SELECT COUNT(*) AS total
            FROM {_full(LEDGER_TABLE)} l
            LEFT JOIN {_full(RESOLUTIONS_TABLE)} r
                ON l.prediction_hash = r.prediction_hash
            WHERE {where_sql}
        """
        count_df = _parameterized_query(db, count_query, params)
        total = int(count_df.iloc[0]["total"]) if not count_df.empty else 0

        return {
            "predictions": df.where(df.notna(), None).to_dict(orient="records"),
            "page": page,
            "limit": limit,
            "total": total,
            "pages": max(1, math.ceil(total / limit)),
        }
    except Exception as e:
        logger.error(f"Search predictions error: {e}")
        raise HTTPException(status_code=500, detail="Failed to search predictions")


# ---------------------------------------------------------------------------
# GET /v1/draft/{year}  — Draft prediction summary
# ---------------------------------------------------------------------------


@router.get("/draft/{year}", summary="Draft prediction summary for a year")
def draft_summary(
    year: int,
    db: DBManager = Depends(get_db),
) -> Dict[str, Any]:
    """
    Returns a summary of draft predictions for a given season year.
    Filters by claim_category='draft_pick' and the specified season_year.
    """
    try:
        query = f"""
            SELECT
                l.prediction_hash,
                l.pundit_id,
                l.pundit_name,
                l.ingestion_timestamp,
                l.source_url,
                l.raw_assertion_text,
                l.extracted_claim,
                l.season_year,
                l.target_player_name,
                l.target_team,
                COALESCE(r.resolution_status, 'PENDING') AS resolution_status,
                r.resolved_at,
                r.binary_correct,
                r.weighted_score,
                r.outcome_notes
            FROM {_full(LEDGER_TABLE)} l
            LEFT JOIN {_full(RESOLUTIONS_TABLE)} r
                ON l.prediction_hash = r.prediction_hash
            WHERE l.claim_category = 'draft_pick'
              AND l.season_year = @year
            ORDER BY l.ingestion_timestamp DESC
        """
        params = [ScalarQueryParameter("year", "INT64", year)]
        df = _parameterized_query(db, query, params)

        resolved = 0
        pending = 0
        if not df.empty:
            resolved = int(df["resolution_status"].isin(["CORRECT", "INCORRECT"]).sum())
            pending = int((df["resolution_status"] == "PENDING").sum())

        return {
            "year": year,
            "total": len(df),
            "resolved": resolved,
            "pending": pending,
            "predictions": df.where(df.notna(), None).to_dict(orient="records"),
        }
    except Exception as e:
        logger.error(f"Draft summary error for {year}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch draft summary")


# ---------------------------------------------------------------------------
# GET /v1/draft/{year}/results  — Draft resolution scoreboard
# ---------------------------------------------------------------------------


@router.get("/draft/{year}/results", summary="Draft resolution scoreboard")
def draft_results(
    year: int,
    db: DBManager = Depends(get_db),
) -> Dict[str, Any]:
    """
    Returns draft predictions grouped by resolution status for a given year,
    including per-pundit accuracy stats.
    """
    try:
        predictions_query = f"""
            SELECT
                l.prediction_hash,
                l.pundit_id,
                l.pundit_name,
                l.extracted_claim,
                l.target_player_name,
                l.target_team,
                COALESCE(r.resolution_status, 'PENDING')
                    AS resolution_status,
                r.resolved_at,
                r.binary_correct,
                r.weighted_score,
                r.outcome_notes
            FROM {_full(LEDGER_TABLE)} l
            LEFT JOIN {_full(RESOLUTIONS_TABLE)} r
                ON l.prediction_hash = r.prediction_hash
            WHERE l.claim_category = 'draft_pick'
              AND l.season_year = @year
            ORDER BY COALESCE(r.resolution_status, 'PENDING'),
                     l.pundit_name
        """
        params = [ScalarQueryParameter("year", "INT64", year)]
        pred_df = _parameterized_query(db, predictions_query, params)

        pundit_query = f"""
            SELECT
                l.pundit_id,
                l.pundit_name,
                COUNT(*) AS total_predictions,
                COUNTIF(r.resolution_status IN ('CORRECT', 'INCORRECT'))
                    AS resolved_count,
                COUNTIF(r.resolution_status = 'CORRECT')
                    AS correct_count,
                SAFE_DIVIDE(
                    COUNTIF(r.resolution_status = 'CORRECT'),
                    COUNTIF(r.resolution_status IN ('CORRECT', 'INCORRECT'))
                ) AS accuracy_rate,
                AVG(r.weighted_score) AS avg_weighted_score
            FROM {_full(LEDGER_TABLE)} l
            LEFT JOIN {_full(RESOLUTIONS_TABLE)} r
                ON l.prediction_hash = r.prediction_hash
            WHERE l.claim_category = 'draft_pick'
              AND l.season_year = @year
            GROUP BY l.pundit_id, l.pundit_name
            ORDER BY accuracy_rate DESC
        """
        pundit_df = _parameterized_query(db, pundit_query, params)

        grouped: Dict[str, list] = {}
        if not pred_df.empty:
            for status_val, group in pred_df.groupby("resolution_status"):
                grouped[str(status_val)] = group.where(group.notna(), None).to_dict(
                    orient="records"
                )

        return {
            "year": year,
            "total": len(pred_df),
            "by_status": grouped,
            "pundit_accuracy": (
                pundit_df.where(pundit_df.notna(), None).to_dict(orient="records")
                if not pundit_df.empty
                else []
            ),
        }
    except Exception as e:
        logger.error(f"Draft results error for {year}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch draft results")


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
