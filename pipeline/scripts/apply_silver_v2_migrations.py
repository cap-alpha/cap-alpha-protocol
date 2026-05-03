"""
apply_silver_v2_migrations.py — Phase B-1 migration runner for silver_v2_* DDL.

Reads migrations 015, 016, 017 and applies them to BigQuery, substituting
{project_id} with the GCP_PROJECT_ID environment variable.

Usage:
    python pipeline/scripts/apply_silver_v2_migrations.py            # apply all
    python pipeline/scripts/apply_silver_v2_migrations.py --dry-run  # print SQL only

Idempotent: all tables use CREATE TABLE IF NOT EXISTS; views use CREATE OR REPLACE.
"""

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

MIGRATION_FILES = [
    "015_create_silver_v2_core.sql",
    "016_create_silver_v2_claims.sql",
    "017_create_silver_v2_sports.sql",
]

MIGRATIONS_DIR = pathlib.Path(__file__).parent.parent / "migrations"


def _split_statements(sql: str) -> list[str]:
    """
    Split a SQL file into individual statements on semicolons, preserving
    statement bodies. Quote-aware: tracks single and double quotes, handles
    escape sequences (\' and \"), and only splits on ; when NOT in a string.
    Empty/whitespace-only results are skipped.
    """
    # Strip SQL line comments so we don't split on semicolons inside comments.
    stripped = re.sub(r"--[^\n]*", "", sql)

    statements = []
    current = []
    in_single_quote = False
    in_double_quote = False
    i = 0

    while i < len(stripped):
        char = stripped[i]

        # Handle escape sequences
        if i + 1 < len(stripped) and char == "\\":
            next_char = stripped[i + 1]
            if next_char in ("'", '"', "\\"):
                current.append(char)
                current.append(next_char)
                i += 2
                continue

        # Track quote state
        if char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
            current.append(char)
        elif char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
            current.append(char)
        # Split on semicolon only when not in quotes
        elif char == ";" and not in_single_quote and not in_double_quote:
            stmt = "".join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []
        else:
            current.append(char)

        i += 1

    # Append any remaining statement
    stmt = "".join(current).strip()
    if stmt:
        statements.append(stmt)

    return statements


def _load_migration(filename: str, project_id: str) -> str:
    """Read a migration file and substitute {project_id}."""
    path = MIGRATIONS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Migration file not found: {path}")
    sql = path.read_text()
    return sql.replace("{project_id}", project_id)


def apply_migrations(dry_run: bool = False) -> None:
    project_id = os.environ.get("GCP_PROJECT_ID")
    if not project_id:
        log.error("GCP_PROJECT_ID environment variable is not set.")
        sys.exit(1)

    log.info("Target BigQuery project: %s", project_id)

    if not dry_run:
        from google.cloud import bigquery  # noqa: PLC0415

        client = bigquery.Client(project=project_id)
    else:
        client = None  # type: ignore[assignment]

    total_ok = 0
    total_skip = 0

    for filename in MIGRATION_FILES:
        log.info("=== Processing %s ===", filename)
        sql = _load_migration(filename, project_id)
        statements = _split_statements(sql)
        log.info("  Found %d statement(s)", len(statements))

        for i, stmt in enumerate(statements, start=1):
            # Truncate for log readability
            preview = stmt[:120].replace("\n", " ")
            if dry_run:
                log.info(
                    "  [DRY-RUN] Statement %d/%d: %s ...", i, len(statements), preview
                )
                total_skip += 1
                continue

            try:
                log.info(
                    "  Executing statement %d/%d: %s ...", i, len(statements), preview
                )
                job = client.query(stmt)  # type: ignore[union-attr]
                job.result()  # wait for completion
                log.info("    OK (job_id=%s)", job.job_id)
                total_ok += 1
            except Exception as exc:
                # Tolerate "already exists" errors for tables/views — BigQuery
                # CREATE TABLE IF NOT EXISTS is idempotent but some statements
                # (e.g. views) may raise on duplicate names in older client versions.
                err_str = str(exc).lower()
                if "already exists" in err_str:
                    log.info("    SKIPPED (already exists): %s", str(exc)[:200])
                    total_skip += 1
                else:
                    log.error("    FAILED: %s", exc)
                    raise

    if dry_run:
        log.info("DRY-RUN complete. %d statement(s) would be executed.", total_skip)
    else:
        log.info(
            "Migration complete. %d statement(s) executed, %d skipped (already exist).",
            total_ok,
            total_skip,
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply silver_v2_* DDL migrations to BigQuery"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print SQL statements without executing them",
    )
    args = parser.parse_args()
    apply_migrations(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
