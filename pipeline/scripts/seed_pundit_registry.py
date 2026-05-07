"""
Seed pundit_registry and source_registry from media_sources.yaml.

This script is idempotent: it skips pundits/sources already present by default.
Use --overwrite to clear and re-seed from scratch.

Usage:
    python -m scripts.seed_pundit_registry              # skip existing (safe re-run)
    python -m scripts.seed_pundit_registry --overwrite  # DELETE + re-insert all rows

Environment:
    GCP_PROJECT_ID              — required
    GCP_SERVICE_ACCOUNT_JSON    — optional (falls back to ADC)
"""

import argparse
import json
import logging
import sys
from pathlib import Path

import yaml

# Ensure project src/ is importable when run as a script
_PIPELINE_DIR = Path(__file__).resolve().parent.parent
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))

from src.db_manager import DBManager  # noqa: E402
from src.registry_manager import RegistryManager  # noqa: E402

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
logger = logging.getLogger(__name__)

_YAML_PATH = _PIPELINE_DIR / "config" / "media_sources.yaml"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed pundit_registry / source_registry from media_sources.yaml"
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help=(
            "DELETE existing rows before inserting. "
            "Default is idempotent skip (safe to re-run)."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse YAML and report counts without writing to BigQuery.",
    )
    args = parser.parse_args()

    # Load YAML
    logger.info(f"Loading media_sources.yaml from {_YAML_PATH}")
    with open(_YAML_PATH) as f:
        config = yaml.safe_load(f)

    sources = config.get("sources", [])
    pundits_total = sum(
        len(s.get("pundits", [])) + (1 if s.get("default_pundit") else 0)
        for s in sources
    )
    logger.info(
        f"YAML contains {len(sources)} source(s) and ~{pundits_total} pundit entries"
    )

    if args.dry_run:
        logger.info("--dry-run: no BigQuery writes.")
        print(
            json.dumps(
                {
                    "dry_run": True,
                    "sources_in_yaml": len(sources),
                    "approx_pundits_in_yaml": pundits_total,
                }
            )
        )
        return

    db = DBManager()
    try:
        rm = RegistryManager(db)
        summary = rm.seed_from_yaml(config, overwrite=args.overwrite)
        logger.info(f"Seed complete: {summary}")
        print(json.dumps(summary))
    finally:
        db.close()


if __name__ == "__main__":
    main()
