#!/usr/bin/env python3
"""
backfill_null_season_year.py — Persist season_year for NULL-season_year rows
in gold_layer.prediction_ledger (Issue #1167).

Background
----------
resolve_daily.py's resolve_game_outcomes() and resolve_player_performance()
now infer season_year at *read time* from ingestion_timestamp when it's NULL
(see src.resolve_daily._infer_season_year_from_ingestion), so those rows can
enter the normal season-completion gate instead of hard-skipping forever.

That read-time fallback is enough on its own — this script is NOT required
for the resolver fix to work. It exists to *persist* the inferred value onto
the ~831 known-affected rows (game_outcome / player_performance claims
ingested 2026-04-24 -> 2026-05-05 with season_year IS NULL) so that:
  - dashboard / analytics queries that read season_year directly (bypassing
    the resolver) see a populated value instead of NULL, and
  - the read-time inference doesn't have to re-run on every resolver pass.

This script reuses the exact same inference function the resolver uses
(imported, not reimplemented) so the persisted value can never drift from
what resolve_daily.py would compute live.

*** SAFETY — READ THIS BEFORE RUNNING ***
This script performs UPDATE DML against gold_layer.prediction_ledger in
production BigQuery. Default behavior is DRY RUN (prints the planned
per-row updates, writes nothing). Passing --execute performs the writes.

Per Issue #1167 triage: DO NOT run with --execute without a human
supervising the run and reviewing the dry-run output first. This script was
authored as part of the resolver-stall fix but intentionally NOT executed
against prod as part of that change.

Usage:
    python -m scripts.backfill_null_season_year                # dry run (default)
    python -m scripts.backfill_null_season_year --limit 2000    # dry run, custom limit
    python -m scripts.backfill_null_season_year --execute        # ACTUALLY WRITES

Options:
    --execute       Perform the UPDATE against BigQuery. Omit for a dry run.
    --limit N       Max rows to process per run (default: 2000; ~831 expected).
    --category CAT  Restrict to one claim_category: "game_outcome" or
                     "player_performance". Default: both (matches the two
                     resolvers that hard-require season_year).
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

# Allow running as `python pipeline/scripts/backfill_null_season_year.py`
# directly. `src` is imported as a package (`from src.db_manager import
# ...`), so the path entry must be the `pipeline/` directory that *contains*
# `src/`, not `pipeline/src` itself (LOW, Issue #1167 adversarial review —
# the previous `.../ "src"` entry made `import src.db_manager` fail with
# ModuleNotFoundError when this script was run directly, only working when
# invoked as `python -m scripts.backfill_null_season_year` from `pipeline/`).
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db_manager import DBManager
from src.resolve_daily import _infer_season_year_from_ingestion

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
logger = logging.getLogger(__name__)

LEDGER_TABLE = "gold_layer.prediction_ledger"
_TARGET_CATEGORIES = ("game_outcome", "player_performance")
_BATCH_SIZE = 500


def find_null_season_year_rows(
    db: DBManager,
    limit: int = 2000,
    category: str | None = None,
) -> "list[dict]":
    """
    Read-only SELECT: find game_outcome / player_performance rows with
    NULL season_year, plus the ingestion_timestamp needed to infer it.
    """
    project_id = os.environ.get("GCP_PROJECT_ID", "")
    if not project_id:
        raise RuntimeError("GCP_PROJECT_ID env var is required")

    categories = [category] if category else list(_TARGET_CATEGORIES)
    category_list_sql = ", ".join(f"'{c}'" for c in categories)

    query = f"""
        SELECT prediction_hash, claim_category, ingestion_timestamp
        FROM `{project_id}.{LEDGER_TABLE}`
        WHERE season_year IS NULL
          AND claim_category IN ({category_list_sql})
        LIMIT {int(limit)}
    """
    logger.info(
        f"Fetching up to {limit} NULL-season_year rows "
        f"(categories={categories}) from {LEDGER_TABLE}…"
    )
    df = db.fetch_df(query)
    return df.to_dict("records")


def plan_updates(rows: "list[dict]") -> "list[dict]":
    """
    Compute the inferred season_year for each row using the exact same
    logic resolve_daily.py uses at read time. Rows with no ingestion_timestamp
    (and therefore no inferable season_year) are skipped, not defaulted.
    """
    updates = []
    skipped = 0
    for row in rows:
        inferred = _infer_season_year_from_ingestion(row.get("ingestion_timestamp"))
        if inferred is None:
            skipped += 1
            continue
        updates.append(
            {
                "prediction_hash": row["prediction_hash"],
                "claim_category": row["claim_category"],
                "season_year": inferred,
            }
        )
    if skipped:
        logger.warning(
            f"{skipped} row(s) had no ingestion_timestamp to infer from — left NULL."
        )
    return updates


def apply_updates(db: DBManager, updates: "list[dict]") -> int:
    """MERGE the computed season_year values back into prediction_ledger."""
    project_id = os.environ["GCP_PROJECT_ID"]
    table_ref = f"`{project_id}.{LEDGER_TABLE}`"
    total_updated = 0

    for batch_start in range(0, len(updates), _BATCH_SIZE):
        batch = updates[batch_start : batch_start + _BATCH_SIZE]
        value_rows = []
        for u in batch:
            phash = str(u["prediction_hash"]).replace("'", "''")
            value_rows.append(f"('{phash}', {int(u['season_year'])})")
        values_sql = ",\n        ".join(value_rows)

        merge_sql = f"""
            MERGE {table_ref} AS target
            USING (
                SELECT * FROM UNNEST([
                    STRUCT<prediction_hash STRING, season_year INT64>
                    {values_sql}
                ])
            ) AS source
            ON target.prediction_hash = source.prediction_hash
            WHEN MATCHED AND target.season_year IS NULL THEN UPDATE SET
                season_year = source.season_year
        """
        result = db.execute(merge_sql)
        rows_affected = result.job.num_dml_affected_rows or 0
        total_updated += rows_affected
        logger.info(
            f"Batch {batch_start // _BATCH_SIZE + 1}: merged {rows_affected} rows"
        )

    return total_updated


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Backfill NULL season_year in gold_layer.prediction_ledger for "
            "game_outcome / player_performance claims (Issue #1167). "
            "DRY RUN by default — pass --execute to actually write."
        )
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Perform the UPDATE against BigQuery. Omit for a dry run (default).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=2000,
        help="Max rows to process per run (default: 2000; ~831 expected).",
    )
    parser.add_argument(
        "--category",
        choices=list(_TARGET_CATEGORIES),
        default=None,
        help="Restrict to one claim_category. Default: both.",
    )
    args = parser.parse_args()

    db = DBManager()
    try:
        rows = find_null_season_year_rows(db, limit=args.limit, category=args.category)
        if not rows:
            logger.info("No NULL-season_year rows found. Nothing to backfill.")
            return

        logger.info(f"Found {len(rows)} NULL-season_year rows.")
        updates = plan_updates(rows)

        if not args.execute:
            logger.info(
                "DRY RUN (default) — no writes performed. "
                "Pass --execute to apply. Sample of first 10 planned updates:"
            )
            for u in updates[:10]:
                logger.info(f"  {u}")
            print(
                json.dumps(
                    {
                        "rows_scanned": len(rows),
                        "rows_plannable": len(updates),
                        "dry_run": True,
                    },
                    indent=2,
                )
            )
            return

        logger.warning(
            f"--execute passed: writing inferred season_year for "
            f"{len(updates)} rows to production BigQuery."
        )
        total_updated = apply_updates(db, updates)
        print(
            json.dumps(
                {
                    "rows_scanned": len(rows),
                    "rows_plannable": len(updates),
                    "rows_updated": total_updated,
                    "dry_run": False,
                },
                indent=2,
            )
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
