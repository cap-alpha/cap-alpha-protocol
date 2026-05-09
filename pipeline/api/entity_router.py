"""
Entity API — FastAPI endpoints for per-entity pages (Issue #816)

Endpoints:
  GET /v1/entities/{entity_id}                — EntityData summary (claim counts + metadata)
  GET /v1/entities/{entity_id}/claims         — Paginated list of ClaimItem
  GET /v1/entities/{entity_id}/pundit-accuracy — Per-pundit accuracy on this entity
  GET /v1/entities/{entity_id}/related        — Co-mentioned entities (related)

All /v1/* routes require a valid X-API-Key header (via pundit_router dependency pattern).

Entity ID conventions
---------------------
Entity IDs are URL-encoded strings that correspond to either:
  - target_player_name (player entities)   e.g. "Patrick Mahomes" → "Patrick+Mahomes"
  - target_team (team entities)            e.g. "KC" or "Kansas City Chiefs"

The entity_type route param ('player', 'team', 'coach', etc.) narrows the search
column.  An unrecognised entity_type falls back to searching both columns.

NOTE: A dedicated entity catalogue table does not yet exist in BigQuery.  Until
one is populated (see issue #816 Phase 2), entity lookup falls back to LIKE
matching on `target_player_name` / `target_team`.  The fallback is clearly marked
with # FALLBACK comments below so it can be swapped for a proper catalogue query
once that table exists.
"""

import logging
import math
import os
from typing import Any, Dict, List, Optional
from urllib.parse import unquote_plus

from fastapi import APIRouter, Depends, HTTPException, Query
from google.cloud.bigquery import DatasetReference, QueryJobConfig, ScalarQueryParameter

from api.api_key_auth import verify_api_key
from src.db_manager import DBManager

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1/entities",
    tags=["entities"],
    dependencies=[Depends(verify_api_key)],
)

# ---------------------------------------------------------------------------
# Table references (must match pundit_router.py conventions)
# ---------------------------------------------------------------------------

LEDGER_TABLE = "gold_layer.prediction_ledger"
RESOLUTIONS_TABLE = "gold_layer.prediction_resolutions"
QUALITY_TABLE = "gold_layer.assertion_quality"


def _full(table: str) -> str:
    project_id = os.environ.get("GCP_PROJECT_ID")
    return f"`{project_id}.{table}`"


def get_db() -> DBManager:
    """FastAPI dependency — yields a DBManager, closes on teardown."""
    db = DBManager()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parameterized_query(db: DBManager, sql: str, params: List[ScalarQueryParameter]):
    """Execute a parameterized BigQuery query and return a DataFrame."""
    dataset_ref = DatasetReference(db.project_id, db.dataset_id)
    job_config = QueryJobConfig(
        query_parameters=params,
        default_dataset=dataset_ref,
    )
    job = db.client.query(sql, job_config=job_config)
    return job.to_dataframe()


def _entity_where(entity_type: str, param_name: str = "entity_name") -> str:
    """
    Return a WHERE fragment that matches the given entity by type.

    entity_type is one of: player, team, coach, pundit, game, award, event.
    Falls back to OR-matching both columns for unknown types.

    # FALLBACK: When a gold_layer.entity_catalogue table exists, replace this
    # with a JOIN on entity_catalogue WHERE entity_id = @entity_id.
    """
    if entity_type in ("player", "coach"):
        return f"LOWER(l.target_player_name) = LOWER(@{param_name})"
    elif entity_type == "team":
        return f"LOWER(l.target_team) = LOWER(@{param_name})"
    elif entity_type == "pundit":
        # Pundits as entities — match against pundit_id or pundit_name
        return f"(LOWER(l.pundit_id) = LOWER(@{param_name}) OR LOWER(l.pundit_name) = LOWER(@{param_name}))"
    else:
        # Unknown entity type — search both player and team columns
        return (
            f"(LOWER(l.target_player_name) = LOWER(@{param_name}) "
            f"OR LOWER(l.target_team) = LOWER(@{param_name}))"
        )


def _verdict_from_accuracy(accuracy_pct: Optional[float]) -> Optional[str]:
    """Map accuracy percentage to a verdict label matching the frontend enum."""
    if accuracy_pct is None:
        return None
    if accuracy_pct >= 75:
        return "Expert"
    if accuracy_pct >= 65:
        return "Reliable"
    if accuracy_pct >= 50:
        return "Average"
    return "Avoid"


# ---------------------------------------------------------------------------
# GET /v1/entities/{entity_id}
# ---------------------------------------------------------------------------


