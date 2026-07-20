"""
apply_migrations.py — Idempotent migration runner for BigQuery.

Scans pipeline/migrations/*.sql sorted by numeric prefix, checks a
tracking table (infra.applied_migrations) to skip already-applied
migrations, and applies pending ones.

Features:
- Auto-bootstraps infra dataset + applied_migrations table on first run
- SHA-256 tracking prevents silent re-application of changed migrations
- --dry-run flag to preview pending migrations without executing
- --mark-applied flag to bootstrap tracking for existing production DB
- GITHUB_SHA env var recorded with each applied migration for traceability
- Backfill declaration enforcement: any migration that creates a table must
  include a ``-- backfill:`` header in the first 10 lines declaring the data
  migration plan (e.g. ``-- backfill: issue #874`` or ``-- backfill: none``).
  A WARNING is logged if this header is missing.

Backfill header format (first 10 lines of the SQL file)::

    -- backfill: issue #874
    -- backfill: none
    -- backfill: not needed
    CREATE TABLE IF NOT EXISTS ...

Usage:
    python pipeline/scripts/apply_migrations.py              # apply pending
    python pipeline/scripts/apply_migrations.py --dry-run    # preview only
    python pipeline/scripts/apply_migrations.py --mark-applied  # mark all as applied
"""

from __future__ import annotations

import argparse
import hashlib
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

# Top-level import so tests can patch 'apply_migrations.bigquery'.
# The google-cloud-bigquery package is a required runtime dependency;
# the import will only fail if the package is not installed.
try:
    from google.cloud import bigquery
    from google.api_core.exceptions import Conflict, NotFound
except ImportError:  # pragma: no cover — package always present at runtime
    bigquery = None  # type: ignore[assignment]
    Conflict = Exception  # type: ignore[assignment,misc]
    NotFound = Exception  # type: ignore[assignment,misc]

MIGRATIONS_DIR = pathlib.Path(__file__).parent.parent / "migrations"

# DDL for the tracking table. infra dataset is created inline if missing.
_TRACKING_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS `{project_id}.infra.applied_migrations` (
    migration_id STRING NOT NULL,
    sha256       STRING NOT NULL,
    applied_at   TIMESTAMP NOT NULL,
    git_sha      STRING
)
""".strip()


# ---------------------------------------------------------------------------
# SQL utilities
# ---------------------------------------------------------------------------


def _parse_backfill_declaration(content: str) -> str | None:
    """
    Scan the first 10 lines of a SQL file for a ``-- backfill: <value>`` header.

    Returns the declared value (e.g. ``"issue #874"``, ``"none"``) or ``None``
    if no backfill header is present.  The prefix match is case-insensitive.

    Example headers::

        -- backfill: issue #874
        -- backfill: none
        -- backfill: not needed
    """
    for line in content.splitlines()[:10]:
        m = re.match(r"--\s*backfill\s*:\s*(.+)", line, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return None


def _creates_table(content: str) -> bool:
    """
    Return True if *content* contains a CREATE TABLE or CREATE OR REPLACE TABLE
    statement (case-insensitive).
    """
    return bool(re.search(r"CREATE\s+(OR\s+REPLACE\s+)?TABLE", content, re.IGNORECASE))


def _split_statements(sql: str) -> list[str]:
    """
    Split a SQL file into individual statements on semicolons.

    Strips line comments first, then splits on semicolons that are NOT inside
    single-quoted or double-quoted string literals. BigQuery OPTIONS(description="...")
    clauses commonly contain semicolons which must not be treated as statement
    delimiters.
    """
    # Strip line comments. Safe because our migration descriptions don't contain --.
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


def _sha256(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Migration discovery
# ---------------------------------------------------------------------------


def _discover_migrations() -> list[pathlib.Path]:
    """
    Return migration files from MIGRATIONS_DIR sorted by numeric prefix.

    Files must match the pattern: NNN_<name>.sql where NNN is one or more
    digits. Files without a leading numeric prefix are ignored.
    """
    pattern = re.compile(r"^(\d+)_.*\.sql$")
    files = []
    for f in MIGRATIONS_DIR.iterdir():
        if pattern.match(f.name):
            files.append(f)
    return sorted(files, key=lambda f: int(pattern.match(f.name).group(1)))


# ---------------------------------------------------------------------------
# BigQuery bootstrap + tracking helpers
# ---------------------------------------------------------------------------


def _ensure_infra_dataset(client, project_id: str) -> None:
    """Create the infra dataset if it does not exist."""
    dataset_id = f"{project_id}.infra"
    dataset = bigquery.Dataset(dataset_id)
    dataset.location = "US"
    try:
        client.create_dataset(dataset, exists_ok=True)
        log.debug("infra dataset ready.")
    except Conflict:
        pass  # already exists — fine


def _ensure_tracking_table(client, project_id: str) -> None:
    """Create infra.applied_migrations if it doesn't exist."""
    _ensure_infra_dataset(client, project_id)
    ddl = _TRACKING_TABLE_DDL.format(project_id=project_id)
    log.debug("Ensuring tracking table exists…")
    job = client.query(ddl)
    try:
        job.result()
    except Exception as exc:
        _reraise_with_billing_hint(exc, project_id)
    log.debug("Tracking table ready.")


