"""
apply_kg_schema.py — Phase 1 KG schema migration runner.
Issue #920 — silver_v2 temporal knowledge graph upgrade.

Applies pipeline/migrations/028_kg_schema_additive.sql idempotently, then
runs Phase 1 verification queries to confirm each new table/column exists
with the expected shape.

Features:
  - Sources GCP_PROJECT_ID from environment (or .env via dotenv if available)
  - Each DDL statement is safe to re-run (CREATE TABLE IF NOT EXISTS / ADD COLUMN IF NOT EXISTS)
  - Prints a summary of created / already-existing objects
  - Exits non-zero on any unexpected failure

Usage:
    source .env && python3 pipeline/scripts/apply_kg_schema.py
    python3 pipeline/scripts/apply_kg_schema.py --dry-run
"""

from __future__ import annotations

import argparse
import logging
import os
import pathlib
import re
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

MIGRATION_FILE = (
    pathlib.Path(__file__).parent.parent / "migrations" / "028_kg_schema_additive.sql"
)

# Expected objects after Phase 1 migration.
# Each entry: (dataset, object_name, object_type, expected_columns_subset)
EXPECTED_OBJECTS: list[tuple[str, str, str, list[str]]] = [
    (
        "silver_v2_claims",
        "claim_entity_link",
        "TABLE",
        ["link_id", "claim_id", "entity_id", "entity_role", "ordinal", "created_at"],
    ),
    (
        "silver_v2_claims",
        "entity_resolution_queue",
        "TABLE",
        [
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
    (
        "silver_v2_claims",
        "claim_state_history",
        "TABLE",
        [
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
]

# Columns expected to exist on existing tables after the ALTER TABLE statements.
EXPECTED_ALTER_COLUMNS: list[tuple[str, str, str]] = [
    # (dataset, table, column)
    ("silver_v2_core", "entity_attribute_event", "value_entity_id"),
    ("silver_v2_claims", "claim", "legacy_prediction_hash"),
    ("silver_v2_claims", "claim", "legacy_chain_hash"),
]


# ---------------------------------------------------------------------------
# SQL helpers
# ---------------------------------------------------------------------------


def _split_statements(sql: str) -> list[str]:
    """Split SQL on top-level semicolons, skipping those inside string literals."""
    # Remove line comments before parsing
    stripped = re.sub(r"--[^\n]*", "", sql)

    parts: list[str] = []
    current: list[str] = []
    in_single = False
    in_double = False

    for ch in stripped:
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == ";" and not in_single and not in_double:
            stmt = "".join(current).strip()
            if stmt:
                parts.append(stmt)
            current = []
            continue
        current.append(ch)

    remainder = "".join(current).strip()
    if remainder:
        parts.append(remainder)
    return parts


# ---------------------------------------------------------------------------
# BigQuery helpers
# ---------------------------------------------------------------------------


def _get_client(project_id: str):
    try:
        from google.cloud import bigquery  # type: ignore[import-untyped]

        return bigquery.Client(project=project_id)
    except ImportError:
        log.error("google-cloud-bigquery is not installed. Run: pip install google-cloud-bigquery")
        sys.exit(1)


def _apply_statements(client, project_id: str, statements: list[str]) -> dict[str, str]:
    """
    Execute each statement.  Returns a dict mapping a short label to the outcome:
    'applied' | 'already_exists' | 'error:<msg>'
    """
    results: dict[str, str] = {}
    for i, stmt in enumerate(statements, start=1):
        label = _extract_object_label(stmt, i)
        preview = stmt[:100].replace("\n", " ")
        log.info("  [%d/%d] %s …", i, len(statements), preview)
        try:
            job = client.query(stmt)
            job.result()
            log.info("    OK — %s (job_id=%s)", label, job.job_id)
            results[label] = "applied"
        except Exception as exc:
            err_str = str(exc).lower()
            if "already exists" in err_str or "duplicate" in err_str:
                log.info("    SKIP (already exists): %s", label)
                results[label] = "already_exists"
            else:
                log.error("    FAILED [%s]: %s", label, exc)
                results[label] = f"error:{exc}"
    return results


def _extract_object_label(stmt: str, fallback_idx: int) -> str:
    """Extract a human-readable label from a DDL statement."""
    # CREATE TABLE IF NOT EXISTS `proj.dataset.table`
    m = re.search(
        r"CREATE\s+(?:OR\s+REPLACE\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?`[^.]+\.([^.]+)\.([^`]+)`",
        stmt,
        re.IGNORECASE,
    )
    if m:
        return f"{m.group(1)}.{m.group(2)}"
    # ALTER TABLE `proj.dataset.table` ADD COLUMN IF NOT EXISTS col
    m = re.search(
        r"ALTER\s+TABLE\s+`[^.]+\.([^.]+)\.([^`]+)`.*ADD\s+COLUMN.*?(\w+)\s+STRING",
        stmt,
        re.IGNORECASE | re.DOTALL,
    )
    if m:
        return f"{m.group(1)}.{m.group(2)} +col:{m.group(3)}"
    return f"stmt_{fallback_idx}"


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


def _verify_tables(client, project_id: str) -> list[str]:
    """
    Query INFORMATION_SCHEMA to confirm each expected table and column exists.
    Returns a list of failure messages; empty = all good.
    """
    failures: list[str] = []

    for dataset, table, obj_type, expected_cols in EXPECTED_OBJECTS:
        # Check table exists
        exists_q = f"""
            SELECT COUNT(*) AS cnt
            FROM `{project_id}.{dataset}.INFORMATION_SCHEMA.TABLES`
            WHERE table_name = '{table}'
              AND table_type = 'BASE TABLE'
        """
        try:
            rows = list(client.query(exists_q).result())
            cnt = rows[0]["cnt"] if rows else 0
            if cnt == 0:
                failures.append(f"MISSING TABLE: {dataset}.{table}")
                continue
            log.info("  VERIFIED TABLE EXISTS: %s.%s", dataset, table)
        except Exception as exc:
            failures.append(f"ERROR checking {dataset}.{table}: {exc}")
            continue

        # Check columns
        cols_q = f"""
            SELECT column_name
            FROM `{project_id}.{dataset}.INFORMATION_SCHEMA.COLUMNS`
            WHERE table_name = '{table}'
        """
        try:
            col_rows = list(client.query(cols_q).result())
            actual_cols = {r["column_name"] for r in col_rows}
            missing_cols = [c for c in expected_cols if c not in actual_cols]
            if missing_cols:
                failures.append(
                    f"MISSING COLUMNS on {dataset}.{table}: {missing_cols}"
                )
            else:
                log.info(
                    "  VERIFIED COLUMNS on %s.%s: %s",
                    dataset,
                    table,
                    ", ".join(expected_cols),
                )
        except Exception as exc:
            failures.append(f"ERROR checking columns on {dataset}.{table}: {exc}")

    return failures


def _verify_alter_columns(client, project_id: str) -> list[str]:
    """
    Verify that ALTER TABLE ADD COLUMN statements resulted in columns existing.
    Returns a list of failure messages.
    """
    failures: list[str] = []
    for dataset, table, column in EXPECTED_ALTER_COLUMNS:
        col_q = f"""
            SELECT COUNT(*) AS cnt
            FROM `{project_id}.{dataset}.INFORMATION_SCHEMA.COLUMNS`
            WHERE table_name = '{table}'
              AND column_name = '{column}'
        """
        try:
            rows = list(client.query(col_q).result())
            cnt = rows[0]["cnt"] if rows else 0
            if cnt == 0:
                failures.append(f"MISSING COLUMN: {dataset}.{table}.{column}")
            else:
                log.info("  VERIFIED COLUMN: %s.%s.%s", dataset, table, column)
        except Exception as exc:
            failures.append(f"ERROR checking {dataset}.{table}.{column}: {exc}")
    return failures


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def _load_dotenv_if_available() -> None:
    """Load .env file from repo root if python-dotenv is installed."""
    try:
        from dotenv import load_dotenv  # type: ignore[import-untyped]

        repo_root = pathlib.Path(__file__).parent.parent.parent
        env_file = repo_root / ".env"
        if env_file.exists():
            load_dotenv(env_file)
            log.debug("Loaded .env from %s", env_file)
    except ImportError:
        pass


def _verify_tables_duckdb(db) -> list[str]:
    """
    Verify Phase 1 schema against a DuckDB backend.

    Uses INFORMATION_SCHEMA queries that work in DuckDB (no project prefix).
    Returns a list of failure messages; empty = all good.
    """
    failures: list[str] = []

    for dataset, table, _obj_type, expected_cols in EXPECTED_OBJECTS:
        # Check columns exist (DuckDB INFORMATION_SCHEMA uses schema/table_name)
        try:
            cols_df = db.fetch_df(
                f"SELECT column_name FROM information_schema.columns "
                f"WHERE table_schema = '{dataset}' AND table_name = '{table}'"
            )
            actual_cols = set(cols_df["column_name"].tolist()) if not cols_df.empty else set()
        except Exception as exc:
            failures.append(f"ERROR checking {dataset}.{table}: {exc}")
            continue

        if not actual_cols:
            failures.append(f"MISSING TABLE: {dataset}.{table}")
            continue

        missing_cols = [c for c in expected_cols if c not in actual_cols]
        if missing_cols:
            failures.append(f"MISSING COLUMNS on {dataset}.{table}: {missing_cols}")
            log.error("  FAIL  %s.%s — missing columns: %s", dataset, table, missing_cols)
        else:
            log.info(
                "  PASS  %s.%s — %d required column(s) present",
                dataset, table, len(expected_cols),
            )

    for dataset, table, column in EXPECTED_ALTER_COLUMNS:
        try:
            cols_df = db.fetch_df(
                f"SELECT column_name FROM information_schema.columns "
                f"WHERE table_schema = '{dataset}' AND table_name = '{table}'"
                f"  AND column_name = '{column}'"
            )
            if cols_df.empty:
                failures.append(f"MISSING COLUMN: {dataset}.{table}.{column}")
                log.error("  FAIL  %s.%s.%s — column not found", dataset, table, column)
            else:
                log.info("  PASS  %s.%s.%s — column present", dataset, table, column)
        except Exception as exc:
            failures.append(f"ERROR checking {dataset}.{table}.{column}: {exc}")

    return failures


def _run_check_duckdb() -> None:
    """
    Read-only verification of Phase 1 KG schema against DuckDB (DB_BACKEND=duckdb).

    Invoked by --check when DB_BACKEND=duckdb (or when GCP_PROJECT_ID is absent).
    """
    # Allow pipeline/src to be importable regardless of CWD.
    # db_manager.py uses `from src.duckdb_manager import ...` which requires
    # the *pipeline* directory (parent of src/) to be on sys.path.
    pipeline_dir = pathlib.Path(__file__).parent.parent
    if str(pipeline_dir) not in sys.path:
        sys.path.insert(0, str(pipeline_dir))

    try:
        from src.db_manager import get_db_manager  # type: ignore[import-untyped]
    except ImportError:
        log.error("Cannot import get_db_manager from pipeline/src/db_manager.py")
        sys.exit(1)

    db = get_db_manager()
    log.info("DuckDB verification — path: %s", getattr(db, "_db_path", "unknown"))
    log.info("")
    log.info("--- Phase 1 verification (DuckDB) ---")

    failures = _verify_tables_duckdb(db)

    if failures:
        log.error("VERIFICATION FAILED — %d issue(s):", len(failures))
        for f in failures:
            log.error("  %s", f)
        sys.exit(1)

    log.info("")
    log.info("=== Phase 1 verification PASSED (DuckDB) ===")
    log.info("  Tables confirmed: claim_entity_link, entity_resolution_queue, claim_state_history")
    log.info("  Columns confirmed: entity_attribute_event.value_entity_id")
    log.info("  Columns confirmed: claim.legacy_prediction_hash, claim.legacy_chain_hash")


def main(dry_run: bool = False, check: bool = False) -> None:
    _load_dotenv_if_available()

    # --check with DB_BACKEND=duckdb uses the local DuckDB file (no GCP creds needed)
    if check and os.environ.get("DB_BACKEND", "").lower() == "duckdb":
        _run_check_duckdb()
        return

    project_id = os.environ.get("GCP_PROJECT_ID")
    if not project_id:
        if check:
            log.error(
                "GCP_PROJECT_ID not set and DB_BACKEND != duckdb.  "
                "For DuckDB: DB_BACKEND=duckdb python3 pipeline/scripts/apply_kg_schema.py --check"
            )
        else:
            log.error(
                "GCP_PROJECT_ID is not set. Run: source .env && python3 pipeline/scripts/apply_kg_schema.py"
            )
        sys.exit(1)

    log.info("Phase 1 KG schema migration — project: %s", project_id)
    log.info("Migration file: %s", MIGRATION_FILE)

    if not MIGRATION_FILE.exists():
        log.error("Migration file not found: %s", MIGRATION_FILE)
        sys.exit(1)

    sql = MIGRATION_FILE.read_text()
    sql = sql.replace("{project_id}", project_id)
    statements = _split_statements(sql)

    log.info("Parsed %d statement(s) from migration file.", len(statements))

    if dry_run:
        log.info("[DRY-RUN] Statements that would be executed:")
        for i, stmt in enumerate(statements, start=1):
            preview = stmt[:120].replace("\n", " ")
            log.info("  [%d] %s …", i, preview)
        log.info("[DRY-RUN] Skipping execution and verification.")
        return

    client = _get_client(project_id)

    # Apply migration
    log.info("--- Applying migration statements ---")
    results = _apply_statements(client, project_id, statements)

    applied_count = sum(1 for v in results.values() if v == "applied")
    skipped_count = sum(1 for v in results.values() if v == "already_exists")
    error_count = sum(1 for v in results.values() if v.startswith("error:"))

    log.info("")
    log.info("=== Migration summary ===")
    log.info("  Applied:       %d", applied_count)
    log.info("  Already exist: %d", skipped_count)
    log.info("  Errors:        %d", error_count)

    if error_count > 0:
        log.error("Migration had %d error(s). Stopping before verification.", error_count)
        for label, outcome in results.items():
            if outcome.startswith("error:"):
                log.error("  %s: %s", label, outcome)
        sys.exit(1)

    # Phase 1 verification
    log.info("")
    log.info("--- Phase 1 verification ---")
    table_failures = _verify_tables(client, project_id)
    col_failures = _verify_alter_columns(client, project_id)
    all_failures = table_failures + col_failures

    if all_failures:
        log.error("VERIFICATION FAILED — %d issue(s):", len(all_failures))
        for f in all_failures:
            log.error("  %s", f)
        sys.exit(1)

    log.info("")
    log.info("=== Phase 1 verification PASSED ===")
    log.info("  New tables confirmed: claim_entity_link, entity_resolution_queue, claim_state_history")
    log.info("  New columns confirmed: entity_attribute_event.value_entity_id")
    log.info("  New columns confirmed: claim.legacy_prediction_hash, claim.legacy_chain_hash")
    log.info("")
    log.info("Phase 1 complete. Proceed to Phase 2 (legacy gold_layer backfill).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Apply Phase 1 KG schema migration (028_kg_schema_additive.sql) and verify."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the statements that would run without executing them.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "Read-only verification: confirm migration 028 was fully applied. "
            "Use DB_BACKEND=duckdb for local DuckDB (no GCP creds needed). "
            "Example: DB_BACKEND=duckdb python3 pipeline/scripts/apply_kg_schema.py --check"
        ),
    )
    args = parser.parse_args()
    main(dry_run=args.dry_run, check=args.check)
