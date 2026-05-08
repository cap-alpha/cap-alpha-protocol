"""
FastMCP server — Phase 1 tool suite (issue #814).

Mounted on the existing FastAPI app at ``/mcp``.  Six tools, all gated to
``agent_growth`` (and equivalent) tiers and rate-limited via an in-memory
token bucket.

Design notes:
  * One BQ access path: ``DBManager`` constructed lazily on each tool call.
    Connection pooling is handled by the underlying ``google.cloud.bigquery``
    client.
  * Tool handlers call ``require_phase1_tier`` then ``require_quota`` first.
    Either of those returning a non-None value short-circuits the tool with
    a structured error envelope; the MCP transport still sees a successful
    JSON-RPC ``result`` so client agents can branch on the ``error`` field.
  * SQL is parameterized via ``ScalarQueryParameter`` everywhere.  The BQ
    "STRING column LIKE @param" pattern uses ``CONCAT('%', @param, '%')``.
  * The ``window`` argument maps to a WHERE filter on
    ``l.ingestion_timestamp``.  ``last_season`` resolves to "the prior NFL
    season" (Aug 1 of (current_year - 1) through Feb 15 of current_year).
"""

from __future__ import annotations

import logging
import math
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastmcp import FastMCP

from api.mcp_auth import (
    get_current_key_info,
    require_phase1_tier,
    require_quota,
)
from api.mcp_models import (
    DISCLAIMER,
    ActivePrediction,
    ActivePredictionsInput,
    ActivePredictionsOutput,
    ClaimChainNode,
    ClaimSearchHit,
    ComparePunditsInput,
    ComparePunditsOutput,
    LeaderboardEntry,
    LeaderboardInput,
    LeaderboardOutput,
    PunditReliabilityInput,
    PunditReliabilityOutput,
    PunditStatBlock,
    SearchClaimsInput,
    SearchClaimsOutput,
    TraceClaimChainInput,
    TraceClaimChainOutput,
)

logger = logging.getLogger(__name__)

LEDGER_TABLE = "gold_layer.prediction_ledger"
RESOLUTIONS_TABLE = "gold_layer.prediction_resolutions"
CALIBRATION_TABLE = "gold_layer.pundit_calibration"

mcp = FastMCP("cap-alpha-ledger")


# ---------------------------------------------------------------------------
# BQ helpers
# ---------------------------------------------------------------------------


def _project_id() -> str:
    return os.environ.get("GCP_PROJECT_ID", "")


def _full(table: str) -> str:
    return f"`{_project_id()}.{table}`"


def _get_db():
    """Lazy DBManager constructor; tests monkeypatch this for isolation."""
    from src.db_manager import DBManager

    return DBManager()


def _run_query(sql: str, params: List[Any]) -> List[Dict[str, Any]]:
    """Execute a parameterized BQ query and return a list of dict rows."""
    from google.cloud.bigquery import DatasetReference, QueryJobConfig

    db = _get_db()
    try:
        dataset_ref = DatasetReference(db.project_id, db.dataset_id)
        job_config = QueryJobConfig(
            query_parameters=params,
            default_dataset=dataset_ref,
        )
        job = db.client.query(sql, job_config=job_config)
        rows = list(job.result())
        out: List[Dict[str, Any]] = []
        for r in rows:
            if hasattr(r, "items"):
                out.append({k: _coerce(v) for k, v in r.items()})
            else:
                out.append({k: _coerce(v) for k, v in dict(r).items()})
        return out
    finally:
        try:
            db.close()
        except Exception:
            pass


def _coerce(v: Any) -> Any:
    """Make BQ values JSON-friendly (datetimes -> isoformat strings)."""
    if isinstance(v, datetime):
        return v.isoformat()
    return v


def _window_lower_bound(window: str) -> Optional[str]:
    """
    Return an ISO timestamp lower bound for a ``window`` enum, or ``None``
    when no time filter applies.
    """
    now = datetime.now(timezone.utc)
    if window == "30d":
        return (now - timedelta(days=30)).isoformat()
    if window == "90d":
        return (now - timedelta(days=90)).isoformat()
    if window == "season":
        # NFL season runs Aug -> Feb of the next year.  Use Aug 1 of the
        # current league year (= current calendar year if we're past July,
        # else previous year).
        league_year = now.year if now.month >= 8 else now.year - 1
        return datetime(league_year, 8, 1, tzinfo=timezone.utc).isoformat()
    if window == "last_season":
        # Aug 1 of (league_year - 1).
        league_year = now.year if now.month >= 8 else now.year - 1
        return datetime(league_year - 1, 8, 1, tzinfo=timezone.utc).isoformat()
    if window == "career" or window == "any":
        return None
    return None


