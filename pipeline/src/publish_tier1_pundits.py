"""
Publish Tier-1 Pundits (Issue #830)

Marks the canonical tier-1 pundit list as published=TRUE in the
pundit_registry BigQuery table.  Pundits that don't exist in the
registry yet are created with published=TRUE so they're immediately
surfaced via the API once content is ingested.

Run once after deploying migration 015:
  python -m src.publish_tier1_pundits

Safe to re-run (idempotent UPDATE / INSERT logic via MERGE).
"""

import logging
import os
import sys
from pathlib import Path

import yaml

from src.db_manager import DBManager

logger = logging.getLogger(__name__)

TIER1_CONFIG = Path(__file__).parent.parent / "config" / "tier1_pundits.yaml"


def load_tier1_pundits(config_path: Path = TIER1_CONFIG) -> list[dict]:
    """Load the tier-1 pundit list from YAML config."""
    with open(config_path) as f:
        cfg = yaml.safe_load(f)
    return cfg.get("pundits", [])


def publish_tier1_pundits(db: DBManager | None = None) -> dict:
    """
    Set published=TRUE for all tier-1 pundits in pundit_registry.

    For pundits already in the registry: UPDATE published=TRUE.
    For pundits not yet in the registry: INSERT a minimal stub row
    so they can be hydrated once content is ingested.

    Returns a summary dict: {updated, inserted, skipped}.
    """
    close_db = db is None
    if db is None:
        db = DBManager()

    try:
        project_id = os.environ.get("GCP_PROJECT_ID")
        if not project_id:
            raise RuntimeError("GCP_PROJECT_ID env var not set")

        pundits = load_tier1_pundits()
        if not pundits:
            logger.warning("Tier-1 pundit list is empty — nothing to publish")
            return {"updated": 0, "inserted": 0, "skipped": 0}

        registry_table = f"`{project_id}.nfl_dead_money.pundit_registry`"

        # Fetch existing pundit_ids so we can split into update vs insert
        existing_df = db.fetch_df(f"SELECT pundit_id FROM {registry_table}")
        existing_ids: set[str] = (
            set(existing_df["pundit_id"].tolist()) if not existing_df.empty else set()
        )

        updated = 0
        inserted = 0

        for pundit in pundits:
            pid = pundit["pundit_id"]
            name = pundit["pundit_name"]
            sport = pundit.get("sport", "NFL")

            if pid in existing_ids:
                # UPDATE existing row
                db.execute(
                    f"""
                    UPDATE {registry_table}
                    SET
                        published  = TRUE,
                        updated_at = CURRENT_TIMESTAMP()
                    WHERE pundit_id = '{pid}'
                    """
                )
                logger.info(f"Published (updated): {name} ({pid})")
                updated += 1
            else:
                # INSERT stub row — will be enriched by media_ingestor once content arrives
                db.execute(
                    f"""
                    INSERT INTO {registry_table} (
                        pundit_id, pundit_name, sport,
                        source_ids, match_authors,
                        enabled, is_source_default, published,
                        polling_cadence,
                        last_seen_at, posts_per_month,
                        created_at, updated_at
                    ) VALUES (
                        '{pid}', '{name}', '{sport}',
                        [], [],
                        TRUE, FALSE, TRUE,
                        'daily',
                        NULL, NULL,
                        CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP()
                    )
                    """
                )
                logger.info(f"Published (inserted stub): {name} ({pid})")
                inserted += 1

        summary = {
            "updated": updated,
            "inserted": inserted,
            "skipped": len(pundits) - updated - inserted,
        }
        logger.info(f"publish_tier1_pundits complete: {summary}")
        return summary

    finally:
        if close_db:
            db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result = publish_tier1_pundits()
    print(f"Done: {result}")
    sys.exit(0)
