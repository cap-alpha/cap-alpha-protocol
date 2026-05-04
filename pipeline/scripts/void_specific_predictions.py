"""
Void specific prediction hashes that were incorrectly extracted (Issue #523).

Usage (inside Docker or with BigQuery credentials):
    python pipeline/scripts/void_specific_predictions.py [--dry-run]
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db_manager import DBManager
from src.resolution_engine import void_prediction

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
logger = logging.getLogger(__name__)

# Prediction hashes to void, with reasons
# Add new entries here as data quality issues are identified.
VOID_LIST = [
    (
        "86e86bcfd39f785e83b2d75b7af0195e2471f42def8b5705c9a163946dde1a34",
        "false_extraction_issue_523: pundit was posing rhetorical questions, not making claims; "
        "extractor incorrectly inferred belief from question framing",
    ),
]


def main(dry_run: bool = False) -> None:
    db = DBManager()

    for prediction_hash, reason in VOID_LIST:
        logger.info(f"Voiding {prediction_hash[:16]}… reason: {reason[:60]}")
        if dry_run:
            logger.info("  DRY RUN — skipping write")
            continue
        result = void_prediction(prediction_hash, reason=reason, db=db)
        logger.info(f"  Voided: {result.resolution_status}")

    if dry_run:
        logger.info("Dry run complete — no changes written")
    else:
        logger.info(f"Voided {len(VOID_LIST)} prediction(s)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Void specific bad predictions")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