def _window_upper_bound(window: str) -> Optional[str]:
    """Return an ISO timestamp upper bound for ``last_season``, else None."""
    now = datetime.now(timezone.utc)
    if window == "last_season":
        league_year = now.year if now.month >= 8 else now.year - 1
        # Last season ends ~ Feb 15 of league_year.
        return datetime(league_year, 2, 15, tzinfo=timezone.utc).isoformat()
    return None


def _wilson_interval(n_correct: int, n_resolved: int) -> Optional[Dict[str, float]]:
    """Wilson 95% CI on a binomial proportion (z=1.96).  None if n_resolved<5."""
    if n_resolved < 5:
        return None
    z = 1.96
    p = n_correct / n_resolved
    denom = 1 + z * z / n_resolved
    centre = (p + z * z / (2 * n_resolved)) / denom
    half = (
        z * math.sqrt(p * (1 - p) / n_resolved + z * z / (4 * n_resolved * n_resolved))
    ) / denom
    return {"low": max(0.0, centre - half), "high": min(1.0, centre + half)}


# ---------------------------------------------------------------------------
# Reliability query — used by get_pundit_reliability AND compare_pundits.
# ---------------------------------------------------------------------------


def _reliability_for_pundit(
    pundit: str,
    domain: str,
    claim_type: Optional[str],
    window: str,
) -> Dict[str, Any]:
    from google.cloud.bigquery import ScalarQueryParameter

    where: List[str] = [
        "(l.pundit_id = @pundit OR LOWER(l.pundit_name) LIKE CONCAT('%', LOWER(@pundit), '%'))"
    ]
    params: List[ScalarQueryParameter] = [
        ScalarQueryParameter("pundit", "STRING", pundit)
    ]

    if domain and domain != "any":
        where.append("LOWER(COALESCE(l.sport, 'nfl')) = LOWER(@domain)")
        params.append(ScalarQueryParameter("domain", "STRING", domain))
    if claim_type:
        where.append("l.claim_category = @claim_type")
        params.append(ScalarQueryParameter("claim_type", "STRING", claim_type))

    lower = _window_lower_bound(window)
    if lower is not None:
        where.append("l.ingestion_timestamp >= @lower_ts")
        params.append(ScalarQueryParameter("lower_ts", "TIMESTAMP", lower))
    upper = _window_upper_bound(window)
    if upper is not None:
        where.append("l.ingestion_timestamp < @upper_ts")
        params.append(ScalarQueryParameter("upper_ts", "TIMESTAMP", upper))

    sql = f"""
        SELECT
            ANY_VALUE(l.pundit_id)   AS pundit_id,
            ANY_VALUE(l.pundit_name) AS pundit_name,
            COUNT(*)                                                                AS n_total,
            COUNTIF(r.resolution_status IN ('CORRECT', 'INCORRECT'))                AS n_resolved,
            COUNTIF(r.resolution_status = 'CORRECT')                                AS n_correct,
            SAFE_DIVIDE(
                COUNTIF(r.resolution_status = 'CORRECT'),
                COUNTIF(r.resolution_status IN ('CORRECT', 'INCORRECT'))
            )                                                                       AS accuracy_rate,
            AVG(r.brier_score)     AS brier_score,
            AVG(r.weighted_score)  AS weighted_score
        FROM {_full(LEDGER_TABLE)} l
        LEFT JOIN {_full(RESOLUTIONS_TABLE)} r ON l.prediction_hash = r.prediction_hash
        WHERE {" AND ".join(where)}
    """
    rows = _run_query(sql, params)
    if not rows:
        return {}
    row = rows[0]
    n_correct = int(row.get("n_correct") or 0)
    n_resolved = int(row.get("n_resolved") or 0)
    return {
        "pundit_id": row.get("pundit_id"),
        "pundit_name": row.get("pundit_name"),
        "n_total": int(row.get("n_total") or 0),
        "n_resolved": n_resolved,
        "n_correct": n_correct,
        "accuracy_rate": row.get("accuracy_rate"),
        "brier_score": row.get("brier_score"),
        "weighted_score": row.get("weighted_score"),
        "confidence_interval": _wilson_interval(n_correct, n_resolved),
    }