def _reraise_with_billing_hint(exc: Exception, project_id: str) -> None:
    """
    Re-raise *exc* as-is, but first log an actionable hint if it looks like
    the classic "GCP billing unlinked" failure mode.

    This project has been paused/resumed for cost reasons before (see
    issue #1107) via ``gcloud billing projects unlink``. When that happens,
    every BigQuery DDL call fails with a 403 Forbidden /
    ``billingNotEnabled`` error and BigQuery falls back to free-tier
    "sandbox mode" (which also rejects unbounded table expirations). That
    error surfaces here — at the very first query the runner makes — and
    without this hint it reads as an opaque migration-runner bug instead of
    an infra/billing state problem.
    """
    err_str = str(exc)
    if "billingNotEnabled" in err_str or "Billing has not been enabled" in err_str:
        log.error(
            "  BILLING DISABLED for project '%s' — BigQuery is refusing DDL "
            "because no billing account is linked (this project has been "
            "paused/resumed for cost reasons before, see issue #1107). "
            "This is NOT a migration-file bug. Fix: "
            "`gcloud billing projects describe %s` to confirm, then "
            "`gcloud billing projects link %s --billing-account=<ACCOUNT_ID>` "
            "or re-link via https://console.cloud.google.com/billing — then "
            "re-run this step.",
            project_id,
            project_id,
            project_id,
        )
    raise exc


def _load_applied(client, project_id: str) -> dict[str, str]:
    """
    Return {migration_id: sha256} for all rows in infra.applied_migrations.
    Returns {} if the table doesn't exist yet (bootstrap case).
    """
    query = f"""
        SELECT migration_id, sha256
        FROM `{project_id}.infra.applied_migrations`
    """
    try:
        rows = list(client.query(query).result())
        return {r["migration_id"]: r["sha256"] for r in rows}
    except NotFound:
        return {}


def _record_applied(
    client, project_id: str, migration_id: str, sha: str, git_sha: str
) -> None:
    """Insert a tracking row for a successfully applied migration."""
    query = f"""
        INSERT INTO `{project_id}.infra.applied_migrations`
            (migration_id, sha256, applied_at, git_sha)
        VALUES
            ('{migration_id}', '{sha}', CURRENT_TIMESTAMP(), '{git_sha}')
    """
    job = client.query(query)
    job.result()


# ---------------------------------------------------------------------------
# Core runner
# ---------------------------------------------------------------------------


