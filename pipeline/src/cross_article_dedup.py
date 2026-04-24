"""
Cross-Article Deduplication for the Prediction Ledger (Issue #210)

When multiple articles quote the same pundit making the same prediction,
the extractor creates duplicate ledger entries. This module detects and
voids those duplicates by comparing PENDING predictions grouped by
(pundit_id, claim_category, target_player_name) using SequenceMatcher.

Usage (inside Docker):
    python -m src.cross_article_dedup              # void duplicates
    python -m src.cross_article_dedup --dry-run     # preview without voiding
"""

import argparse
import logging
import os
from difflib import SequenceMatcher
from typing import Optional

import pandas as pd

from src.db_manager import DBManager
from src.resolution_engine import void_prediction

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
logger = logging.getLogger(__name__)

LEDGER_TABLE = "gold_layer.prediction_ledger"
RESOLUTIONS_TABLE = "gold_layer.prediction_resolutions"

SIMILARITY_THRESHOLD = 0.75


def _get_pending_predictions(db: DBManager) -> pd.DataFrame:
    """
    Fetches all PENDING predictions from the ledger that have not yet
    been resolved or voided. Returns columns needed for dedup grouping.
    """
    project_id = os.environ.get("GCP_PROJECT_ID")
    query = f"""
        SELECT
            l.prediction_hash,
            l.pundit_id,
            l.extracted_claim,
            l.claim_category,
            l.target_player_name,
            l.ingestion_timestamp
        FROM `{project_id}.{LEDGER_TABLE}` l
        LEFT JOIN `{project_id}.{RESOLUTIONS_TABLE}` r
            ON l.prediction_hash = r.prediction_hash
        WHERE r.prediction_hash IS NULL
           OR r.resolution_status = 'PENDING'
        ORDER BY l.ingestion_timestamp ASC
    """
    return db.fetch_df(query)


def _find_duplicates_in_group(group_df: pd.DataFrame) -> list[str]:
    """
    Within a group of predictions from the same pundit/category/player,
    compare extracted_claim pairwise. When two claims have
    SequenceMatcher ratio >= SIMILARITY_THRESHOLD, keep the earliest
    (by ingestion_timestamp) and mark the later one as a duplicate.

    Returns a list of prediction_hashes to void.
    """
    if len(group_df) <= 1:
        return []

    # Sort by ingestion_timestamp ascending so earliest is first
    sorted_df = group_df.sort_values("ingestion_timestamp").reset_index(drop=True)

    to_void = set()
    kept_indices = []

    for idx, row in sorted_df.iterrows():
        if row["prediction_hash"] in to_void:
            continue

        claim = (row.get("extracted_claim") or "").lower()
        is_dup = False

        for kept_idx in kept_indices:
            kept_row = sorted_df.iloc[kept_idx]
            kept_claim = (kept_row.get("extracted_claim") or "").lower()
            ratio = SequenceMatcher(None, claim, kept_claim).ratio()
            if ratio >= SIMILARITY_THRESHOLD:
                # This row is a duplicate of an earlier one -- void it
                to_void.add(row["prediction_hash"])
                is_dup = True
                break

        if not is_dup:
            kept_indices.append(idx)

    return list(to_void)


def cross_article_dedup(db: Optional[DBManager] = None, dry_run: bool = False) -> dict:
    """
    Main dedup entry point.

    1. Query all PENDING predictions
    2. Group by (pundit_id, claim_category, target_player_name)
    3. Within each group, compare extracted_claim pairwise
    4. Keep the earliest entry, void the rest as cross_article_duplicate

    Returns a summary dict with counts.
    """
    close_db = db is None
    if db is None:
        db = DBManager()

    summary = {
        "total_pending": 0,
        "groups_checked": 0,
        "duplicates_found": 0,
        "duplicates_voided": 0,
        "dry_run": dry_run,
    }

    try:
        pending_df = _get_pending_predictions(db)
        summary["total_pending"] = len(pending_df)

        if pending_df.empty:
            logger.info("No pending predictions to check for duplicates.")
            return summary

        logger.info(
            f"Checking {len(pending_df)} pending predictions for "
            f"cross-article duplicates..."
        )

        # Normalize target_player_name for grouping (treat None as empty string)
        pending_df["_group_player"] = (
            pending_df["target_player_name"].fillna("").str.lower().str.strip()
        )
        pending_df["_group_category"] = (
            pending_df["claim_category"].fillna("").str.lower().str.strip()
        )

        grouped = pending_df.groupby(["pundit_id", "_group_category", "_group_player"])

        all_to_void = []
        for group_key, group_df in grouped:
            if len(group_df) <= 1:
                continue

            summary["groups_checked"] += 1
            duplicates = _find_duplicates_in_group(group_df)

            if duplicates:
                pundit_id, category, player = group_key
                logger.info(
                    f"Found {len(duplicates)} duplicate(s) in group "
                    f"pundit={pundit_id}, category={category}, "
                    f"player={player or '(none)'}"
                )
                all_to_void.extend(duplicates)

        summary["duplicates_found"] = len(all_to_void)

        if not all_to_void:
            logger.info("No cross-article duplicates found.")
            return summary

        for pred_hash in all_to_void:
            if dry_run:
                logger.info(f"DRY RUN: would void {pred_hash[:16]}...")
            else:
                void_prediction(
                    prediction_hash=pred_hash,
                    reason="cross_article_duplicate",
                    db=db,
                )
                summary["duplicates_voided"] += 1
                logger.info(f"Voided duplicate: {pred_hash[:16]}...")

        logger.info(
            f"Cross-article dedup complete: "
            f"{summary['duplicates_found']} duplicates found, "
            f"{summary['duplicates_voided']} voided."
        )
        return summary
    finally:
        if close_db:
            db.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Cross-Article Deduplication for Prediction Ledger"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview duplicates without voiding them",
    )
    args = parser.parse_args()

    import json

    result = cross_article_dedup(dry_run=args.dry_run)
    print(json.dumps(result, indent=2))
