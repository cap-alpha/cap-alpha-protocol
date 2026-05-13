"""
apply_kg_schema.py — Phase 1 KG schema apply + idempotency check (issue #920).

Delegates to the general apply_migrations runner for *applying* migration 028
(028_kg_schema_additive.sql), but adds a dedicated ``--check`` mode that
verifies the schema is actually present in BigQuery and exits non-zero if any
expected table or column is missing.

Purpose
-------
- ``--apply``   Apply migration 028 (skips if already recorded in
                infra.applied_migrations).  Safe to re-run; idempotent.
- ``--check``   Query INFORMATION_SCHEMA to confirm every expected table and
                column from 028 is present.  Exits 0 = all present,
                1 = any missing.
- ``--dry-run`` Show which tables/columns would be checked, without connecting
                to BigQuery.

Usage
-----
    export GCP_PROJECT_ID=cap-alpha-protocol

    # Apply migration 028 (delegates to apply_migrations.py, skips if done)
    python pipeline/scripts/apply_kg_schema.py --apply

    # Verify the schema is live
    python pipeline/scripts/apply_kg_schema.py --check

    # Preview what would be checked (no BQ connection)
    python pipeline/scripts/apply_kg_schema.py --check --dry-run

Notes
-----
- The DDL lives in pipeline/migrations/028_kg_schema_additive.sql.
  PR #924 created that file; this script works with it.
- The general runner (apply_migrations.py) tracks ALL migrations via
  infra.applied_migrations; this script is a thin, focused wrapper for
  Phase 1 of issue #920.
"""

from __future__ import annotations

import argparse
import logging
import os
import pathlib
import sys
from typing import NamedTuple

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema expectations extracted from 028_kg_schema_additive.sql
# ---------------------------------------------------------------------------

# Tables that must exist after 028 is applied.
# Each tuple: (dataset, table, [required_columns])
class _TableSpec(NamedTuple):
    dataset: str
    table: str
    required_columns: list[str]


EXPECTED_TABLES: list[_TableSpec] = [
    _TableSpec(
        dataset="silver_v2_claims",
        table="claim_entity_link",
        required_columns=["link_id", "claim_id", "entity_id", "entity_role", "ordinal", "created_at"],
    ),
    _TableSpec(
        dataset="silver_v2_claims",
        table="claim_state_history",
        required_columns=[
            "history_id",
            "claim_id",
            "state",
            "effective_from",
            "effective_to",
            "effective_source",
            "resolution_id",
            "brier_score",
            "binary_correct",
            "notes",
            "created_at",
        ],
    ),
    _TableSpec(
        dataset="silver_v2_claims",
        table="entity_resolution_queue",
        required_columns=[
            "queue_id",
            "raw_entity_string",
            "normalized_string",
            "domain",
            "placeholder_entity_id",
            "first_seen_at",
            "last_attempted_at",
            "attempt_count",
            "status",
            "resolved_entity_id",
            "resolved_by",
            "resolved_at",
            "notes",
            "created_at",
        ],
    ),
]

# ADD COLUMN changes: (dataset, table, column) that must exist after 028.
EXPECTED_NEW_COLUMNS: list[tuple[str, str, str]] = [
    ("silver_v2_core", "entity_attribute_event", "value_entity_id"),
    ("silver_v2_claims", "claim", "legacy_prediction_hash"),
    ("silver_v2_claims", "claim", "legacy_chain_hash"),
]


# ---------------------------------------------------------------------------
# BigQuery connectivity (import-guarded so tests can mock)
# ---------------------------------------------------------------------------

try:
    from google.cloud import bigquery as _bq_module
    from google.api_core.exceptions import NotFound as _NotFound
except ImportError:  # pragma: no cover — package always present at runtime
    _bq_module = None  # type: ignore[assignment]
    _NotFound = Exception  # type: ignore[assignment,misc]


# ---------------------------------------------------------------------------
# Dry-run output
# ---------------------------------------------------------------------------


def _dry_run_check() -> None:
    """Print what would be checked without hitting BigQuery."""
    log.info("[DRY-RUN] Tables expected after migration 028:")
    for spec in EXPECTED_TABLES:
        log.info(
            "  TABLE  %s.%s  columns=%s",
            spec.dataset,
            spec.table,
            spec.required_columns,
        )
    log.info("[DRY-RUN] ADD COLUMN changes expected after migration 028:")
    for dataset, table, col in EXPECTED_NEW_COLUMNS:
        log.info("  COLUMN  %s.%s.%s", dataset, table, col)


# ---------------------------------------------------------------------------
# INFORMATION_SCHEMA helpers
# ---------------------------------------------------------------------------