# ---------------------------------------------------------------------------
# Tool: get_pundit_reliability
# ---------------------------------------------------------------------------


@mcp.tool(
    name="get_pundit_reliability",
    description=(
        "Accuracy + Brier + sample size for a pundit, optionally filtered by "
        "claim_type and time window. Use to decide whether to weight a "
        "specific pundit's claim. Requires agent_growth tier."
    ),
)
def get_pundit_reliability(args: PunditReliabilityInput) -> Dict[str, Any]:
    err = require_phase1_tier("get_pundit_reliability")
    if err is not None:
        return err
    err = require_quota("get_pundit_reliability", cost=1)
    if err is not None:
        return err

    try:
        stats = _reliability_for_pundit(
            pundit=args.pundit_id,
            domain=args.domain,
            claim_type=args.claim_type,
            window=args.window,
        )
    except Exception as exc:
        logger.exception("get_pundit_reliability failed")
        return {
            "error": "INTERNAL",
            "code": -32603,
            "detail": str(exc),
            "disclaimer": DISCLAIMER,
        }

    return PunditReliabilityOutput(
        pundit_id=stats.get("pundit_id"),
        pundit_name=stats.get("pundit_name"),
        domain=args.domain,
        claim_type=args.claim_type,
        window=args.window,
        n_total=stats.get("n_total", 0),
        n_resolved=stats.get("n_resolved", 0),
        n_correct=stats.get("n_correct", 0),
        accuracy_rate=stats.get("accuracy_rate"),
        brier_score=stats.get("brier_score"),
        weighted_score=stats.get("weighted_score"),
        confidence_interval=stats.get("confidence_interval"),
    ).model_dump()


# ---------------------------------------------------------------------------
# Tool: get_active_predictions
# ---------------------------------------------------------------------------


@mcp.tool(
    name="get_active_predictions",
    description=(
        "Unresolved (PENDING) claims about a player, team, or pundit whose "
        "resolution_horizon has not yet passed. Use to see the open "
        "prediction book before placing your own bet. Requires agent_growth tier."
    ),
)
def get_active_predictions(args: ActivePredictionsInput) -> Dict[str, Any]:
    err = require_phase1_tier("get_active_predictions")
    if err is not None:
        return err
    err = require_quota("get_active_predictions", cost=1)
    if err is not None:
        return err

    from google.cloud.bigquery import ScalarQueryParameter

    where: List[str] = ["COALESCE(r.resolution_status, 'PENDING') = 'PENDING'"]
    # resolution_horizon is the deadline by which a claim must be judged;
    # filter out claims whose horizon has already passed (those are stale).
    where.append(
        "(l.resolution_horizon IS NULL OR l.resolution_horizon > CURRENT_TIMESTAMP())"
    )

    params: List[ScalarQueryParameter] = []
    if args.domain and args.domain != "any":
        where.append("LOWER(COALESCE(l.sport, 'nfl')) = LOWER(@domain)")
        params.append(ScalarQueryParameter("domain", "STRING", args.domain))
    if args.entity:
        where.append(
            "(LOWER(COALESCE(l.target_player_name, '')) LIKE CONCAT('%', LOWER(@entity), '%') "
            "OR LOWER(COALESCE(l.target_team, '')) LIKE CONCAT('%', LOWER(@entity), '%') "
            "OR LOWER(COALESCE(l.pundit_id, '')) LIKE CONCAT('%', LOWER(@entity), '%'))"
        )
        params.append(ScalarQueryParameter("entity", "STRING", args.entity))

    params.append(ScalarQueryParameter("lim", "INT64", args.limit))

    sql = f"""
        SELECT
            l.prediction_hash,
            l.pundit_id,
            l.pundit_name,
            l.claim_category,
            l.extracted_claim,
            l.target_player_name,
            l.target_team,
            l.ingestion_timestamp,
            l.resolution_horizon,
            l.source_url
        FROM {_full(LEDGER_TABLE)} l
        LEFT JOIN {_full(RESOLUTIONS_TABLE)} r ON l.prediction_hash = r.prediction_hash
        WHERE {" AND ".join(where)}
        ORDER BY l.ingestion_timestamp DESC
        LIMIT @lim
    """
    try:
        rows = _run_query(sql, params)
    except Exception as exc:
        logger.exception("get_active_predictions failed")
        return {
            "error": "INTERNAL",
            "code": -32603,
            "detail": str(exc),
            "disclaimer": DISCLAIMER,
        }

    items = [
        ActivePrediction(**{k: row.get(k) for k in ActivePrediction.model_fields})
        for row in rows
    ]
    return ActivePredictionsOutput(
        entity=args.entity,
        domain=args.domain,
        n_pending=len(items),
        predictions=items,
    ).model_dump()