@router.get("/{entity_id}", summary="Entity summary — name, type, claim counts")
def entity_detail(
    entity_id: str,
    entity_type: str = Query(
        default="player",
        description="player | team | coach | pundit | game | award | event",
    ),
    db: DBManager = Depends(get_db),
) -> Dict[str, Any]:
    """
    Returns EntityData: entity metadata + aggregate claim counts.

    entity_id is URL-decoded and matched case-insensitively against
    target_player_name (for player/coach) or target_team (for team).
    """
    entity_name = unquote_plus(entity_id)

    where_fragment = _entity_where(entity_type)
    params: List[ScalarQueryParameter] = [
        ScalarQueryParameter("entity_name", "STRING", entity_name),
    ]

    # FALLBACK: aggregate claim counts from prediction_ledger directly.
    # Replace with entity_catalogue JOIN when that table is available (#816 Phase 2).
    simple_query = f"""
        SELECT
            COUNT(*)                                                         AS total_claims,
            COUNTIF(COALESCE(r.resolution_status, 'PENDING') = 'CORRECT')   AS correct_claims,
            COUNTIF(COALESCE(r.resolution_status, 'PENDING') = 'INCORRECT') AS incorrect_claims,
            COUNTIF(COALESCE(r.resolution_status, 'PENDING') = 'PENDING')   AS pending_claims
        FROM {_full(LEDGER_TABLE)} l
        LEFT JOIN {_full(RESOLUTIONS_TABLE)} r
            ON l.prediction_hash = r.prediction_hash
        WHERE {where_fragment}
    """

    try:
        df = _parameterized_query(db, simple_query, params)

        if df.empty or int(df.iloc[0]["total_claims"]) == 0:
            raise HTTPException(
                status_code=404,
                detail=f"Entity '{entity_name}' not found (type={entity_type})",
            )

        row = df.iloc[0]
        total_claims = int(row["total_claims"])
        correct_claims = int(row["correct_claims"])
        incorrect_claims = int(row["incorrect_claims"])
        pending_claims = int(row["pending_claims"])

        return {
            "entity_id": entity_id,
            "entity_type": entity_type,
            "entity_name": entity_name,
            "entity_subtype": None,  # populated by entity_catalogue Phase 2
            "context": None,  # populated by entity_catalogue Phase 2
            "tags": [],  # populated by entity_catalogue Phase 2
            "total_claims": total_claims,
            "correct_claims": correct_claims,
            "incorrect_claims": incorrect_claims,
            "pending_claims": pending_claims,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("entity_detail error for %s (%s): %s", entity_name, entity_type, e)
        raise HTTPException(status_code=500, detail="Failed to fetch entity detail")


# ---------------------------------------------------------------------------
# GET /v1/entities/{entity_id}/claims
# ---------------------------------------------------------------------------


@router.get("/{entity_id}/claims", summary="Paginated claims mentioning this entity")
def entity_claims(
    entity_id: str,
    entity_type: str = Query(
        default="player",
        description="player | team | coach | pundit | game | award | event",
    ),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status: Optional[str] = Query(
        default=None,
        description="Filter by resolution_status: CORRECT | INCORRECT | PENDING",
    ),
    db: DBManager = Depends(get_db),
) -> Dict[str, Any]:
    """
    Returns a paginated list of ClaimItem records for the entity.

    Each ClaimItem includes:
      claim_id (= prediction_hash), pundit_id, pundit_name, outlet (source_url domain),
      claim_text, claim_date, claim_context (season_year + category), resolution_status,
      confidence (quality_score), hash_short.
    """
    entity_name = unquote_plus(entity_id)
    where_fragment = _entity_where(entity_type)

    status_clause = ""
    params: List[ScalarQueryParameter] = [
        ScalarQueryParameter("entity_name", "STRING", entity_name),
        ScalarQueryParameter("lim", "INT64", limit),
        ScalarQueryParameter("off", "INT64", offset),
    ]
    if status:
        status_clause = "AND COALESCE(r.resolution_status, 'PENDING') = @status"
        params.append(ScalarQueryParameter("status", "STRING", status))

    query = f"""
        SELECT
            l.prediction_hash                                                   AS claim_id,
            l.pundit_id,
            l.pundit_name,
            -- Derive outlet from source_url domain (best-effort, no full URL parse)
            REGEXP_EXTRACT(l.source_url, r'https?://(?:www\\.)?([^/]+)')        AS outlet,
            l.extracted_claim                                                    AS claim_text,
            FORMAT_TIMESTAMP('%b %d, %Y', l.ingestion_timestamp)                AS claim_date,
            -- claim_context: "Season YYYY · category"
            CONCAT(
                COALESCE(CAST(l.season_year AS STRING), ''),
                IF(l.claim_category IS NOT NULL, CONCAT(' · ', l.claim_category), '')
            )                                                                   AS claim_context,
            COALESCE(r.resolution_status, 'PENDING')                            AS resolution_status,
            q.quality_score                                                     AS confidence,
            -- hash_short: first 4 chars … last 4 chars
            CONCAT(SUBSTR(l.prediction_hash, 1, 4), '…', SUBSTR(l.prediction_hash, -4)) AS hash_short
        FROM {_full(LEDGER_TABLE)} l
        LEFT JOIN {_full(RESOLUTIONS_TABLE)} r
            ON l.prediction_hash = r.prediction_hash
        LEFT JOIN {_full(QUALITY_TABLE)} q
            ON l.prediction_hash = q.prediction_hash
        WHERE {where_fragment}
          {status_clause}
        ORDER BY l.ingestion_timestamp DESC
        LIMIT @lim OFFSET @off
    """

    count_query = f"""
        SELECT COUNT(*) AS total
        FROM {_full(LEDGER_TABLE)} l
        LEFT JOIN {_full(RESOLUTIONS_TABLE)} r
            ON l.prediction_hash = r.prediction_hash
        WHERE {where_fragment}
          {status_clause}
    """

    try:
        df = _parameterized_query(db, query, params)

        # Count query uses same params (excluding lim/off which are not referenced)
        count_params = [p for p in params if p.name not in ("lim", "off")]
        count_df = _parameterized_query(db, count_query, count_params)
        total = int(count_df.iloc[0]["total"]) if not count_df.empty else 0

        return {
            "entity_id": entity_id,
            "claims": df.where(df.notna(), None).to_dict(orient="records"),
            "limit": limit,
            "offset": offset,
            "total": total,
            "pages": max(1, math.ceil(total / limit)),
        }
    except Exception as e:
        logger.error("entity_claims error for %s (%s): %s", entity_name, entity_type, e)
        raise HTTPException(status_code=500, detail="Failed to fetch entity claims")


# ---------------------------------------------------------------------------
# GET /v1/entities/{entity_id}/pundit-accuracy
# ---------------------------------------------------------------------------


@router.get(
    "/{entity_id}/pundit-accuracy", summary="Per-pundit accuracy for this entity"
)
def entity_pundit_accuracy(
    entity_id: str,
    entity_type: str = Query(
        default="player",
        description="player | team | coach | pundit | game | award | event",
    ),
    min_claims: int = Query(
        default=1, ge=1, description="Minimum claims threshold to include a pundit"
    ),
    db: DBManager = Depends(get_db),
) -> Dict[str, Any]:
    """
    Returns a list of PunditAccuracyRow — one row per pundit who has made
    at least min_claims claims about this entity, sorted by accuracy desc.

    Fields: pundit_id, pundit_name, outlet, claims, correct, accuracy_pct, brier_score, verdict.
    """
    entity_name = unquote_plus(entity_id)
    where_fragment = _entity_where(entity_type)

    params: List[ScalarQueryParameter] = [
        ScalarQueryParameter("entity_name", "STRING", entity_name),
        ScalarQueryParameter("min_claims", "INT64", min_claims),
    ]

    query = f"""
        SELECT
            l.pundit_id,
            l.pundit_name,
            REGEXP_EXTRACT(
                MIN(l.source_url), r'https?://(?:www\\.)?([^/]+)'
            )                                                               AS outlet,
            COUNT(*)                                                        AS claims,
            COUNTIF(r.resolution_status = 'CORRECT')                       AS correct,
            SAFE_DIVIDE(
                COUNTIF(r.resolution_status = 'CORRECT'),
                COUNTIF(r.resolution_status IN ('CORRECT', 'INCORRECT'))
            ) * 100                                                         AS accuracy_pct,
            AVG(r.brier_score)                                              AS brier_score
        FROM {_full(LEDGER_TABLE)} l
        LEFT JOIN {_full(RESOLUTIONS_TABLE)} r
            ON l.prediction_hash = r.prediction_hash
        WHERE {where_fragment}
        GROUP BY l.pundit_id, l.pundit_name
        HAVING COUNT(*) >= @min_claims
        ORDER BY accuracy_pct DESC NULLS LAST, claims DESC
    """

    try:
        df = _parameterized_query(db, query, params)

        rows = []
        for _, row in df.iterrows():
            accuracy_pct = (
                float(row["accuracy_pct"]) if row["accuracy_pct"] is not None else None
            )
            rows.append(
                {
                    "pundit_id": row["pundit_id"],
                    "pundit_name": row["pundit_name"],
                    "outlet": row["outlet"] if row["outlet"] is not None else None,
                    "claims": int(row["claims"]),
                    "correct": int(row["correct"]),
                    "accuracy_pct": round(accuracy_pct, 1)
                    if accuracy_pct is not None
                    else None,
                    "brier_score": float(row["brier_score"])
                    if row["brier_score"] is not None
                    else None,
                    "verdict": _verdict_from_accuracy(accuracy_pct),
                }
            )

        return {
            "entity_id": entity_id,
            "pundit_accuracy": rows,
            "total": len(rows),
        }
    except Exception as e:
        logger.error(
            "entity_pundit_accuracy error for %s (%s): %s", entity_name, entity_type, e
        )
        raise HTTPException(
            status_code=500, detail="Failed to fetch pundit accuracy for entity"
        )


# ---------------------------------------------------------------------------
# GET /v1/entities/{entity_id}/related
# ---------------------------------------------------------------------------


@router.get("/{entity_id}/related", summary="Related entities (co-mentioned in claims)")
def entity_related(
    entity_id: str,
    entity_type: str = Query(
        default="player",
        description="player | team | coach | pundit | game | award | event",
    ),
    limit: int = Query(default=10, ge=1, le=50),
    db: DBManager = Depends(get_db),
) -> Dict[str, Any]:
    """
    Returns a list of RelatedEntity — entities that appear in the same claims as
    this entity.  Co-mention count is the number of shared predictions.

    For player entities: related entities are teams mentioned in the same predictions.
    For team entities: related entities are players mentioned in the same predictions.

    # FALLBACK: This uses the current simple column-based matching.  A future
    # version with an entity_catalogue will use entity graph edges.
    """
    entity_name = unquote_plus(entity_id)
    where_fragment = _entity_where(entity_type)

    params: List[ScalarQueryParameter] = [
        ScalarQueryParameter("entity_name", "STRING", entity_name),
        ScalarQueryParameter("lim", "INT64", limit),
    ]

    # For player entities: return related teams
    # For team entities: return related players
    # For others: return both
    if entity_type in ("player", "coach"):
        related_query = f"""
            SELECT
                l.target_team                                           AS related_name,
                'team'                                                  AS related_type,
                COUNT(*)                                                AS co_mention_count
            FROM {_full(LEDGER_TABLE)} l
            WHERE {where_fragment}
              AND l.target_team IS NOT NULL
              AND l.target_team != ''
            GROUP BY l.target_team
            ORDER BY co_mention_count DESC
            LIMIT @lim
        """
    elif entity_type == "team":
        related_query = f"""
            SELECT
                l.target_player_name                                    AS related_name,
                'player'                                                AS related_type,
                COUNT(*)                                                AS co_mention_count
            FROM {_full(LEDGER_TABLE)} l
            WHERE {where_fragment}
              AND l.target_player_name IS NOT NULL
              AND l.target_player_name != ''
            GROUP BY l.target_player_name
            ORDER BY co_mention_count DESC
            LIMIT @lim
        """
    else:
        # Generic: return top co-mentioned players
        related_query = f"""
            SELECT
                COALESCE(l.target_player_name, l.target_team)          AS related_name,
                IF(l.target_player_name IS NOT NULL, 'player', 'team') AS related_type,
                COUNT(*)                                                AS co_mention_count
            FROM {_full(LEDGER_TABLE)} l
            WHERE {where_fragment}
              AND COALESCE(l.target_player_name, l.target_team) IS NOT NULL
            GROUP BY l.target_player_name, l.target_team
            ORDER BY co_mention_count DESC
            LIMIT @lim
        """

    try:
        df = _parameterized_query(db, related_query, params)

        related_entities = []
        for _, row in df.iterrows():
            related_name = row.get("related_name")
            if not related_name:
                continue
            related_type = str(row.get("related_type", "player"))
            # Build a URL-safe entity_id from the related name
            related_entity_id = str(related_name)
            # Initials: first letter of each word
            initials = "".join(w[0].upper() for w in related_name.split() if w)[:2]
            related_entities.append(
                {
                    "entity_id": related_entity_id,
                    "entity_type": related_type,
                    "entity_name": str(related_name),
                    "entity_subtype": None,
                    "co_mention_count": int(row["co_mention_count"]),
                    "initials": initials or "??",
                }
            )

        return {
            "entity_id": entity_id,
            "related": related_entities,
            "total": len(related_entities),
        }
    except Exception as e:
        logger.error(
            "entity_related error for %s (%s): %s", entity_name, entity_type, e
        )
        raise HTTPException(status_code=500, detail="Failed to fetch related entities")
