"""
Scrape Spotrac player salaries and save to raw data directory.

This script scrapes individual player salary data from Spotrac,
which can then be merged with PFR rosters for complete player profiles.
"""

import sys
import logging
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.spotrac_scraper_v2 import scrape_and_save_player_salaries

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Scrape Spotrac player salaries")
    parser.add_argument("--year", type=int, required=True, help="NFL season year")
    parser.add_argument(
        "--output-dir", type=str, default="data/raw", help="Output directory"
    )

    args = parser.parse_args()

    logger.info(f"Scraping player salaries for {args.year}...")

    try:
        filepath = scrape_and_save_player_salaries(
            year=args.year, output_dir=args.output_dir
        )
        logger.info(f"✅ SUCCESS: Saved to {filepath}")
        return 0
    except Exception as e:
        logger.error(f"❌ FAILED: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
