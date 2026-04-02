"""
BigQuery migration runner.

Applies SQL migrations from pipeline/migrations/ that are compatible with BigQuery.
Skips old DuckDB/MotherDuck migrations (001, 002).

Usage (inside Docker):
    python scripts/run_bq_migrations.py
    python scripts/run_bq_migrations.py --migration 003
"""

import argparse
import logging
import os
import sys

from google.cloud import bigquery
from google.cloud.exceptions import Conflict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pipeline.src.db_manager import DBManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Migrations to skip (DuckDB/MotherDuck SQL, not valid for BigQuery)
SKIP_MIGRATIONS = {"001", "002"}

MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), "..", "pipeline", "migrations")


def ensure_dataset(client: bigquery.Client, project_id: str, dataset_id: str, location: str = "US"):
    """Creates a BigQuery dataset if it doesn't exist."""
    dataset_ref = bigquery.Dataset(f"{project_id}.{dataset_id}")
    dataset_ref.location = location
    try:
        client.create_dataset(dataset_ref)
        logger.info(f"Created dataset: {project_id}.{dataset_id}")
    except Conflict:
        logger.info(f"Dataset already exists: {project_id}.{dataset_id}")


def apply_migration(migration_num: str, db: DBManager):
    """Applies a single migration file."""
    migration_files = [
        f for f in os.listdir(MIGRATIONS_DIR)
        if f.startswith(migration_num) and f.endswith(".sql")
    ]
    if not migration_files:
        logger.error(f"No migration file found starting with {migration_num}")
        sys.exit(1)

    migration_file = os.path.join(MIGRATIONS_DIR, migration_files[0])
    logger.info(f"Applying migration: {migration_files[0]}")

    with open(migration_file) as f:
        sql = f.read()

    project_id = os.environ.get("GCP_PROJECT_ID")
    sql = sql.replace("{project_id}", project_id)

    db.execute(sql)
    logger.info(f"Migration {migration_num} applied successfully.")


def main():
    parser = argparse.ArgumentParser(description="Apply BigQuery migrations")
    parser.add_argument("--migration", help="Apply a specific migration number (e.g. 003)")
    args = parser.parse_args()

    project_id = os.environ.get("GCP_PROJECT_ID")
    if not project_id:
        logger.error("GCP_PROJECT_ID not set.")
        sys.exit(1)

    db = DBManager()

    # Ensure required datasets exist before running migrations
    ensure_dataset(db.client, project_id, "gold_layer")
    ensure_dataset(db.client, project_id, "nfl_dead_money")

    if args.migration:
        if args.migration in SKIP_MIGRATIONS:
            logger.warning(f"Migration {args.migration} is a legacy DuckDB migration — skipping.")
            return
        apply_migration(args.migration, db)
    else:
        # Apply all non-skipped migrations in order
        migration_files = sorted(
            f for f in os.listdir(MIGRATIONS_DIR) if f.endswith(".sql")
        )
        for mf in migration_files:
            num = mf.split("_")[0]
            if num in SKIP_MIGRATIONS:
                logger.info(f"Skipping legacy migration: {mf}")
                continue
            apply_migration(num, db)

    db.close()
    logger.info("All migrations complete.")


if __name__ == "__main__":
    main()
