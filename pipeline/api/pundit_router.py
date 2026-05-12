"""
Pundit Scorecard API — Public REST Endpoints (Issue #113, #198, #201)

Endpoints:
  GET /v1/me                                — Authenticated key info (tier, rate limits)
  GET /v1/pundits/                          — List all tracked pundits with summary scores
  GET /v1/pundits/{pundit_id}               — Pundit detail with accuracy breakdown by category
  GET /v1/pundits/{pundit_id}/predictions   — Paginated prediction history with resolution status
  GET /v1/predictions/                      — Filterable prediction search with parameterized queries
  GET /v1/predictions/recent                — Latest resolved predictions across all pundits
  GET /v1/draft/{year}                      — Draft prediction summary for a given year
  GET /v1/draft/{year}/results              — Draft resolution scoreboard for a given year
  GET /v1/leaderboard                       — Ranked pundits by weighted score / accuracy
  GET /v1/integrity/verify                  — Hash chain integrity check (tamper detection)
  GET /v1/me/usage                          — Caller's usage stats (tier, request counts, rate limits)

All /v1/* routes require a valid X-API-Key header (except /v1/me which also requires it,
but returns the key's own metadata).

Quality filtering:
  Most list/search endpoints accept ?min_quality=0.7 to restrict results to
  predictions scored >= that threshold in gold_layer.assertion_quality.
  Tier shortcuts: HIGH=0.7, MEDIUM=0.4, LOW=0.0 (default: no filter).
"""

import logging
import math
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from google.cloud.bigquery import DatasetReference, QueryJobConfig, ScalarQueryParameter

from api.api_key_auth import verify_api_key
from src.calibration import CALIBRATION_TABLE
from src.cryptographic_ledger import verify_chain_integrity
from src.db_manager import DBManager
from src.resolution_engine import get_pundit_accuracy_summary
from src.rolling_windows import get_pundit_rolling_accuracy
from src.scoring import get_pundit_stats

logger = logging.getLogger(__name__)

# Rate limits by tier (requests per minute)
TIER_RATE_LIMITS: Dict[str, int] = {
    "free": 10,
    "pro": 60,
    "api_starter": 120,
    "api_growth": 300,
    "enterprise": 1000,
}

router = APIRouter(
    prefix="/v1",
    tags=["pundit-ledger"],
    dependencies=[Depends(verify_api_key)],
)


def get_db() -> DBManager:
    """FastAPI dependency — yields a DBManager, closes on teardown."""
    db = DBManager()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# /v1/me/usage tier + rate-limit config  (keep in sync with api_key_auth.py)
# ---------------------------------------------------------------------------

# Tier → rate limit config.  Keep in sync with web/lib/api-keys/tiers.ts.
_RATE_LIMITS: Dict[str, Dict[str, int]] = {
    "free": {"requests_per_minute": 100, "requests_per_day": 10_000},
    "pro": {"requests_per_minute": 1_000, "requests_per_day": 100_000},
    "agent": {"requests_per_minute": 10_000, "requests_per_day": 1_000_000},
    "api_starter": {"requests_per_minute": 10_000, "requests_per_day": 1_000_000},
    "api_growth": {"requests_per_minute": 100_000, "requests_per_day": 10_000_000},
    "enterprise": {"requests_per_minute": 999_999, "requests_per_day": 999_999_999},
}

_MONTHLY_QUOTAS: Dict[str, Optional[int]] = {
    "free": 10_000,
    "pro": 100_000,
    "agent": 1_000_000,
    "api_starter": 1_000_000,
    "api_growth": 10_000_000,
    "enterprise": None,
}


LEDGER_TABLE = "gold_layer.prediction_ledger"
RESOLUTIONS_TABLE = "gold_layer.prediction_resolutions"
QUALITY_TABLE = "gold_layer.assertion_quality"
# CALIBRATION_TABLE imported from src.calibration


def _full(table: str) -> str:
    project_id = os.environ.get("GCP_PROJECT_ID")
    return f"`{project_id}.{table}`"