# ---------------------------------------------------------------------------
# Tool: search_claims
# ---------------------------------------------------------------------------


@mcp.tool(
    name="search_claims",
    description=(
        "Lexical search across the claim ledger (LIKE / substring on "
        "extracted_claim and raw_assertion_text). Phase 1 is keyword-only; "
        "semantic search ships in Phase 2. Requires agent_growth tier."
    ),
)
def search_claims(args: SearchClaimsInput) -> Dict[str, Any]:
    err = require_phase1_tier("search_claims")
    if err is not None:
        return err
    err = require_quota("search_claims", cost=2)
    if err is not None:
        return err

    from google.cloud.bigquery import ScalarQueryParameter

    where: List[str] = [
        "(LOWER(COALESCE(l.extracted_claim, '')) LIKE CONCAT('%', LOWER(@q), '%') "
        "OR LOWER(COALESCE(l.raw_assertion_text, '')) LIKE CONCAT('%', LOWER(@q), '%'))"
    ]
    params: List[ScalarQueryParameter] = [
        ScalarQueryParameter("q", "STRING", args.query)
    ]

    if args.domain and args.domain != "any":
        where.append("LOWER(COALESCE(l.sport, 'nfl')) = LOWER(@domain)")
        params.append(ScalarQueryParameter("domain", "STRING", args.domain))
    if args.claim_type:
        where.append("l.claim_category = @claim_type")
        params.append(ScalarQueryParameter("claim_type", "STRING", args.claim_type))
    if args.pundit_id:
        where.append("l.pundit_id = @pundit_id")
        params.append(ScalarQueryParameter("pundit_id", "STRING", args.pundit_id))

    params.append(ScalarQueryParameter("lim", "INT64", args.limit))

    sql = f"""
        SELECT
            l.prediction_hash,
            l.pundit_id,
            l.pundit_name,
            l.claim_category,
            l.extracted_claim,
            l.raw_assertion_text,
            COALESCE(r.resolution_status, 'PENDING') AS resolution_status,
            l.ingestion_timestamp,
            l.source_url
        FROM {_full(LEDGER_TABLE)} l
        LEFT JOIN {_full(RESOLUTIONS_TABLE)} r ON l.prediction_hash = r.prediction_hash
        WHERE {" AND ".join(where)}
        ORDER BY l.ingestion_timestamp DESC
        LIMIT @lim
    """
    try:
        rows = _run_query(sql, params)
    except Exception as exc:
        logger.exception("search_claims failed")
        return {
            "error": "INTERNAL",
            "code": -32603,
            "detail": str(exc),
            "disclaimer": DISCLAIMER,
        }

    hits = [
        ClaimSearchHit(**{k: row.get(k) for k in ClaimSearchHit.model_fields})
        for row in rows
    ]
    return SearchClaimsOutput(
        query=args.query,
        n_results=len(hits),
        results=hits,
        search_mode="lexical",
    ).model_dump()


# ---------------------------------------------------------------------------
# Tool: compare_pundits
# ---------------------------------------------------------------------------


