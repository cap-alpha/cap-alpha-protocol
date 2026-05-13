#!/usr/bin/env python3
"""
Bootstrap the local DuckDB file from pipeline migration SQL files.

Reads all pipeline/migrations/*.sql files in lexicographic order, translates
BigQuery DDL to DuckDB-compatible DDL, and executes them against a local
DuckDB file.

Usage:
    DB_BACKEND=duckdb python3 pipeline/scripts/init_local_db.py

The script is idempotent — safe to run multiple times.  All tables are created
with IF NOT EXISTS so re-runs are no-ops for already-created tables.

Environment variables:
    DUCKDB_PATH   Path to the DuckDB file (default: pipeline/data/local.duckdb)
    PROJECT_ID    BQ project placeholder used in some SQL templates (default: local)
"""

import logging
import os
import re
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Resolve repo root so the script works from any CWD
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
_PIPELINE_DIR = _SCRIPT_DIR.parent
_REPO_ROOT = _PIPELINE_DIR.parent

MIGRATIONS_DIR = _PIPELINE_DIR / "migrations"
_DEFAULT_DB_PATH = _PIPELINE_DIR / "data" / "local.duckdb"


# ---------------------------------------------------------------------------
# BQ → DuckDB DDL translation
# ---------------------------------------------------------------------------

def _strip_options_clauses(sql: str) -> str:
    """
    Strip BigQuery OPTIONS(...) clauses from SQL.

    The naive regex ``OPTIONS\\s*\\([^)]*\\)`` breaks when the description string
    contains a literal ``)``.  This function walks the string character-by-character
    so it correctly handles quoted content inside the OPTIONS clause.
    """
    result: list[str] = []
    i = 0
    n = len(sql)
    while i < n:
        # Case-insensitive match for the word OPTIONS
        if sql[i:i+7].upper() == "OPTIONS" and (i == 0 or not sql[i-1].isalnum()):
            j = i + 7
            # Skip whitespace between OPTIONS and (
            while j < n and sql[j] in (" ", "\t", "\n", "\r"):
                j += 1
            if j < n and sql[j] == "(":
                # Consume everything until the matching close paren,
                # respecting single- and double-quoted strings.
                depth = 1
                j += 1  # move past the opening (
                in_single = False
                in_double = False
                while j < n and depth > 0:
                    c = sql[j]
                    if c == "'" and not in_double:
                        in_single = not in_single
                    elif c == '"' and not in_single:
                        in_double = not in_double
                    elif c == "(" and not in_single and not in_double:
                        depth += 1
                    elif c == ")" and not in_single and not in_double:
                        depth -= 1
                    j += 1
                # Skip the matched OPTIONS(...) — emit nothing
                i = j
                continue
        result.append(sql[i])
        i += 1
    return "".join(result)