def _quality_join(min_quality: Optional[float]) -> str:
    """Return a JOIN clause + WHERE fragment for quality filtering, or empty strings."""
    if min_quality is None:
        return ""
    return (
        f"INNER JOIN {_full(QUALITY_TABLE)} q "
        f"ON l.prediction_hash = q.prediction_hash "
        f"AND q.quality_score >= {float(min_quality)}"
    )


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
# GET /v1/me — authenticated key metadata
# ---------------------------------------------------------------------------


@router.get("/me", summary="Authenticated API key info")
def me(
    key_info: Dict[str, Any] = Depends(verify_api_key),
) -> Dict[str, Any]:
    """
    Returns the tier, rate limit, scopes, and last-used info for the
    authenticated API key.  Useful for SDK clients to surface quota info.
    """
    tier = key_info.get("tier", "free")
    rate_limit = TIER_RATE_LIMITS.get(tier, TIER_RATE_LIMITS["free"])
    return {
        "key_id": key_info.get("key_id"),
        "name": key_info.get("name"),
        "user_id": key_info.get("user_id"),
        "tier": tier,
        "status": key_info.get("status"),
        "scopes": key_info.get("scopes") or [],
        "rate_limit_per_minute": rate_limit,
        "created_at": str(key_info.get("created_at"))
        if key_info.get("created_at")
        else None,
        "last_used_at": str(key_info.get("last_used_at"))
        if key_info.get("last_used_at")
        else None,
        "key_last_four": key_info.get("key_last_four"),
    }


# ---------------------------------------------------------------------------
# GET /v1/leaderboard
# ---------------------------------------------------------------------------


@router.get("/leaderboard", summary="Ranked pundits by accuracy")
def leaderboard(
    limit: int = Query(default=25, ge=1, le=100),
    min_quality: Optional[float] = Query(
        default=None,
        ge=0.0,
        le=1.0,
        description="Filter predictions by minimum quality score (0.0–1.0). Use 0.7 for HIGH quality only.",
    ),
    db: DBManager = Depends(get_db),
) -> Dict[str, Any]:
    """
    Returns pundits ranked by weighted accuracy score (accuracy × timeliness).
    Accepts ?min_quality=0.7 to restrict to high-quality predictions only.
    """
    try:
        df = get_pundit_accuracy_summary(
            db=db, min_quality=min_quality, min_resolved_claims=5, published_only=True
        )
        if df.empty:
            return {"leaderboard": [], "total": 0}

        # Enrich with composite_score from claim_scores table (best-effort)
        try:
            stats_df = get_pundit_stats(db=db)
            if not stats_df.empty:
                composite_map = stats_df.set_index("pundit_id")[
                    "composite_score"
                ].to_dict()
                df["composite_score"] = df["pundit_id"].map(composite_map)
        except Exception as stats_err:
            logger.warning(f"Could not load composite scores: {stats_err}")

        # Re-sort by composite_score if present, else keep weighted-score order
        if "composite_score" in df.columns and df["composite_score"].notna().any():
            df = df.sort_values("composite_score", ascending=False, na_position="last")

        top = df.head(limit)
        return {
            "leaderboard": top.where(top.notna(), None).to_dict(orient="records"),
            "total": len(df),
            "min_quality_filter": min_quality,
        }
    except Exception as e:
        logger.error(f"Leaderboard error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch leaderboard")


# ---------------------------------------------------------------------------
# GET /v1/pundits/
# ---------------------------------------------------------------------------


