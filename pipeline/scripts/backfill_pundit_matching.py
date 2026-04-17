"""
Backfill Pundit Matching for Existing raw_pundit_media Rows (Issue #166)

Re-runs the enhanced pundit matcher (author field → byline scan → source default)
against all rows in raw_pundit_media that currently have no matched_pundit_id.
Updates them in place.

Usage (inside Docker):
    python pipeline/scripts/backfill_pundit_matching.py             # live update
    python pipeline/scripts/backfill_pundit_matching.py --dry-run   # preview
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db_manager import DBManager
from src.media_ingestor import load_media_config, match_pundit

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
logger = logging.getLogger(__name__)


def backfill(dry_run: bool = False):
    db = DBManager()
    project_id = os.environ["GCP_PROJECT_ID"]

    # Load current source config to get pundit rosters + defaults
    config = load_media_config()
    sources_by_id = {s["id"]: s for s in config.get("sources", [])}

    # Fetch all unmatched rows (string "None" was written instead of actual NULL)
    query = f"""
        SELECT content_hash, source_id, author, raw_text
        FROM `{project_id}.nfl_dead_money.raw_pundit_media`
        WHERE matched_pundit_id IS NULL
           OR matched_pundit_id = 'None'
           OR matched_pundit_name IS NULL
           OR matched_pundit_name = 'None'
    """
    df = db.fetch_df(query)
    logger.info(f"Found {len(df)} unmatched rows to re-process")

    if df.empty:
        logger.info("Nothing to backfill.")
        return

    matched_count = 0
    updates = []

    for _, row in df.iterrows():
        source_id = row["source_id"]
        source = sources_by_id.get(source_id, {})
        pundits = source.get("pundits", [])

        pid, pname, method = match_pundit(
            author=row.get("author"),
            pundits=pundits,
            raw_text=row.get("raw_text"),
            source=source,
        )

        if pid:
            matched_count += 1
            updates.append(
                {
                    "content_hash": row["content_hash"],
                    "pundit_id": pid,
                    "pundit_name": pname,
                    "method": method,
                }
            )
            if matched_count <= 10:
                logger.info(
                    f"  MATCH [{method}]: {row['content_hash'][:16]}… "
                    f"→ {pname} (source={source_id})"
                )

    logger.info(
        f"Backfill results: {matched_count}/{len(df)} rows now matched "
        f"({len(df) - matched_count} still unmatched)"
    )

    # Show method breakdown
    methods = {}
    for u in updates:
        methods[u["method"]] = methods.get(u["method"], 0) + 1
    for method, count in sorted(methods.items()):
        logger.info(f"  {method}: {count}")

    if dry_run:
        logger.info("DRY RUN — no updates written.")
        return

    # Batch update via individual UPDATE statements
    # (BigQuery doesn't support parameterized batch updates easily)
    for u in updates:
        escaped_name = u["pundit_name"].replace("'", "\\'")
        update_sql = f"""
            UPDATE `{project_id}.nfl_dead_money.raw_pundit_media`
            SET matched_pundit_id = '{u["pundit_id"]}',
                matched_pundit_name = '{escaped_name}'
            WHERE content_hash = '{u["content_hash"]}'
        """
        try:
            db.execute(update_sql)
        except Exception as e:
            logger.error(f"Failed to update {u['content_hash'][:16]}…: {e}")

    logger.info(f"Wrote {len(updates)} updates to raw_pundit_media.")
    db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill pundit matching")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    backfill(dry_run=args.dry_run)
