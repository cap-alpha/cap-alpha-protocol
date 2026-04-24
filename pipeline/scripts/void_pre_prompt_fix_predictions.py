"""
Void Pre-Prompt-Fix Predictions (Issue #168)

Marks all existing prediction_ledger rows as VOID in prediction_resolutions,
since they were extracted with the original weak prompt that accepted vibes,
stale news, and duplicates. Preserves the chain hash integrity (append-only).

Idempotent — safe to re-run. Skips predictions that already have a resolution.

Usage (inside Docker):
    python pipeline/scripts/void_pre_prompt_fix_predictions.py
    python pipeline/scripts/void_pre_prompt_fix_predictions.py --dry-run
"""

import argparse
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db_manager import DBManager
from src.resolution_engine import void_prediction

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
logger = logging.getLogger(__name__)

VOID_REASON = "low_quality_extraction_pre_prompt_fix_issue_168"


def void_existing_predictions(dry_run: bool = False):
    db = DBManager()
    project_id = os.environ["GCP_PROJECT_ID"]

    # Get all prediction hashes that don't already have a resolution
    query = f"""
        SELECT l.prediction_hash, l.pundit_name, l.extracted_claim
        FROM `{project_id}.gold_layer.prediction_ledger` l
        LEFT JOIN `{project_id}.gold_layer.prediction_resolutions` r
            ON l.prediction_hash = r.prediction_hash
        WHERE r.prediction_hash IS NULL
        ORDER BY l.ingestion_timestamp ASC
    """
    df = db.fetch_df(query)
    logger.info(f"Found {len(df)} unresolved predictions to void")

    if df.empty:
        logger.info("All predictions already have resolutions. Nothing to do.")
        return

    voided = 0
    for _, row in df.iterrows():
        phash = row["prediction_hash"]
        claim = str(row.get("extracted_claim", ""))[:80]
        pundit = row.get("pundit_name", "Unknown")

        if dry_run:
            logger.info(f"DRY RUN: would void {phash[:16]}… ({pundit}: {claim})")
            voided += 1
            continue

        try:
            void_prediction(
                prediction_hash=phash,
                reason=VOID_REASON,
                db=db,
            )
            voided += 1
            logger.info(f"VOIDED: {phash[:16]}… ({pundit}: {claim})")
        except Exception as e:
            logger.error(f"Failed to void {phash[:16]}…: {e}")

    logger.info(f"Voided {voided}/{len(df)} predictions.")
    db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Void pre-prompt-fix predictions"
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    void_existing_predictions(dry_run=args.dry_run)
