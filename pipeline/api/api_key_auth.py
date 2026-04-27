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
"""

import hashlib
import logging
import os
from typing import Any, Dict

from fastapi import Depends, Header, HTTPException
from google.cloud.bigquery import QueryJobConfig, ScalarQueryParameter

from src.db_manager import DBManager

logger = logging.getLogger(__name__)

# Table reference helper — project injected at query time via db.project_id
_API_KEYS_TABLE = "monetization.api_keys"


def _full_table(project_id: str) -> str:
    return f"`{project_id}.{_API_KEYS_TABLE}`"


def _hash_key(raw_key: str) -> str:
    """SHA-256(pepper || raw_key).  Pepper falls back to empty string when unset."""
    pepper = os.environ.get("API_KEY_PEPPER", "")
    return hashlib.sha256((pepper + raw_key).encode()).hexdigest()


def get_db_for_auth() -> DBManager:
    """Dependency-injected DBManager for auth path (separate from per-request get_db)."""
    db = DBManager()
    try:
        yield db
    finally:
        db.close()


def verify_api_key(
    x_api_key: str = Header(..., description="API key in the form capk_live_..."),
    db: DBManager = Depends(get_db_for_auth),
) -> Dict[str, Any]:
    """
    FastAPI dependency that validates an X-API-Key header against BigQuery.

    Returns the key row dict on success.
    Raises HTTP 401 when key is missing/invalid, HTTP 403 when revoked/expired.
    """
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
