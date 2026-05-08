"""
MCP authentication, tier enforcement, and rate limiting (issue #814 Phase 1).

The MCP transport (FastMCP HTTP/SSE) carries the API key in the
``X-API-Key`` request header.  The verification path reuses the existing
``api_key_auth.verify_api_key`` BigQuery lookup so there is exactly one
source of truth for keys, tiers, and revocation.

Per-key state (the resolved key_info dict and a token-bucket counter) is
stored in process-local memory keyed by ``key_id``.  Redis can be wired
in later by replacing :class:`InMemoryRateLimiter` with a Redis-backed
implementation that exposes the same ``consume`` method — no caller-site
changes required.
"""

from __future__ import annotations

import logging
import os
import time
from contextvars import ContextVar
from threading import Lock
from typing import Any, Dict, Optional

from api.api_key_auth import _hash_key
from src.db_manager import DBManager

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tier matrix — what gets MCP Phase 1 access
# ---------------------------------------------------------------------------

# Phase 1 tools are gated to ``agent_growth`` and above.  ``agent`` is kept as a
# backward-compatible alias that some legacy keys carry (see pundit_router.py
# line 76 — the existing ``agent`` rate-limit row).  ``api_growth`` is also
# admitted because the Phase 1 cut is sellable as an MCP-enabled Growth upsell
# per the issue spec.
PHASE1_ALLOWED_TIERS: frozenset[str] = frozenset(
    {
        "agent",
        "agent_growth",
        "agent_standard",
        "agent_pro",
        "api_growth",
        "enterprise",
    }
)

# Default minimum advertised tier for Phase 1 (used in upgrade_required error).
PHASE1_MIN_TIER = "agent_growth"

# Per-tier rate limits in tokens/min (matches issue spec defaults).
TIER_RATE_LIMITS_PER_MIN: Dict[str, int] = {
    "free": 10,
    "pro": 60,
    "api_starter": 120,
    "api_growth": 300,
    "agent": 200,
    "agent_growth": 200,
    "agent_standard": 200,
    "agent_pro": 500,
    "enterprise": 2000,
}

# Caller-spec'd default: 100 req/min per key.  We use the per-tier table when
# present and fall back to this when a tier is unknown.
DEFAULT_RATE_LIMIT_PER_MIN = 100


# ---------------------------------------------------------------------------
# Context variable — current key_info, set per MCP request
# ---------------------------------------------------------------------------

_current_key_info: ContextVar[Optional[Dict[str, Any]]] = ContextVar(
    "mcp_current_key_info", default=None
)


def get_current_key_info() -> Optional[Dict[str, Any]]:
    """Return the resolved key_info dict for the active request, or None."""
    return _current_key_info.get()


def set_current_key_info(info: Optional[Dict[str, Any]]) -> Any:
    """Bind the key_info dict to the active request context."""
    return _current_key_info.set(info)


def reset_current_key_info(token: Any) -> None:
    """Reset the context var using the token returned by ``set_current_key_info``."""
    _current_key_info.reset(token)


# ---------------------------------------------------------------------------
# Tier checks
# ---------------------------------------------------------------------------


def has_phase1_access(tier: Optional[str]) -> bool:
    if not tier:
        return False
    return tier in PHASE1_ALLOWED_TIERS


def require_phase1_tier(tool_name: str) -> Optional[Dict[str, Any]]:
    """
    Returns ``None`` if the current key is allowed to call Phase 1 tools.
    Otherwise returns an ``UPGRADE_REQUIRED`` error envelope ready to send
    back through the MCP transport.
    """
    info = get_current_key_info()
    tier = (info or {}).get("tier")
    if has_phase1_access(tier):
        return None
    from api.mcp_models import upgrade_required_error

    return upgrade_required_error(
        tool=tool_name,
        user_tier=tier or "anonymous",
        minimum_tier=PHASE1_MIN_TIER,
    )


# ---------------------------------------------------------------------------
# Rate limiter — in-memory token bucket per key_id
# ---------------------------------------------------------------------------