@mcp.tool(
    name="compare_pundits",
    description=(
        "Side-by-side accuracy stats for a list of pundits (2-10), optionally "
        "filtered by claim_type. Picks the recommended pundit by highest "
        "weighted_score with at least 5 resolved claims; otherwise reports "
        "'insufficient_data'. Requires agent_growth tier."
    ),
)
def compare_pundits(args: ComparePunditsInput) -> Dict[str, Any]:
    err = require_phase1_tier("compare_pundits")
    if err is not None:
        return err
    err = require_quota("compare_pundits", cost=2)
    if err is not None:
        return err

    blocks: List[PunditStatBlock] = []
    try:
        for pid in args.pundit_ids:
            stats = _reliability_for_pundit(
                pundit=pid,
                domain=args.domain,
                claim_type=args.claim_type,
                window="career",
            )
            blocks.append(
                PunditStatBlock(
                    pundit_id=stats.get("pundit_id") or pid,
                    pundit_name=stats.get("pundit_name"),
                    n_total=stats.get("n_total", 0),
                    n_resolved=stats.get("n_resolved", 0),
                    n_correct=stats.get("n_correct", 0),
                    accuracy_rate=stats.get("accuracy_rate"),
                    brier_score=stats.get("brier_score"),
                    weighted_score=stats.get("weighted_score"),
                )
            )
    except Exception as exc:
        logger.exception("compare_pundits failed")
        return {
            "error": "INTERNAL",
            "code": -32603,
            "detail": str(exc),
            "disclaimer": DISCLAIMER,
        }

    eligible = [
        b for b in blocks if (b.n_resolved or 0) >= 5 and b.weighted_score is not None
    ]
    if eligible:
        recommendation = max(
            eligible, key=lambda b: b.weighted_score or float("-inf")
        ).pundit_id
    else:
        recommendation = "insufficient_data"

    return ComparePunditsOutput(
        domain=args.domain,
        claim_type=args.claim_type,
        pundits=blocks,
        recommendation=recommendation,
    ).model_dump()


# ---------------------------------------------------------------------------
# Tool: trace_claim_chain
# ---------------------------------------------------------------------------


@mcp.tool(
    name="trace_claim_chain",
    description=(
        "Walk the SHA-256 prediction chain backwards from the given "
        "prediction_hash. Returns the requested claim plus up to ``depth`` "
        "predecessors with their chain_hash / prev_hash links so the caller "
        "can verify tamper-evidence. Requires agent_growth tier."
    ),
)
def trace_claim_chain(args: TraceClaimChainInput) -> Dict[str, Any]:
    err = require_phase1_tier("trace_claim_chain")
    if err is not None:
        return err
    err = require_quota("trace_claim_chain", cost=1)
    if err is not None:
        return err

    from google.cloud.bigquery import ScalarQueryParameter

    sql = f"""
        SELECT
            l.prediction_hash,
            l.prev_hash,
            l.chain_hash,
            l.pundit_id,
            l.pundit_name,
            l.extracted_claim,
            l.ingestion_timestamp,
            COALESCE(r.resolution_status, 'PENDING') AS resolution_status
        FROM {_full(LEDGER_TABLE)} l
        LEFT JOIN {_full(RESOLUTIONS_TABLE)} r ON l.prediction_hash = r.prediction_hash
        WHERE l.prediction_hash = @hash
        LIMIT 1
    """
    chain: List[ClaimChainNode] = []
    visited: set[str] = set()
    cursor: Optional[str] = args.prediction_hash
    try:
        for _ in range(args.depth + 1):
            if not cursor or cursor in visited:
                break
            visited.add(cursor)
            rows = _run_query(sql, [ScalarQueryParameter("hash", "STRING", cursor)])
            if not rows:
                break
            row = rows[0]
            chain.append(
                ClaimChainNode(
                    prediction_hash=row.get("prediction_hash") or cursor,
                    prev_hash=row.get("prev_hash"),
                    chain_hash=row.get("chain_hash"),
                    pundit_id=row.get("pundit_id"),
                    pundit_name=row.get("pundit_name"),
                    extracted_claim=row.get("extracted_claim"),
                    ingestion_timestamp=row.get("ingestion_timestamp"),
                    resolution_status=row.get("resolution_status"),
                )
            )
            cursor = row.get("prev_hash")
    except Exception as exc:
        logger.exception("trace_claim_chain failed")
        return {
            "error": "INTERNAL",
            "code": -32603,
            "detail": str(exc),
            "disclaimer": DISCLAIMER,
        }

    if not chain:
        return TraceClaimChainOutput(
            prediction_hash=args.prediction_hash,
            chain=[],
            verified=None,
            verification_status="NOT_FOUND",
        ).model_dump()

    # Chain validity: every node except the genesis must reference a prev_hash
    # that matches the next node we walked to.  We do not recompute SHA-256
    # here (that lives in cryptographic_ledger.verify_chain_integrity); we
    # just confirm the linked-list pointers are consistent.
    consistent = all(
        chain[i].prev_hash == chain[i + 1].prediction_hash
        for i in range(len(chain) - 1)
    )
    return TraceClaimChainOutput(
        prediction_hash=args.prediction_hash,
        chain=chain,
        verified=consistent,
        verification_status="VALID" if consistent else "BROKEN",
    ).model_dump()


# ---------------------------------------------------------------------------
# Tool: get_leaderboard
# ---------------------------------------------------------------------------


