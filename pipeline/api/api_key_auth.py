"""
API Key Authentication — FastAPI dependency for /v1/* routes.

Schema (monetization.api_keys):
  key_id         STRING  — primary key, prefix "capk_"
  key_hash       STRING  — SHA-256(pepper || raw_key)
  key_last_four  STRING  — last 4 chars of the raw key
  user_id        STRING  — Clerk user id
  tier           STRING  — free | pro | api_starter | api_growth | enterprise
  scopes         REPEATED STRING (nullable)
  status         STRING  — active | revoked
  created_at     TIMESTAMP
  revoked_at     TIMESTAMP (nullable)
  last_used_at   TIMESTAMP (nullable)
  last_used_ip   STRING (nullable)
  name           STRING  — user-supplied label

Hashing: SHA-256(pepper || raw_key).  Pepper from env var API_KEY_PEPPER.
Must match web/lib/api-keys/index.ts hashApiKey() exactly — both sides hit the
same BigQuery table.

Startup behaviour:
  - In production (PROD=1 or ENV=production), an absent or short (<16 bytes)
    API_KEY_PEPPER raises RuntimeError at import time — the server refuses to start.
  - In dev/test, missing pepper logs a CRITICAL warning but continues.  This lets
    unit tests run without a pepper set while ensuring production deployments are safe.
"""

import hashlib
import logging
import os
import sys
from typing import Any, Dict, Optional

from fastapi import Depends, Header, HTTPException
from google.cloud.bigquery import QueryJobConfig, ScalarQueryParameter

from src.db_manager import DBManager

logger = logging.getLogger(__name__)

# Table reference helper — project injected at query time via db.project_id
_API_KEYS_TABLE = "monetization.api_keys"

_MIN_PEPPER_BYTES = 16


def _is_production() -> bool:
    """Return True when running in a production environment."""
    return os.environ.get("PROD", "").lower() in ("1", "true", "yes") or os.environ.get(
        "ENV", ""
    ).lower() in ("production", "prod")


def _check_pepper() -> None:
    """
    Validate API_KEY_PEPPER at startup.

    Production: raises RuntimeError (server refuses to start).
    Dev/test:   logs CRITICAL and continues.
    """
    pepper = os.environ.get("API_KEY_PEPPER", "")
    if len(pepper.encode()) < _MIN_PEPPER_BYTES:
        msg = (
            f"API_KEY_PEPPER is {'unset' if not pepper else 'too short'} "
            f"(need >= {_MIN_PEPPER_BYTES} bytes). "
            "Hash strengthening is disabled — keys are vulnerable to offline brute force "
            "if the api_keys table is ever exfiltrated."
        )
        if _is_production():
            raise RuntimeError(
                f"[FATAL] {msg} Set a strong random pepper in Cloud Run secrets before deploying."
            )
        else:
            logger.critical(
                "%s  (tolerated in dev/test — set API_KEY_PEPPER for production)", msg
            )


# Run the check when this module is imported (i.e. at server startup).
_check_pepper()


def _full_table(project_id: str) -> str:
    return f"`{project_id}.{_API_KEYS_TABLE}`"


def _hash_key(raw_key: str) -> str:
    """SHA-256(pepper || raw_key) — must stay in sync with web/lib/api-keys/index.ts hashApiKey().

    Both sides write/read the same BigQuery column, so the algorithm must be identical.
    """
    pepper = os.environ.get("API_KEY_PEPPER", "")
    return hashlib.sha256((pepper + raw_key).encode()).hexdigest()


def get_db_for_auth():
    """Dependency-injected DBManager for auth path. Skipped when API_AUTH_DISABLED=1."""
    if os.environ.get("API_AUTH_DISABLED", "").lower() in ("1", "true", "yes"):
        yield None
        return
    db = DBManager()
    try:
        yield db
    finally:
        db.close()


def verify_api_key(
    x_api_key: Optional[str] = Header(None, description="API key in the form capk_live_..."),
    db: DBManager = Depends(get_db_for_auth),
) -> Dict[str, Any]:
    """
    FastAPI dependency that validates an X-API-Key header against BigQuery.

    Returns the key row dict on success.
    Raises HTTP 401 when key is missing/invalid, HTTP 403 when revoked/expired.

    Set API_AUTH_DISABLED=1 to bypass BQ lookup in local dev (no-op key injected).
    """
    if os.environ.get("API_AUTH_DISABLED", "").lower() in ("1", "true", "yes"):
        return {
            "key_id": "local-dev",
            "user_id": "local-dev-user",
            "tier": "enterprise",
            "status": "active",
            "scopes": [],
            "name": "Local Dev Bypass (API_AUTH_DISABLED)",
        }

    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")

    key_hash = _hash_key(x_api_key)

    sql = f"""
        SELECT
            key_id,
            user_id,
            tier,
            status,
            scopes,
            name,
            created_at,
            revoked_at,
            last_used_at,
            key_last_four
        FROM {_full_table(db.project_id)}
        WHERE key_hash = @key_hash
        LIMIT 1
    """
    try:
        job_config = QueryJobConfig(
            query_parameters=[ScalarQueryParameter("key_hash", "STRING", key_hash)]
        )
        job = db.client.query(sql, job_config=job_config)
        rows = list(job.result())
    except Exception as e:
        logger.error(f"API key lookup failed: {e}")
        raise HTTPException(status_code=500, detail="Auth service unavailable")

    if not rows:
        raise HTTPException(status_code=401, detail="Invalid API key")

    # BigQuery Row supports .items(); plain dicts also have .items() — both work.
    raw = rows[0]
    row = dict(raw.items()) if hasattr(raw, "items") else dict(raw)

    if row.get("status") != "active":
        raise HTTPException(status_code=403, detail="API key has been revoked")

    # Best-effort last_used_at update — fire-and-forget, don't block the request
    try:
        import datetime

        update_sql = f"""
            UPDATE {_full_table(db.project_id)}
            SET last_used_at = @now
            WHERE key_hash = @key_hash
        """
        update_config = QueryJobConfig(
            query_parameters=[
                ScalarQueryParameter(
                    "now",
                    "TIMESTAMP",
                    datetime.datetime.utcnow().isoformat() + "Z",
                ),
                ScalarQueryParameter("key_hash", "STRING", key_hash),
            ]
        )
        db.client.query(update_sql, job_config=update_config)
    except Exception as update_err:
        logger.warning(f"Failed to update last_used_at: {update_err}")

    return row