class InMemoryRateLimiter:
    """
    Token-bucket per ``key_id``.  Refill rate = ``capacity_per_min / 60`` per
    second.  Capacity equals one full minute's allotment (so a quiet key can
    burst its full per-minute allowance instantly).
    """

    def __init__(self) -> None:
        self._state: Dict[str, Dict[str, float]] = {}
        self._lock = Lock()

    def consume(
        self,
        key_id: str,
        tier: Optional[str],
        cost: int = 1,
    ) -> Dict[str, Any]:
        capacity = float(
            TIER_RATE_LIMITS_PER_MIN.get(tier or "", DEFAULT_RATE_LIMIT_PER_MIN)
        )
        refill_per_sec = capacity / 60.0
        now = time.monotonic()
        with self._lock:
            row = self._state.get(key_id)
            if row is None:
                row = {"tokens": capacity, "last_refill": now}
                self._state[key_id] = row
            elapsed = max(0.0, now - row["last_refill"])
            row["tokens"] = min(capacity, row["tokens"] + elapsed * refill_per_sec)
            row["last_refill"] = now

            if row["tokens"] >= cost:
                row["tokens"] -= cost
                return {
                    "ok": True,
                    "tokens_remaining": row["tokens"],
                    "capacity": capacity,
                }

            # Reject — compute when the next ``cost`` tokens will be available.
            deficit = cost - row["tokens"]
            retry_after = deficit / refill_per_sec if refill_per_sec > 0 else 60
            return {
                "ok": False,
                "tokens_remaining": row["tokens"],
                "capacity": capacity,
                "retry_after_seconds": int(retry_after) + 1,
            }

    def reset(self, key_id: Optional[str] = None) -> None:
        """Test helper — drop limiter state for a key (or all keys)."""
        with self._lock:
            if key_id is None:
                self._state.clear()
            else:
                self._state.pop(key_id, None)


_GLOBAL_LIMITER = InMemoryRateLimiter()


def get_limiter() -> InMemoryRateLimiter:
    """Module-level singleton — swap for a Redis impl by monkeypatch in tests."""
    return _GLOBAL_LIMITER


def require_quota(tool_name: str, cost: int = 1) -> Optional[Dict[str, Any]]:
    """
    Decrement the caller's bucket; return ``None`` if allowed, otherwise a
    ``RATE_LIMITED`` error envelope.
    """
    info = get_current_key_info() or {}
    key_id = info.get("key_id") or "anonymous"
    tier = info.get("tier")
    decision = get_limiter().consume(key_id, tier, cost=cost)
    if decision["ok"]:
        return None
    from api.mcp_models import rate_limited_error

    return rate_limited_error(
        tool=tool_name,
        user_tier=tier or "anonymous",
        retry_after_seconds=int(decision["retry_after_seconds"]),
    )


# ---------------------------------------------------------------------------
# API key resolution — used by the FastMCP HTTP middleware to populate the
# ContextVar before any tool handler runs.
# ---------------------------------------------------------------------------

# Reuse the existing pundit_router auth fields.
_AUTH_TABLE = "monetization.api_keys"


def resolve_api_key(
    raw_key: str, db: Optional[DBManager] = None
) -> Optional[Dict[str, Any]]:
    """
    Look up ``raw_key`` in BigQuery and return its key row dict (or ``None``
    when missing / revoked).  Mirrors ``api_key_auth.verify_api_key`` but is
    callable from non-FastAPI-dependency code paths (e.g. an ASGI middleware
    on the MCP HTTP transport).
    """
    if not raw_key:
        return None

    try:
        from google.cloud.bigquery import QueryJobConfig, ScalarQueryParameter
    except Exception as exc:  # pragma: no cover — bigquery always present in prod
        logger.error("bigquery client unavailable: %s", exc)
        return None

    close_db = db is None
    if db is None:
        db = DBManager()
    try:
        key_hash = _hash_key(raw_key)
        sql = f"""
            SELECT key_id, user_id, tier, status, scopes, name,
                   created_at, revoked_at, last_used_at, key_last_four
            FROM `{db.project_id}.{_AUTH_TABLE}`
            WHERE key_hash = @key_hash
            LIMIT 1
        """
        params = [ScalarQueryParameter("key_hash", "STRING", key_hash)]
        try:
            job = db.client.query(
                sql, job_config=QueryJobConfig(query_parameters=params)
            )
            rows = list(job.result())
        except Exception as exc:
            logger.error("MCP auth lookup failed: %s", exc)
            return None
        if not rows:
            return None
        raw = rows[0]
        row = dict(raw.items()) if hasattr(raw, "items") else dict(raw)
        if row.get("status") != "active":
            return None
        return row
    finally:
        if close_db:
            try:
                db.close()
            except Exception:
                pass


def is_mcp_auth_disabled() -> bool:
    """
    Test/dev escape hatch: when ``MCP_AUTH_DISABLED=1`` (or ``ENV=test``) the
    server skips the BigQuery auth lookup and pretends the caller is on the
    ``agent_growth`` tier.  Production must never set this.
    """
    return (
        os.environ.get("MCP_AUTH_DISABLED", "").lower() in ("1", "true", "yes")
        or os.environ.get("ENV", "").lower() == "test"
    )
