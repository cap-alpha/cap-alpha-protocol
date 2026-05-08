"""
Quality Dashboard API — Public Endpoints (Issue #706)

Endpoints:
  GET /v1/quality/extraction-health   — 30-day extraction run rollup
  GET /v1/quality/resolution-stats    — Prediction resolution rates + Brier trend

No API-key auth required — public health data, linked from /methodology.
Responses cached 5 min via module-level dict (no Redis, no new dependencies).
"""

import logging
import os
import time
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException

from src.db_manager import DBManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/quality", tags=["quality-dashboard"])

# ---------------------------------------------------------------------------
# Simple in-memory TTL cache (no Redis, no new dependencies)
# ---------------------------------------------------------------------------

_CACHE: Dict[str, Any] = {}
_CACHE_TTL = 300  # 5 minutes


def _cache_get(key: str) -> Any:
    entry = _CACHE.get(key)
    if entry and time.time() - entry["ts"] < _CACHE_TTL:
        return entry["data"]
    return None


def _cache_set(key: str, data: Any) -> None:
    _CACHE[key] = {"data": data, "ts": time.time()}


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def get_db() -> DBManager:
    db = DBManager()
    try:
        yield db
    finally:
        db.close()


def _full(table: str) -> str:
    """Return a fully-qualified BigQuery table reference."""
    project_id = os.environ.get("GCP_PROJECT_ID")
    return f"`{project_id}.{table}`"


# ---------------------------------------------------------------------------
# GET /v1/quality/extraction-health
# ---------------------------------------------------------------------------

EXTRACTION_RUN_TABLE = "silver_v2_claims.extraction_run"
RAW_UTTERANCE_TABLE = "silver_v2_claims.raw_utterance"


def _compute_testability_trend(daily_rows: List[Dict[str, Any]]) -> str:
    """
    Determine trend direction from the second half vs the first half of rows.
    Returns 'improving', 'declining', or 'stable'.
    """
    if len(daily_rows) < 2:
        return "stable"
    scores = [r.get("mean_testability_score") or 0.0 for r in daily_rows]
    mid = len(scores) // 2
    recent_avg = sum(scores[mid:]) / max(len(scores[mid:]), 1)
    older_avg = sum(scores[:mid]) / max(mid, 1)
    delta = recent_avg - older_avg
    if delta > 0.02:
        return "improving"
    if delta < -0.02:
        return "declining"
    return "stable"


@router.get("/extraction-health", summary="30-day extraction health rollup")
def extraction_health(
    db: DBManager = Depends(get_db),
) -> Dict[str, Any]:
    """
    Returns per-day extraction stats for the last 30 days plus summary metrics.

    Source tables:
      - silver_v2_claims.extraction_run — utterances_written, claims_promoted per run
      - silver_v2_claims.raw_utterance  — testability_score per utterance
    """
    cached = _cache_get("extraction-health")
    if cached is not None:
        return cached

    try:
        # Per-day rollup: join extraction_run with per-day utterance aggregates
        query = f"""
            WITH daily_runs AS (
                SELECT
                    CAST(run_date AS STRING) AS run_date,
                    SUM(utterances_written)  AS utterances_written,
                    SUM(claims_promoted)     AS claims_promoted,
                    LOGICAL_OR(
                        utterances_written = 0 OR utterances_written IS NULL
                    ) AS zero_output
                FROM {_full(EXTRACTION_RUN_TABLE)}
                WHERE run_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
                GROUP BY run_date
            ),
            daily_scores AS (
                SELECT
                    CAST(DATE(published_at) AS STRING) AS run_date,
                    AVG(testability_score)             AS mean_testability_score
                FROM {_full(RAW_UTTERANCE_TABLE)}
                WHERE published_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
                  AND testability_score IS NOT NULL
                GROUP BY run_date
            )
            SELECT
                r.run_date,
                COALESCE(r.utterances_written, 0)               AS utterances_written,
                COALESCE(r.claims_promoted, 0)                  AS claims_promoted,
                COALESCE(r.zero_output, FALSE)                  AS zero_output,
                ROUND(COALESCE(s.mean_testability_score, 0.0), 4) AS mean_testability_score
            FROM daily_runs r
            LEFT JOIN daily_scores s USING (run_date)
            ORDER BY r.run_date ASC
        """

        df = db.client.query(query).to_dataframe()

        if df.empty:
            result: Dict[str, Any] = {
                "last_30_days": [],
                "zero_output_rate_pct": 0.0,
                "testability_trend": "stable",
            }
            _cache_set("extraction-health", result)
            return result

        daily: List[Dict[str, Any]] = []
        for _, row in df.iterrows():
            daily.append({
                "run_date": str(row["run_date"]),
                "utterances_written": int(row["utterances_written"]),
                "claims_promoted": int(row["claims_promoted"]),
                "zero_output": bool(row["zero_output"]),
                "mean_testability_score": float(row["mean_testability_score"]),
            })

        total_days = len(daily)
        zero_days = sum(1 for d in daily if d["zero_output"])
        zero_output_rate = round(
            100.0 * zero_days / total_days if total_days > 0 else 0.0, 1
        )

        trend = _compute_testability_trend(daily)

        result = {
            "last_30_days": daily,
            "zero_output_rate_pct": zero_output_rate,
            "testability_trend": trend,
        }
        _cache_set("extraction-health", result)
        return result

    except Exception as exc:
        logger.error("extraction-health query failed: %s", exc)
        raise HTTPException(
            status_code=500, detail="Failed to fetch extraction health"
        )