def _query_columns(client, project_id: str, dataset: str, table: str) -> set[str]:
    """
    Return the set of column names for the given table from INFORMATION_SCHEMA.
    Returns empty set if the table or dataset does not exist.
    """
    sql = f"""
        SELECT column_name
        FROM `{project_id}.{dataset}.INFORMATION_SCHEMA.COLUMNS`
        WHERE table_name = '{table}'
    """
    try:
        rows = list(client.query(sql).result())
        return {r["column_name"] for r in rows}
    except Exception as exc:
        # Treat "not found" or "dataset does not exist" as empty
        err_str = str(exc).lower()
        if "not found" in err_str or "does not exist" in err_str:
            return set()
        raise


def _check_schema(client, project_id: str) -> bool:
    """
    Verify every expected table and column from migration 028 is present.

    Returns True if all checks pass, False if any are missing.
    Logs individual PASS / FAIL per check.
    """
    all_pass = True

    # --- Check tables (and their required columns) ---
    for spec in EXPECTED_TABLES:
        cols = _query_columns(client, project_id, spec.dataset, spec.table)
        table_fqn = f"{spec.dataset}.{spec.table}"
        if not cols:
            log.error("  FAIL  Table %s does not exist", table_fqn)
            all_pass = False
            continue

        log.info("  PASS  Table %s exists (%d column(s) found)", table_fqn, len(cols))
        for required_col in spec.required_columns:
            if required_col in cols:
                log.info("    PASS  column %s", required_col)
            else:
                log.error("    FAIL  column %s is missing from %s", required_col, table_fqn)
                all_pass = False

    # --- Check ADD COLUMN changes on existing tables ---
    for dataset, table, col in EXPECTED_NEW_COLUMNS:
        table_fqn = f"{dataset}.{table}"
        cols = _query_columns(client, project_id, dataset, table)
        if not cols:
            log.error(
                "  FAIL  Base table %s does not exist (cannot check column %s)",
                table_fqn,
                col,
            )
            all_pass = False
            continue
        if col in cols:
            log.info("  PASS  %s.%s column exists", table_fqn, col)
        else:
            log.error("  FAIL  %s.%s column is missing", table_fqn, col)
            all_pass = False

    return all_pass


# ---------------------------------------------------------------------------
# Apply wrapper
# ---------------------------------------------------------------------------

# Resolve path relative to this file so it works regardless of CWD.
_SCRIPTS_DIR = pathlib.Path(__file__).parent
_MIGRATION_FILE = _SCRIPTS_DIR.parent / "migrations" / "028_kg_schema_additive.sql"
_MIGRATION_ID = "028_kg_schema_additive.sql"


def _apply(dry_run: bool = False) -> None:
    """
    Delegate to apply_migrations.py, filtered to migration 028.

    We invoke the function directly (not subprocess) so the caller gets proper
    Python-level exceptions and the same logging format.
    """
    # Ensure scripts/ is importable
    _scripts_str = str(_SCRIPTS_DIR)
    if _scripts_str not in sys.path:
        sys.path.insert(0, _scripts_str)

    from apply_migrations import apply_migrations as _runner

    log.info(
        "Applying migration %s (028_kg_schema_additive.sql)%s",
        _MIGRATION_ID,
        " [DRY-RUN]" if dry_run else "",
    )
    if not _MIGRATION_FILE.exists():
        log.error(
            "Migration file not found: %s  "
            "(expected alongside phase2 scripts from PR #924)",
            _MIGRATION_FILE,
        )
        sys.exit(1)

    # The general runner applies ALL pending migrations in order. Migration 028
    # will be skipped if already applied (SHA-tracked). Earlier pending migrations
    # (if any) will also be applied — this is intentional; 028 cannot be applied
    # before its predecessors.
    _runner(dry_run=dry_run)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Phase 1 KG schema apply + check script for migration 028 (issue #920). "
            "Use --apply to run the migration runner, --check to verify the schema."
        )
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Apply migration 028_kg_schema_additive.sql via apply_migrations.py",
    )
    mode.add_argument(
        "--check",
        action="store_true",
        help="Verify that all tables/columns from migration 028 exist in BigQuery",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Preview without executing. "
            "With --apply: show which migrations would run. "
            "With --check: list expected tables/columns without querying BQ."
        ),
    )
    args = parser.parse_args()

    if args.apply:
        _apply(dry_run=args.dry_run)
        return

    # --check mode
    if args.dry_run:
        _dry_run_check()
        return

    project_id = os.environ.get("GCP_PROJECT_ID")
    if not project_id:
        log.error("GCP_PROJECT_ID environment variable is not set.")
        sys.exit(1)

    if _bq_module is None:
        log.error("google-cloud-bigquery is not installed.")
        sys.exit(1)

    client = _bq_module.Client(project=project_id)
    log.info("Checking KG schema (migration 028) against project %s …", project_id)

    ok = _check_schema(client, project_id)

    if ok:
        log.info("Schema check PASSED — all tables and columns from 028 are present.")
        sys.exit(0)
    else:
        log.error("Schema check FAILED — one or more expected tables/columns are missing.")
        sys.exit(1)


if __name__ == "__main__":
    main()