def apply_migrations(dry_run: bool = False, mark_applied: bool = False) -> None:
    project_id = os.environ.get("GCP_PROJECT_ID")
    if not project_id:
        log.error("GCP_PROJECT_ID environment variable is not set.")
        sys.exit(1)

    git_sha = os.environ.get("GITHUB_SHA", "local")
    log.info("Target BigQuery project: %s", project_id)
    log.info("Git SHA: %s", git_sha)

    files = _discover_migrations()
    if not files:
        log.warning("No migration files found in %s", MIGRATIONS_DIR)
        return

    log.info("Discovered %d migration file(s).", len(files))

    if dry_run:
        log.info("[DRY-RUN] Skipping BigQuery connection — listing pending migrations.")
        for f in files:
            content = f.read_text()
            sha = _sha256(content)
            creates = _creates_table(content)
            backfill = _parse_backfill_declaration(content) if creates else None
            if creates and backfill is None:
                backfill_str = " [BACKFILL UNDECLARED]"
            elif backfill:
                backfill_str = f" [backfill: {backfill}]"
            else:
                backfill_str = ""
            log.info("  [DRY-RUN] %s  sha256=%s%s", f.name, sha[:12], backfill_str)
        return

    client = bigquery.Client(project=project_id)

    # Bootstrap tracking table (no-op if already exists)
    _ensure_tracking_table(client, project_id)

    applied = _load_applied(client, project_id)
    log.info("Already applied: %d migration(s).", len(applied))

    total_applied = 0
    total_skipped = 0

    for migration_path in files:
        migration_id = migration_path.name
        content = migration_path.read_text()
        sha = _sha256(content)

        if migration_id in applied:
            existing_sha = applied[migration_id]
            if existing_sha == sha:
                log.info("  SKIP  %s (already applied, SHA matches)", migration_id)
                total_skipped += 1
                continue
            else:
                log.error(
                    "  ERROR  %s is already applied with SHA %s but the file "
                    "now has SHA %s — refusing to apply a changed migration. "
                    "Create a new migration file instead.",
                    migration_id,
                    existing_sha[:12],
                    sha[:12],
                )
                sys.exit(1)

        if mark_applied:
            log.info(
                "  MARK-APPLIED  %s  sha256=%s",
                migration_id,
                sha[:12],
            )
            _record_applied(client, project_id, migration_id, sha, git_sha)
            total_applied += 1
            continue

        # Apply the migration — normalize all project_id template variants.
        # Some SQL files use shell-style ${PROJECT_ID} / ${project_id} instead of
        # Python-style {project_id}; handle all three to avoid BigQuery 400 errors.
        sql = content
        sql = sql.replace("${PROJECT_ID}", project_id)
        sql = sql.replace("${project_id}", project_id)
        sql = sql.replace("{project_id}", project_id)
        statements = _split_statements(sql)
        log.info(
            "  APPLY  %s  (%d statement(s), sha256=%s)",
            migration_id,
            len(statements),
            sha[:12],
        )

        for i, stmt in enumerate(statements, start=1):
            preview = stmt[:120].replace("\n", " ")
            try:
                log.info("    [%d/%d] %s …", i, len(statements), preview)
                job = client.query(stmt)
                job.result()
                log.info("    OK (job_id=%s)", job.job_id)
            except Exception as exc:
                err_str = str(exc).lower()
                if "already exists" in err_str:
                    log.info("    SKIP (already exists): %s", str(exc)[:200])
                else:
                    log.error("    FAILED: %s", exc)
                    raise

        _record_applied(client, project_id, migration_id, sha, git_sha)
        log.info("  RECORDED  %s", migration_id)

        if _creates_table(content):
            backfill = _parse_backfill_declaration(content)
            if backfill is None:
                log.warning(
                    "  BACKFILL UNDECLARED  %s creates a table but has no "
                    "'-- backfill: <issue #NNN | none>' header. "
                    "Add one to declare the data migration plan.",
                    migration_id,
                )
            else:
                log.info("  BACKFILL  %s declared: %s", migration_id, backfill)

        total_applied += 1

    action = "marked-applied" if mark_applied else "applied"
    log.info(
        "Done. %d migration(s) %s, %d skipped.",
        total_applied,
        action,
        total_skipped,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Idempotent BigQuery migration runner")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print which migrations would run without executing them",
    )
    parser.add_argument(
        "--mark-applied",
        action="store_true",
        help=(
            "Mark all existing migration files as applied without executing "
            "their SQL. Use this once to bootstrap tracking on an existing "
            "production database."
        ),
    )
    args = parser.parse_args()

    if args.dry_run and args.mark_applied:
        parser.error("--dry-run and --mark-applied are mutually exclusive.")

    apply_migrations(dry_run=args.dry_run, mark_applied=args.mark_applied)


if __name__ == "__main__":
    main()
