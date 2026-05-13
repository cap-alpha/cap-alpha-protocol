"""
verify_kg_migration.py — Phase 2 verification gate.

Runs the four zero-count checks from issue #920 Phase 2 verification gate.
Prints PASS/FAIL for each check. Exits 0 if all pass, 1 if any fail.

Supports both BigQuery (default) and DuckDB (DB_BACKEND=duckdb) modes.

Usage:
    GCP_PROJECT_ID=my-project python pipeline/scripts/verify_kg_migration.py
    DB_BACKEND=duckdb python pipeline/scripts/verify_kg_migration.py

Prerequisites (BigQuery):
    - GCP_PROJECT_ID environment variable set
    - Phase 1 DDL applied (claim_entity_link, claim_state_history tables exist)
    - Phase 2 ledger + resolution migrations run

Prerequisites (DuckDB):
    - DB_BACKEND=duckdb
    - DUCKDB_PATH pointing to the DuckDB file (default: pipeline/data/local.duckdb)
    - init_local_db.py + seed_test_data_duckdb.py + run_kg_migration_duckdb.py already run
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

try:
    from google.cloud import bigquery
except ImportError:  # pragma: no cover
    bigquery = None  # type: ignore[assignment]

_SCRIPT_DIR = Path(__file__).resolve().parent
_PIPELINE_DIR = _SCRIPT_DIR.parent
_DEFAULT_DB_PATH = _PIPELINE_DIR / "data" / "local.duckdb"


def _require_env(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        log.error("Environment variable %s is required but not set.", name)
        sys.exit(1)
    return val


# ---------------------------------------------------------------------------
# DuckDB-mode verification
# ---------------------------------------------------------------------------

# Queries using DuckDB schema-qualified table names (no project prefix)
_DUCKDB_CHECKS: list[tuple[str, str]] = [
    (
        "Every legacy claim present in silver_v2",
        """
        SELECT COUNT(*)
        FROM gold_layer.prediction_ledger pl
        LEFT JOIN silver_v2_claims.claim c
            ON c.legacy_prediction_hash = pl.prediction_hash
        WHERE c.claim_id IS NULL
        """,
    ),
    (
        "Every legacy resolution present in silver_v2",
        """
        SELECT COUNT(*)
        FROM gold_layer.prediction_resolutions pr
        LEFT JOIN silver_v2_claims.claim c
            ON c.legacy_prediction_hash = pr.prediction_hash
        LEFT JOIN silver_v2_claims.resolution r
            ON r.claim_id = c.claim_id
        WHERE r.resolution_id IS NULL
        """,
    ),
    (
        "Every claim has at least one claim_state_history row",
        """
        SELECT COUNT(*)
        FROM silver_v2_claims.claim c
        LEFT JOIN silver_v2_claims.claim_state_history h
            ON h.claim_id = c.claim_id
        WHERE h.history_id IS NULL
        """,
    ),
    (
        "Every claim with a subject has at least one claim_entity_link",
        """
        SELECT COUNT(*)
        FROM silver_v2_claims.claim c
        LEFT JOIN silver_v2_claims.claim_entity_link l
            ON l.claim_id = c.claim_id
        WHERE l.link_id IS NULL
          AND c.claim_subject_type IS NOT NULL
        """,
    ),
]


def run_all_checks_duckdb(db_path: str) -> bool:
    """Run all verification checks against DuckDB. Returns True if all pass."""
    import duckdb

    conn = duckdb.connect(db_path, read_only=True)
    print(f"\nKnowledge Graph Migration Verification — DuckDB: {db_path}")
    print("=" * 70)

    results = []
    for check_name, query in _DUCKDB_CHECKS:
        try:
            count = conn.execute(query).fetchone()[0]
            if count == 0:
                print(f"  PASS  {check_name} (count=0)")
                results.append(True)
            else:
                print(f"  FAIL  {check_name} (count={count})")
                results.append(False)
        except Exception as exc:
            print(f"  ERROR {check_name}: {exc}")
            results.append(False)

    conn.close()

    print("=" * 70)
    passed_count = sum(results)
    total = len(results)
    if all(results):
        print(f"ALL {total} CHECKS PASSED — Phase 2 migration verified.")
        return True
    else:
        failed = total - passed_count
        print(f"{failed}/{total} CHECKS FAILED — migration incomplete or has gaps.")
        return False


# ---------------------------------------------------------------------------
# BigQuery-mode verification
# ---------------------------------------------------------------------------


def _run_check(
    client: "bigquery.Client",
    project_id: str,
    check_name: str,
    query: str,
) -> bool:
    """Run a single verification query. Returns True (PASS) if count == 0."""
    try:
        job = client.query(query.format(project_id=project_id))
        rows = list(job.result())
        count = rows[0][0] if rows else -1
        if count == 0:
            print(f"  PASS  {check_name} (count=0)")
            return True
        else:
            print(f"  FAIL  {check_name} (count={count})")
            return False
    except Exception as exc:
        print(f"  ERROR {check_name}: {exc}")
        return False


CHECKS: list[tuple[str, str]] = [
    (
        "Every legacy claim present in silver_v2",
        """
        SELECT COUNT(*)
        FROM `{project_id}.gold_layer.prediction_ledger` pl
        LEFT JOIN `{project_id}.silver_v2_claims.claim` c
            ON c.legacy_prediction_hash = pl.prediction_hash
        WHERE c.claim_id IS NULL
        """,
    ),
    (
        "Every legacy resolution present in silver_v2",
        """
        SELECT COUNT(*)
        FROM `{project_id}.gold_layer.prediction_resolutions` pr
        LEFT JOIN `{project_id}.silver_v2_claims.claim` c
            ON c.legacy_prediction_hash = pr.prediction_hash
        LEFT JOIN `{project_id}.silver_v2_claims.resolution` r
            ON r.claim_id = c.claim_id
        WHERE r.resolution_id IS NULL
        """,
    ),
    (
        "Every claim has at least one claim_state_history row",
        """
        SELECT COUNT(*)
        FROM `{project_id}.silver_v2_claims.claim` c
        LEFT JOIN `{project_id}.silver_v2_claims.claim_state_history` h
            ON h.claim_id = c.claim_id
        WHERE h.history_id IS NULL
        """,
    ),
    (
        "Every claim with a subject has at least one claim_entity_link",
        """
        SELECT COUNT(*)
        FROM `{project_id}.silver_v2_claims.claim` c
        LEFT JOIN `{project_id}.silver_v2_claims.claim_entity_link` l
            ON l.claim_id = c.claim_id
        WHERE l.link_id IS NULL
          AND c.claim_subject_type IS NOT NULL
        """,
    ),
]


def run_all_checks(project_id: str) -> bool:
    """Run all verification checks. Returns True if all pass."""
    if bigquery is None:
        log.error(
            "google-cloud-bigquery is not installed. Run: pip install google-cloud-bigquery"
        )
        sys.exit(1)

    client = bigquery.Client(project=project_id)

    print(f"\nKnowledge Graph Migration Verification — project: {project_id}")
    print("=" * 70)

    results = []
    for check_name, query in CHECKS:
        passed = _run_check(client, project_id, check_name, query)
        results.append(passed)

    print("=" * 70)
    passed_count = sum(results)
    total = len(results)
    if all(results):
        print(f"ALL {total} CHECKS PASSED — Phase 2 migration verified.")
        return True
    else:
        failed = total - passed_count
        print(f"{failed}/{total} CHECKS FAILED — migration incomplete or has gaps.")
        return False


def main() -> None:
    backend = os.environ.get("DB_BACKEND", "bigquery").lower()
    if backend == "duckdb":
        db_path = os.environ.get("DUCKDB_PATH", str(_DEFAULT_DB_PATH))
        success = run_all_checks_duckdb(db_path)
    else:
        project_id = _require_env("GCP_PROJECT_ID")
        success = run_all_checks(project_id)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
