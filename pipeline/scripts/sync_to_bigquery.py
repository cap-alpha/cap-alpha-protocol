#!/usr/bin/env python3
"""
BigQuery Health Check — Post-Pipeline Validation

Verifies that Bronze, Silver, and Gold layer tables landed data in the most
recent pipeline run. Exits 0 on success, 1 if any critical table is empty.

Run after medallion_pipeline.py.
"""

import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db_manager import DBManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Tables that MUST have rows for the run to be considered successful
CRITICAL_TABLES = [
    "bronze_overthecap_contracts",
    "silver_spotrac_contracts",
    "fact_player_efficiency",
]

# Additional tables to report on but not fail the build over
INFORMATIONAL_TABLES = [
    "silver_spotrac_salaries",
    "silver_pfr_game_logs",
    "silver_penalties",
]


def check_row_count(db: DBManager, table: str) -> int:
    try:
        result = db.fetch_df(
            f"SELECT COUNT(*) as cnt FROM `{db.project_id}.{db.dataset_id}.{table}`"
        )
        return int(result["cnt"].iloc[0])
    except Exception as e:
        logger.warning(f"  Could not query {table}: {e}")
        return -1


def main():
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    logger.info(f"=== BigQuery Pipeline Health Check — {now_utc} ===")

    failures = []

    with DBManager() as db:
        logger.info(f"Project: {db.project_id}  Dataset: {db.dataset_id}")

        logger.info("\n--- Critical Tables ---")
        for table in CRITICAL_TABLES:
            count = check_row_count(db, table)
            status = "✓" if count > 0 else "✗ EMPTY" if count == 0 else "✗ ERROR"
            logger.info(f"  {status}  {table}: {count:,} rows")
            if count <= 0:
                failures.append(table)

        logger.info("\n--- Informational Tables ---")
        for table in INFORMATIONAL_TABLES:
            count = check_row_count(db, table)
            status = "✓" if count > 0 else "—"
            logger.info(f"  {status}  {table}: {count:,} rows")

    if failures:
        logger.error(f"\n❌ Health check FAILED. Empty or errored tables: {failures}")
        sys.exit(1)

    logger.info("\n✅ Health check PASSED. All critical tables have data.")
    sys.exit(0)


if __name__ == "__main__":
    main()
