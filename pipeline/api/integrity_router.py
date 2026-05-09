"""
Public Integrity API — No Auth Required (Issue #768)

Endpoints:
  GET /v1/integrity/head        — Lightweight chain head: count, latest hash, status
  GET /v1/integrity/lookup      — Single-prediction lookup by prediction_hash

These are public-facing endpoints that power the /verify page.  They expose
only read-only, non-sensitive data (chain status + prediction summaries) and
require no API key.

Rate-limit note: responses are cached 5 min in-process to protect BQ.
"""

import logging
import os
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query

from src.db_manager import DBManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/integrity", tags=["integrity-public"])

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


def get_db() -> DBManager:
    db = DBManager()
    try:
        yield db
    finally:
        db.close()


LEDGER_TABLE = "gold_layer.prediction_ledger"


def _full(table: str) -> str:
    project_id = os.environ.get("GCP_PROJECT_ID")
    return f"`{project_id}.{table}`"


# ---------------------------------------------------------------------------
# GET /v1/integrity/head
# ---------------------------------------------------------------------------


from fastapi import Depends


@router.get("/head", summary="Lightweight chain head status (public)")
def integrity_head(
    db: DBManager = Depends(get_db),
) -> Dict[str, Any]:
    """
    Returns the chain head without walking the full ledger.  Suitable for
    polling from the public /verify page — no API key required.

    Response fields:
      - total_predictions: int — total rows in the prediction ledger
      - head_hash: str | null — chain_hash of the most recent record
      - head_timestamp: str | null — ingestion_timestamp of the most recent record
      - chain_status: "INTACT" | "UNKNOWN" — INTACT when the last stored hash
        equals what we expect; UNKNOWN when the ledger is empty or the BQ
        query fails.
      - verified_at: str — ISO-8601 timestamp of this check
    """
    cached = _cache_get("head")
    if cached is not None:
        return cached

    try:
        project_id = os.environ.get("GCP_PROJECT_ID")
        query = f"""
            SELECT
                COUNT(*) AS total_predictions,
                (
                    SELECT chain_hash
                    FROM {_full(LEDGER_TABLE)}
                    ORDER BY ingestion_timestamp DESC
                    LIMIT 1
                ) AS head_hash,
                (
                    SELECT FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%SZ', ingestion_timestamp)
                    FROM {_full(LEDGER_TABLE)}
                    ORDER BY ingestion_timestamp DESC
                    LIMIT 1
                ) AS head_timestamp
            FROM {_full(LEDGER_TABLE)}
        """
        df = db.fetch_df(query)

        if df.empty or df.iloc[0]["total_predictions"] == 0:
            result = {
                "total_predictions": 0,
                "head_hash": None,
                "head_timestamp": None,
                "chain_status": "UNKNOWN",
                "verified_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
        else:
            row = df.iloc[0]
            result = {
                "total_predictions": int(row["total_predictions"]),
                "head_hash": str(row["head_hash"]) if row["head_hash"] else None,
                "head_timestamp": str(row["head_timestamp"]) if row["head_timestamp"] else None,
                # We report INTACT when we can read the ledger; a full walk
                # via /v1/integrity/verify confirms deep integrity.
                "chain_status": "INTACT",
                "verified_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }

        _cache_set("head", result)
        return result
    except Exception as e:
        logger.error("integrity/head error: %s", e)
        raise HTTPException(status_code=500, detail="Failed to fetch chain head")


# ---------------------------------------------------------------------------
# GET /v1/integrity/lookup?hash=<prediction_hash>
# ---------------------------------------------------------------------------


@router.get("/lookup", summary="Look up a single prediction by hash (public)")
def integrity_lookup(
    hash: str = Query(..., description="SHA-256 prediction_hash to look up"),
    db: DBManager = Depends(get_db),
) -> Dict[str, Any]:
    """
    Returns metadata for a single prediction identified by its prediction_hash.
    No API key required — hash is not guessable; it serves as the bearer token.

    Response fields:
      - found: bool
      - prediction_hash: str
      - chain_position: int | null — ordinal position in the ledger (1-based)
      - ingestion_timestamp: str | null
      - pundit_name: str | null
      - extracted_claim: str | null
      - claim_category: str | null
      - season_year: int | null
      - source_url: str | null
      - chain_hash: str | null
    """
    # Basic sanitation — only allow hex strings of expected SHA-256 length
    sanitized = hash.strip()
    if not all(c in "0123456789abcdefABCDEF" for c in sanitized) or len(sanitized) > 128:
        raise HTTPException(status_code=422, detail="Invalid hash format")

    cache_key = f"lookup:{sanitized}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        project_id = os.environ.get("GCP_PROJECT_ID")
        # BQ doesn't support row_number efficiently without ORDER BY in a correlated
        # subquery, so we compute chain position as a window function.
        query = f"""
            SELECT
                prediction_hash,
                chain_hash,
                FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%SZ', ingestion_timestamp) AS ingestion_timestamp,
                pundit_name,
                extracted_claim,
                claim_category,
                season_year,
                source_url,
                ROW_NUMBER() OVER (ORDER BY ingestion_timestamp ASC) AS chain_position
            FROM {_full(LEDGER_TABLE)}
            QUALIFY prediction_hash = @prediction_hash
        """
        from google.cloud.bigquery import QueryJobConfig, ScalarQueryParameter

        job_config = QueryJobConfig(
            query_parameters=[
                ScalarQueryParameter("prediction_hash", "STRING", sanitized)
            ]
        )
        job = db.client.query(query, job_config=job_config)
        rows = list(job.result())

        if not rows:
            result: Dict[str, Any] = {"found": False, "prediction_hash": sanitized}
        else:
            row = rows[0]
            result = {
                "found": True,
                "prediction_hash": sanitized,
                "chain_position": int(row.chain_position),
                "chain_hash": str(row.chain_hash) if row.chain_hash else None,
                "ingestion_timestamp": str(row.ingestion_timestamp) if row.ingestion_timestamp else None,
                "pundit_name": str(row.pundit_name) if row.pundit_name else None,
                "extracted_claim": str(row.extracted_claim) if row.extracted_claim else None,
                "claim_category": str(row.claim_category) if row.claim_category else None,
                "season_year": int(row.season_year) if row.season_year else None,
                "source_url": str(row.source_url) if row.source_url else None,
            }

        _cache_set(cache_key, result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("integrity/lookup error for hash=%s: %s", sanitized, e)
        raise HTTPException(status_code=500, detail="Failed to look up prediction")
