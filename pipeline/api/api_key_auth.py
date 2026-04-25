"""
B2B API Key Authentication & Rate Limiting (SP30-1 / GH-#108).

Authentication:
  Clients pass their API key in the X-API-Key header.
  Valid keys are read from the B2B_API_KEYS environment variable — a
  comma-separated list of accepted keys (e.g. "key1,key2,key3").
  In production, rotate keys by updating the env var and redeploying.

Rate Limiting:
  Sliding-window in-memory rate limiter (thread-safe).
  Default: 1000 requests per hour per API key.
  Override with B2B_RATE_LIMIT_RPH env var.

Usage (FastAPI dependency injection):
    from api.api_key_auth import require_api_key

    @router.get("/some/endpoint")
    def endpoint(key_info: dict = Depends(require_api_key)):
        ...
"""

import logging
import os
import threading
import time
from collections import deque
from typing import Deque, Dict

from fastapi import Header, HTTPException, status

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_DEFAULT_RATE_LIMIT_RPH = 1000  # requests per hour


def _load_valid_keys() -> frozenset:
    """Load accepted API keys from B2B_API_KEYS env var (comma-separated)."""
    raw = os.environ.get("B2B_API_KEYS", "")
    keys = {k.strip() for k in raw.split(",") if k.strip()}
    return frozenset(keys)


def _get_rate_limit() -> int:
    try:
        return int(os.environ.get("B2B_RATE_LIMIT_RPH", _DEFAULT_RATE_LIMIT_RPH))
    except ValueError:
        return _DEFAULT_RATE_LIMIT_RPH


# ---------------------------------------------------------------------------
# Sliding-window rate limiter
# ---------------------------------------------------------------------------

_WINDOW_SECONDS = 3600  # 1 hour
_lock = threading.Lock()
_request_log: Dict[str, Deque[float]] = {}  # key → deque of request timestamps


def _check_rate_limit(api_key: str) -> None:
    """
    Sliding-window rate limiter.  Raises HTTP 429 if the key exceeds its hourly quota.
    Thread-safe using a module-level lock.
    """
    limit = _get_rate_limit()
    now = time.monotonic()
    window_start = now - _WINDOW_SECONDS

    with _lock:
        if api_key not in _request_log:
            _request_log[api_key] = deque()

        timestamps = _request_log[api_key]

        # Evict timestamps outside the current window
        while timestamps and timestamps[0] < window_start:
            timestamps.popleft()

        if len(timestamps) >= limit:
            oldest = timestamps[0]
            retry_after = int(_WINDOW_SECONDS - (now - oldest)) + 1
            logger.warning(f"Rate limit exceeded for API key (first 8 chars): {api_key[:8]}...")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. {limit} requests/hour allowed.",
                headers={"Retry-After": str(retry_after)},
            )

        timestamps.append(now)


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------


def require_api_key(x_api_key: str = Header(..., alias="X-API-Key")) -> dict:
    """
    FastAPI dependency that validates the X-API-Key header and enforces rate limits.

    Returns a dict with key metadata (currently just the key prefix for logging).
    Raises HTTP 401 if the key is missing or invalid.
    Raises HTTP 429 if the key has exceeded its rate limit.
    """
    valid_keys = _load_valid_keys()

    if not valid_keys:
        # No keys configured — API key auth is disabled (dev/test mode)
        logger.debug("B2B_API_KEYS not set — API key auth disabled")
        return {"key_prefix": "dev", "authenticated": True}

    if x_api_key not in valid_keys:
        logger.warning(f"Invalid API key attempt (first 8 chars): {x_api_key[:8]}...")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key. Pass your key in the X-API-Key header.",
        )

    _check_rate_limit(x_api_key)

    return {
        "key_prefix": x_api_key[:8] + "...",
        "authenticated": True,
    }