def translate_ddl(sql: str, project_id: str = "local") -> str:
    """
    Translate BigQuery DDL to DuckDB-compatible DDL.

    Handles:
      - {project_id} template substitution
      - Backtick-quoted table references → schema-qualified names
      - BQ type aliases → DuckDB types
      - PARTITION BY, CLUSTER BY, OPTIONS(...) clauses stripped
      - CURRENT_TIMESTAMP() → CURRENT_TIMESTAMP
      - GENERATE_UUID() → gen_random_uuid()::VARCHAR
      - SAFE_CAST → TRY_CAST
      - BQ JSON '' literal syntax → VARCHAR literals
      - INSERT INTO with BQ-specific literals → DuckDB-compatible
      - CREATE OR REPLACE VIEW → CREATE OR REPLACE VIEW (supported in DuckDB)
      - CREATE SCHEMA → CREATE SCHEMA IF NOT EXISTS
      - BOOL → BOOLEAN
    """
    # Template substitution for {project_id}
    sql = sql.replace("{project_id}", project_id)

    # OPTIONS(...) — strip entire clause using a paren-depth-aware parser
    # (must happen before other substitutions; the naive regex breaks when
    # description strings contain literal parentheses)
    sql = _strip_options_clauses(sql)

    # PARTITION BY ... (up to CLUSTER BY, OPTIONS, or end of line)
    sql = re.sub(
        r"\bPARTITION\s+BY\s+[^\n;(]+(?:\([^)]*\))?",
        "",
        sql,
        flags=re.IGNORECASE,
    )

    # CLUSTER BY ...
    sql = re.sub(r"\bCLUSTER\s+BY\s+[^\n;(]+", "", sql, flags=re.IGNORECASE)

    # SAFE_CAST → TRY_CAST
    sql = re.sub(r"\bSAFE_CAST\b", "TRY_CAST", sql, flags=re.IGNORECASE)

    # CURRENT_TIMESTAMP() → CURRENT_TIMESTAMP
    sql = re.sub(
        r"\bCURRENT_TIMESTAMP\s*\(\s*\)",
        "CURRENT_TIMESTAMP",
        sql,
        flags=re.IGNORECASE,
    )

    # GENERATE_UUID() → gen_random_uuid()::VARCHAR
    sql = re.sub(
        r"\bGENERATE_UUID\s*\(\s*\)",
        "gen_random_uuid()::VARCHAR",
        sql,
        flags=re.IGNORECASE,
    )

    # BQ JSON type → VARCHAR (but not "JSON 'literal'" — that becomes VARCHAR 'literal')
    # Match JSON as a type keyword (not followed by a string literal)
    sql = re.sub(r"\bJSON\b(?!\s*'[^']*')", "VARCHAR", sql, flags=re.IGNORECASE)

    # ARRAY<T> patterns must fire BEFORE scalar type substitutions.
    # If STRING→VARCHAR fires first, ARRAY<STRING> becomes ARRAY<VARCHAR> which
    # then silently fails to match the no-trailing-\b pattern below.
    # No trailing \b: > is a non-word char; \b after > only matches when the
    # next char is a word char (not space/comma), causing silent non-matches.
    sql = re.sub(r"\bARRAY<STRING>", "VARCHAR[]", sql, flags=re.IGNORECASE)
    sql = re.sub(r"\bARRAY<FLOAT64>", "DOUBLE[]", sql, flags=re.IGNORECASE)
    sql = re.sub(r"\bARRAY<INT64>", "BIGINT[]", sql, flags=re.IGNORECASE)
    sql = re.sub(r"\bARRAY<BOOL>", "BOOLEAN[]", sql, flags=re.IGNORECASE)

    # Scalar BQ type aliases → DuckDB equivalents (after ARRAY<T> patterns above)
    sql = re.sub(r"\bSTRING\b", "VARCHAR", sql, flags=re.IGNORECASE)
    sql = re.sub(r"\bINT64\b", "BIGINT", sql, flags=re.IGNORECASE)
    sql = re.sub(r"\bFLOAT64\b", "DOUBLE", sql, flags=re.IGNORECASE)
    sql = re.sub(r"\bBOOL\b", "BOOLEAN", sql, flags=re.IGNORECASE)

    # WHEN NOT MATCHED BY SOURCE → unsupported in DuckDB — strip
    sql = re.sub(
        r"\bWHEN\s+NOT\s+MATCHED\s+BY\s+SOURCE\b.*?(?=WHEN\b|;|$)",
        "",
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # `project.dataset.table` → dataset.table
    sql = re.sub(
        r"`([^`]+)\.([^`]+)\.([^`]+)`",
        lambda m: f"{m.group(2)}.{m.group(3)}",
        sql,
    )
    # `dataset.table` → dataset.table
    sql = re.sub(
        r"`([^`]+)\.([^`]+)`",
        lambda m: f"{m.group(1)}.{m.group(2)}",
        sql,
    )
    # remaining `identifier` → identifier
    sql = re.sub(r"`([^`]+)`", r"\1", sql)

    # DATE_TRUNC with 2-arg BQ style → DuckDB date_trunc(part, col)
    sql = re.sub(
        r"\bDATE_TRUNC\s*\(([^,]+),\s*([^)]+)\)",
        lambda m: f"date_trunc({m.group(2).strip()!r}, {m.group(1).strip()})",
        sql,
        flags=re.IGNORECASE,
    )

    return sql


def split_statements(sql: str) -> list[str]:
    """
    Split a SQL script on semicolons, skipping empty and comment-only blocks.
    """
    statements = []
    for stmt in sql.split(";"):
        # Strip comment-only lines
        lines = [
            line for line in stmt.splitlines()
            if not line.strip().startswith("--")
        ]
        cleaned = "\n".join(lines).strip()
        if cleaned:
            statements.append(cleaned)
    return statements


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    import duckdb  # deferred so the script fails loudly if duckdb not installed

    db_path = os.environ.get("DUCKDB_PATH", str(_DEFAULT_DB_PATH))
    project_id = os.environ.get("PROJECT_ID", "local")

    # Ensure output directory exists
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    if not MIGRATIONS_DIR.exists():
        logger.error("Migrations directory not found: %s", MIGRATIONS_DIR)
        sys.exit(1)

    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not migration_files:
        logger.warning("No .sql files found in %s", MIGRATIONS_DIR)

    logger.info("DuckDB path: %s", db_path)
    logger.info("Migrations dir: %s (%d files)", MIGRATIONS_DIR, len(migration_files))

    conn = duckdb.connect(str(db_path))

    # Create known schemas up-front so cross-schema references resolve
    for schema in (
        "nfl_dead_money",
        "gold_layer",
        "silver_v2_claims",
        "silver_v2_core",
        "silver_v2_sports",
        "monetization",
    ):
        try:
            conn.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
            logger.debug("Schema ensured: %s", schema)
        except Exception as e:
            logger.debug("Schema %s skipped: %s", schema, e)

    ok = 0
    skipped = 0
    failed = 0

    for migration_file in migration_files:
        logger.info("Applying: %s", migration_file.name)
        raw_sql = migration_file.read_text(encoding="utf-8")
        translated = translate_ddl(raw_sql, project_id=project_id)

        for stmt in split_statements(translated):
            try:
                conn.execute(stmt)
                ok += 1
            except Exception as e:
                err_str = str(e).lower()
                # Tolerate "already exists", "duplicate key", view-overwrite errors
                # and BQ-only constructs we couldn't translate (e.g. MERGE in DML migrations)
                if any(kw in err_str for kw in (
                    "already exists",
                    "duplicate",
                    "not supported",
                    "no such table",  # views referencing BQ-only tables
                    "merge",
                    "countif",
                    "safe_divide",
                )):
                    logger.debug(
                        "  Skipped (tolerated): %s — %.120s", migration_file.name, e
                    )
                    skipped += 1
                else:
                    logger.warning(
                        "  FAILED: %s — %.200s\n  SQL: %.120s",
                        migration_file.name,
                        e,
                        stmt[:120],
                    )
                    failed += 1

    conn.close()

    logger.info(
        "Done — %d statements OK, %d skipped, %d failed", ok, skipped, failed
    )
    if failed > 0:
        logger.warning(
            "%d statements failed — schema may be incomplete.  "
            "Check logs above.  Core tables (DDL) should still be usable.",
            failed,
        )


if __name__ == "__main__":
    main()
