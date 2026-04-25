import pandas as pd
from src.spotrac_scraper_v2 import SpotracScraper
import logging
import sys

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(name)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("AgeSurvey")


def check_age_source(year=2025):
    with SpotracScraper(headless=True) as scraper:
        # 1. Survey Dead Money
        logger.info("--- Checking Dead Money Page ---")
        try:
            df_dead = scraper.scrape_player_salaries(year)
            if "age" in df_dead.columns:
                valid_ages = df_dead["age"].dropna()
                logger.info(f"Dead Money: Found {len(valid_ages)} valid ages.")
                if not valid_ages.empty:
                    logger.info(f"Sample: {valid_ages.head().tolist()}")
            else:
                logger.info("Dead Money: 'age' column NOT found.")
                logger.info(f"Columns: {df_dead.columns.tolist()}")
        except Exception as e:
            logger.error(f"Dead Money failed: {e}")

        # 2. Survey Contracts
        logger.info("\n--- Checking Contracts Page (First Team only) ---")
        try:
            # Just scrape one team to test
            df_contracts = scraper.scrape_player_contracts(year, team_list=["BUF"])
            if "age" in df_contracts.columns:
                valid_ages = df_contracts["age"].dropna()
                logger.info(f"Contracts: Found {len(valid_ages)} valid ages.")
                if not valid_ages.empty:
                    logger.info(f"Sample: {valid_ages.head().tolist()}")
            else:
                logger.info("Contracts: 'age' column NOT found.")
                logger.info(f"Columns: {df_contracts.columns.tolist()}")
        except Exception as e:
            logger.error(f"Contracts failed: {e}")


if __name__ == "__main__":
    check_age_source()