@mcp.tool(
    name="get_leaderboard",
    description=(
        "Ranked pundit accuracy across the ledger, optionally filtered by "
        "claim_type and time window. Sorted by weighted_score DESC. "
        "Requires agent_growth tier."
    ),
)
def get_leaderboard(args: LeaderboardInput) -> Dict[str, Any]:
    err = require_phase1_tier("get_leaderboard")
    if err is not None:
        return err
    err = require_quota("get_leaderboard", cost=1)
    if err is not None:
        return err

    from google.cloud.bigquery import ScalarQueryParameter

    where: List[str] = []
    params: List[ScalarQueryParameter] = []
    if args.domain and args.domain != "any":
        where.append("LOWER(COALESCE(l.sport, 'nfl')) = LOWER(@domain)")
        params.append(ScalarQueryParameter("domain", "STRING", args.domain))
    if args.claim_type:
        where.append("l.claim_category = @claim_type")
        params.append(ScalarQueryParameter("claim_type", "STRING", args.claim_type))
    lower = _window_lower_bound(args.window)
    if lower is not None:
        where.append("l.ingestion_timestamp >= @lower_ts")
        params.append(ScalarQueryParameter("lower_ts", "TIMESTAMP", lower))
    upper = _window_upper_bound(args.window)
    if upper is not None:
        where.append("l.ingestion_timestamp < @upper_ts")
        params.append(ScalarQueryParameter("upper_ts", "TIMESTAMP", upper))
    params.append(ScalarQueryParameter("lim", "INT64", args.limit))

    where_sql = f"WHERE {' AND '.join(where)}" if where else ""

    sql = f"""
        SELECT
            l.pundit_id,
            ANY_VALUE(l.pundit_name) AS pundit_name,
            COUNT(*)                                                                AS n_total,
            COUNTIF(r.resolution_status IN ('CORRECT', 'INCORRECT'))                AS n_resolved,
            SAFE_DIVIDE(
                COUNTIF(r.resolution_status = 'CORRECT'),
                COUNTIF(r.resolution_status IN ('CORRECT', 'INCORRECT'))
            )                                                                       AS accuracy_rate,
            AVG(r.brier_score)     AS brier_score,
            AVG(r.weighted_score)  AS weighted_score
        FROM {_full(LEDGER_TABLE)} l
        LEFT JOIN {_full(RESOLUTIONS_TABLE)} r ON l.prediction_hash = r.prediction_hash
        {where_sql}
        GROUP BY l.pundit_id
        HAVING n_resolved >= 5
        ORDER BY weighted_score DESC NULLS LAST
        LIMIT @lim
    """
    try:
        rows = _run_query(sql, params)
    except Exception as exc:
        logger.exception("get_leaderboard failed")
        return {
            "error": "INTERNAL",
            "code": -32603,
            "detail": str(exc),
            "disclaimer": DISCLAIMER,
        }

    entries: List[LeaderboardEntry] = []
    for i, row in enumerate(rows, start=1):
        entries.append(
            LeaderboardEntry(
                rank=i,
                pundit_id=row.get("pundit_id"),
                pundit_name=row.get("pundit_name"),
                n_resolved=int(row.get("n_resolved") or 0),
                accuracy_rate=row.get("accuracy_rate"),
                brier_score=row.get("brier_score"),
                weighted_score=row.get("weighted_score"),
            )
        )

    return LeaderboardOutput(
        domain=args.domain,
        claim_type=args.claim_type,
        window=args.window,
        leaderboard=entries,
        total=len(entries),
    ).model_dump()


# ---------------------------------------------------------------------------
# ASGI integration — exposed for main.py to mount at /mcp.
# ---------------------------------------------------------------------------


def get_mcp_asgi_app(path: str = "/"):
    """
    Return the FastMCP HTTP/SSE ASGI app.  Must be mounted at ``/mcp`` from
    the parent FastAPI app so the final route is ``/mcp/...``.
    """
    return mcp.http_app(path=path)


def get_mcp_server() -> FastMCP:
    """Module accessor — used by tests and ``/mcp/.well-known`` discovery."""
    return mcp


__all__ = [
    "mcp",
    "get_mcp_asgi_app",
    "get_mcp_server",
    "get_pundit_reliability",
    "get_active_predictions",
    "search_claims",
    "compare_pundits",
    "trace_claim_chain",
    "get_leaderboard",
]