# ---------------------------------------------------------------------------
# GET /v1/quality/resolution-stats
# ---------------------------------------------------------------------------

LEDGER_TABLE = "gold_layer.prediction_ledger"
RESOLUTIONS_TABLE = "gold_layer.prediction_resolutions"


@router.get("/resolution-stats", summary="Prediction resolution rates + Brier trend")
def resolution_stats(
    db: DBManager = Depends(get_db),
) -> Dict[str, Any]:
    """
    Returns overall and per-category resolution rates, void rates, and
    weekly mean Brier scores for the last 12 weeks.

    Source tables:
      - gold_layer.prediction_ledger      — predictions by category
      - gold_layer.prediction_resolutions — resolution outcomes + Brier scores
    """
    cached = _cache_get("resolution-stats")
    if cached is not None:
        return cached

    try:
        # Overall resolution + void rates
        overall_query = f"""
            SELECT
                COUNT(l.ledger_id)                                           AS total_count,
                COUNTIF(r.resolution_status IN ('CORRECT', 'INCORRECT'))     AS resolved_count,
                COUNTIF(r.resolution_status = 'VOID')                        AS void_count,
                SAFE_DIVIDE(
                    COUNTIF(r.resolution_status IN ('CORRECT', 'INCORRECT')),
                    COUNT(l.ledger_id)
                )                                                             AS resolution_rate,
                SAFE_DIVIDE(
                    COUNTIF(r.resolution_status = 'VOID'),
                    COUNT(l.ledger_id)
                )                                                             AS void_rate
            FROM {_full(LEDGER_TABLE)} l
            LEFT JOIN {_full(RESOLUTIONS_TABLE)} r
                ON l.ledger_id = r.ledger_id
        """
        overall_df = db.client.query(overall_query).to_dataframe()
        overall_row = overall_df.iloc[0] if not overall_df.empty else None

        resolution_rate_pct = round(
            float(overall_row["resolution_rate"] or 0) * 100, 1
        ) if overall_row is not None else 0.0
        void_rate_pct = round(
            float(overall_row["void_rate"] or 0) * 100, 1
        ) if overall_row is not None else 0.0

        # Per-category breakdown
        category_query = f"""
            SELECT
                l.claim_category                                             AS category,
                COUNT(l.ledger_id)                                           AS count,
                COUNTIF(r.resolution_status IN ('CORRECT', 'INCORRECT'))     AS resolved_count,
                COUNTIF(r.resolution_status = 'VOID')                        AS void_count,
                SAFE_DIVIDE(
                    COUNTIF(r.resolution_status IN ('CORRECT', 'INCORRECT')),
                    COUNT(l.ledger_id)
                )                                                             AS resolution_rate,
                SAFE_DIVIDE(
                    COUNTIF(r.resolution_status = 'VOID'),
                    COUNT(l.ledger_id)
                )                                                             AS void_rate
            FROM {_full(LEDGER_TABLE)} l
            LEFT JOIN {_full(RESOLUTIONS_TABLE)} r
                ON l.ledger_id = r.ledger_id
            WHERE l.claim_category IS NOT NULL
            GROUP BY l.claim_category
            ORDER BY count DESC
        """
        cat_df = db.client.query(category_query).to_dataframe()

        by_category: List[Dict[str, Any]] = []
        for _, row in cat_df.iterrows():
            by_category.append({
                "category": str(row["category"]),
                "count": int(row["count"]),
                "resolution_rate_pct": round(
                    float(row["resolution_rate"] or 0) * 100, 1
                ),
                "void_rate_pct": round(
                    float(row["void_rate"] or 0) * 100, 1
                ),
            })

        # Weekly Brier score — last 12 weeks (84 days)
        brier_query = f"""
            SELECT
                CAST(DATE_TRUNC(r.resolution_date, WEEK(MONDAY)) AS STRING) AS week,
                AVG(r.brier_score)                                            AS mean_brier_score,
                COUNT(*)                                                      AS n
            FROM {_full(RESOLUTIONS_TABLE)} r
            WHERE r.brier_score IS NOT NULL
              AND r.resolution_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 84 DAY)
            GROUP BY week
            ORDER BY week ASC
        """
        brier_df = db.client.query(brier_query).to_dataframe()

        weekly_brier: List[Dict[str, Any]] = []
        for _, row in brier_df.iterrows():
            weekly_brier.append({
                "week": str(row["week"]),
                "mean_brier_score": round(float(row["mean_brier_score"] or 0), 4),
                "n": int(row["n"]),
            })

        result: Dict[str, Any] = {
            "resolution_rate_pct": resolution_rate_pct,
            "void_rate_pct": void_rate_pct,
            "by_category": by_category,
            "weekly_brier": weekly_brier,
        }
        _cache_set("resolution-stats", result)
        return result

    except Exception as exc:
        logger.error("resolution-stats query failed: %s", exc)
        raise HTTPException(
            status_code=500, detail="Failed to fetch resolution stats"
        )