@router.get("/pundits/", summary="List all tracked pundits")
def list_pundits(
    min_quality: Optional[float] = Query(
        default=None,
        ge=0.0,
        le=1.0,
        description="Filter predictions by minimum quality score (0.0–1.0).",
    ),
    db: DBManager = Depends(get_db),
) -> Dict[str, Any]:
    """
    Returns all pundits with aggregate accuracy stats.
    Accepts ?min_quality=0.7 to compute stats using only high-quality predictions.
    """
    try:
        df = get_pundit_accuracy_summary(
            db=db, min_quality=min_quality, min_resolved_claims=5, published_only=True
        )

        # Left-join calibration metrics (brier_score, overconfidence_score)
        try:
            project_id = os.environ.get("GCP_PROJECT_ID")
            cal_query = f"""
                SELECT
                    pundit_id,
                    brier_score,
                    overconfidence_score,
                    n_predictions AS calibration_n
                FROM `{project_id}.{CALIBRATION_TABLE}`
            """
            cal_df = db.client.query(cal_query).to_dataframe()
            if not cal_df.empty and not df.empty:
                df = df.merge(cal_df, on="pundit_id", how="left")
        except Exception as cal_err:
            logger.warning("Calibration join failed in list_pundits: %s", cal_err)

        return {
            "pundits": df.where(df.notna(), None).to_dict(orient="records"),
            "total": len(df),
            "min_quality_filter": min_quality,
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

        # Individual pundit detail bypasses the global 5-claim gate so we can
        # still return raw counts; the 404 check below handles the "not found" case.
        summary_df = get_pundit_accuracy_summary(db=db, min_resolved_claims=0)
        pundit_row = summary_df[summary_df["pundit_id"] == pundit_id]
        if pundit_row.empty:
            raise HTTPException(
                status_code=404, detail=f"Pundit '{pundit_id}' not found"
            )

        summary = pundit_row.iloc[0].where(pundit_row.iloc[0].notna(), None).to_dict()
        breakdown = breakdown_df.where(breakdown_df.notna(), None).to_dict(
            orient="records"
        )

        # Fetch calibration metrics (brier_score, overconfidence_score, reliability_bins)
        calibration: Dict[str, Any] = {}
        try:
            cal_query = f"""
                SELECT
                    brier_score,
                    overconfidence_score,
                    reliability_bins,
                    n_predictions AS calibration_n,
                    computed_at AS calibration_computed_at
                FROM {_full(CALIBRATION_TABLE)}
                WHERE pundit_id = @pundit_id
                LIMIT 1
            """
            cal_df = _parameterized_query(
                db, cal_query, [ScalarQueryParameter("pundit_id", "STRING", pundit_id)]
            )
            if not cal_df.empty:
                row = cal_df.iloc[0]
                import json as _json
                calibration = {
                    "brier_score": row["brier_score"] if row["brier_score"] is not None else None,
                    "overconfidence_score": row["overconfidence_score"] if row["overconfidence_score"] is not None else None,
                    "reliability_bins": _json.loads(row["reliability_bins"]) if row.get("reliability_bins") else [],
                    "n_predictions": int(row["calibration_n"]) if row.get("calibration_n") is not None else None,
                    "computed_at": str(row["calibration_computed_at"]) if row.get("calibration_computed_at") is not None else None,
                }
        except Exception as cal_err:
            logger.warning("Calibration fetch failed for %s: %s", pundit_id, cal_err)
            # Calibration is best-effort — don't fail the whole endpoint

        # Fetch rolling accuracy windows (career / last_season / 30d + drift flag)
        rolling: Dict[str, Any] = {}
        try:
            rolling = get_pundit_rolling_accuracy(pundit_id=pundit_id, db=db)
        except Exception as rolling_err:
            logger.warning(
                "Rolling windows fetch failed for %s: %s", pundit_id, rolling_err
            )
            # Best-effort — don't fail the whole endpoint

        return {
            "pundit": {**summary, **calibration},
            "accuracy_by_category": breakdown,
            "rolling_accuracy": rolling,
        }
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
                l.llm_provider,
                l.llm_model,
                l.prompt_version,
                COALESCE(r.resolution_status, 'PENDING') AS resolution_status,
                r.resolved_at,
                r.binary_correct,
                r.brier_score,
                r.weighted_score,
                r.outcome_source,
                r.outcome_notes,
                q.quality_score
            FROM {_full(LEDGER_TABLE)} l
            LEFT JOIN {_full(RESOLUTIONS_TABLE)} r
                ON l.prediction_hash = r.prediction_hash
            LEFT JOIN {_full(QUALITY_TABLE)} q
                ON l.prediction_hash = q.prediction_hash
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
                l.source_url,
                l.raw_assertion_text,
                l.extracted_claim,
                l.claim_category,
                l.season_year,
                l.target_player_id,
                l.target_team,
                l.llm_provider,
                l.llm_model,
                l.prompt_version,
                r.resolution_status,
                r.resolved_at,
                r.binary_correct,
                r.brier_score,
                r.weighted_score,
                r.outcome_source,
                r.outcome_notes,
                q.quality_score
            FROM {_full(LEDGER_TABLE)} l
            INNER JOIN {_full(RESOLUTIONS_TABLE)} r
                ON l.prediction_hash = r.prediction_hash
            LEFT JOIN {_full(QUALITY_TABLE)} q
                ON l.prediction_hash = q.prediction_hash
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
# GET /v1/predictions/similar  — Similar predictions by player/team + category
# ---------------------------------------------------------------------------


@router.get("/predictions/similar", summary="Similar predictions by player or team in same category")
def similar_predictions(
    utterance_id: str = Query(..., description="prediction_hash of the reference prediction"),
    limit: int = Query(default=10, ge=1, le=50),
    db: DBManager = Depends(get_db),
) -> Dict[str, Any]:
    """
    Returns other predictions that share the same claim category AND overlap on
    player or team with the reference prediction (utterance_id = prediction_hash).

    Similarity criteria:
      - (target_player_id matches OR target_team matches) AND claim_category matches
      - utterance_id != reference
      - testability_score proxy: weighted_score IS NOT NULL (resolved predictions) OR
        always included for unresolved — filtered by brier_score availability

    Results ordered by ingestion_timestamp DESC, limited to `limit`.
    """
    try:
        # Step 1: fetch the reference prediction's player/team/category
        ref_query = f"""
            SELECT
                target_player_id,
                target_team,
                claim_category
            FROM {_full(LEDGER_TABLE)}
            WHERE prediction_hash = @utterance_id
            LIMIT 1
        """
        ref_params = [ScalarQueryParameter("utterance_id", "STRING", utterance_id)]
        ref_df = _parameterized_query(db, ref_query, ref_params)

        if ref_df.empty:
            raise HTTPException(status_code=404, detail=f"Prediction '{utterance_id}' not found")

        ref = ref_df.iloc[0]
        target_player_id: str | None = ref["target_player_id"] if ref["target_player_id"] else None
        target_team: str | None = ref["target_team"] if ref["target_team"] else None
        claim_category: str | None = ref["claim_category"] if ref["claim_category"] else None

        # If neither player nor team is set, return empty — nothing to match on
        if not target_player_id and not target_team:
            return {"similar": [], "count": 0, "utterance_id": utterance_id}

        # Step 2: build the similarity WHERE clause
        # (same player OR same team) AND same category AND not the same prediction
        params: List[ScalarQueryParameter] = [
            ScalarQueryParameter("utterance_id", "STRING", utterance_id),
            ScalarQueryParameter("lim", "INT64", limit),
        ]
        overlap_clauses: List[str] = []
        if target_player_id:
            overlap_clauses.append("l.target_player_id = @target_player_id")
            params.append(ScalarQueryParameter("target_player_id", "STRING", target_player_id))
        if target_team:
            overlap_clauses.append("l.target_team = @target_team")
            params.append(ScalarQueryParameter("target_team", "STRING", target_team))

        overlap_sql = " OR ".join(overlap_clauses)
        category_clause = ""
        if claim_category:
            category_clause = "AND l.claim_category = @claim_category"
            params.append(ScalarQueryParameter("claim_category", "STRING", claim_category))

        query = f"""
            SELECT
                l.prediction_hash       AS utterance_id,
                l.pundit_id             AS speaker_entity_id,
                l.pundit_name,
                l.extracted_claim,
                l.ingestion_timestamp   AS uttered_at,
                l.claim_category,
                l.target_player_id,
                l.target_team,
                COALESCE(r.brier_score, NULL)        AS brier_score,
                COALESCE(r.weighted_score, NULL)     AS testability_score,
                COALESCE(r.resolution_status, 'PENDING') AS outcome,
                l.sport
            FROM {_full(LEDGER_TABLE)} l
            LEFT JOIN {_full(RESOLUTIONS_TABLE)} r
                ON l.prediction_hash = r.prediction_hash
            WHERE ({overlap_sql})
              {category_clause}
              AND l.prediction_hash != @utterance_id
            ORDER BY l.ingestion_timestamp DESC
            LIMIT @lim
        """
        df = _parameterized_query(db, query, params)
        return {
            "similar": df.where(df.notna(), None).to_dict(orient="records"),
            "count": len(df),
            "utterance_id": utterance_id,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Similar predictions error for {utterance_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch similar predictions")


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
    min_quality: Optional[float] = Query(
        default=None,
        ge=0.0,
        le=1.0,
        description="Minimum quality score filter (0.0–1.0). Use 0.7 for HIGH quality only.",
    ),
    limit: int = Query(default=50, ge=1, le=200),
    page: int = Query(default=1, ge=1),
    db: DBManager = Depends(get_db),
) -> Dict[str, Any]:
    """
    Filterable prediction search with parameterized BigQuery queries.
    Joins prediction_ledger LEFT JOIN prediction_resolutions.
    Optionally restrict to ?min_quality=0.7 for high-quality predictions only.
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
        quality_join = _quality_join(min_quality)

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
            {quality_join}
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
            {quality_join}
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
            "min_quality_filter": min_quality,
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


# ---------------------------------------------------------------------------
# GET /v1/me/usage  — Caller's usage stats (Issue #148)
# ---------------------------------------------------------------------------


@router.get("/me/usage", summary="Current user's API usage stats")
def me_usage(
    caller: Dict[str, Any] = Depends(verify_api_key),
    db: DBManager = Depends(get_db),
) -> Dict[str, Any]:
    """
    Returns usage stats for the authenticated API key owner.

    Reads from monetization.api_requests (populated by the metering middleware
    from issue #145).  If the table is empty or missing, returns stubs with
    zero counts so the dashboard always renders.
    """
    user_id: str = caller["user_id"]
    tier: str = caller.get("tier") or "free"
    rate_limits = _RATE_LIMITS.get(tier, _RATE_LIMITS["free"])
    monthly_quota = _MONTHLY_QUOTAS.get(tier, _MONTHLY_QUOTAS["free"])

    project_id = os.environ.get("GCP_PROJECT_ID", "cap-alpha-protocol")
    requests_table = f"`{project_id}.monetization.api_requests`"

    try:
        sql = f"""
            SELECT
                COUNTIF(ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 MINUTE))
                    AS requests_last_minute,
                COUNTIF(ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 DAY))
                    AS requests_today,
                COUNTIF(
                    ts >= TIMESTAMP_TRUNC(CURRENT_TIMESTAMP(), MONTH)
                )                                          AS requests_this_month,
                COUNT(*)                                   AS requests_total
            FROM {requests_table}
            WHERE user_id = @user_id
        """
        params = [ScalarQueryParameter("user_id", "STRING", user_id)]
        job_config = QueryJobConfig(query_parameters=params)
        job = db.client.query(sql, job_config=job_config)
        rows = list(job.result())
        row = rows[0] if rows else None

        requests_last_minute = int(row.requests_last_minute) if row else 0
        requests_today = int(row.requests_today) if row else 0
        requests_this_month = int(row.requests_this_month) if row else 0
        requests_total = int(row.requests_total) if row else 0

    except Exception as exc:
        # Table may not exist yet (metering pipeline from #145 not deployed)
        logger.warning("me/usage: could not query api_requests: %s", exc)
        requests_last_minute = 0
        requests_today = 0
        requests_this_month = 0
        requests_total = 0

    return {
        "tier": tier,
        "tier_display": tier.replace("_", " ").title(),
        "monthly_quota": monthly_quota,
        "requests_last_minute": requests_last_minute,
        "requests_today": requests_today,
        "requests_this_month": requests_this_month,
        "requests_total": requests_total,
        "rate_limit": rate_limits,
    }
