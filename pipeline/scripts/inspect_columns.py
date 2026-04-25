import pandas as pd
from src.spotrac_scraper_v2 import SpotracScraper
import logging
import sys

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger("Inspector")


def inspect():
    with SpotracScraper(headless=True) as scraper:
        # 1. Dead Money
        try:
            logger.info("Scraping Dead Money 2025...")
            df = scraper.scrape_player_salaries(2025)
            logger.info(f"Dead Money Columns: {df.columns.tolist()}")
            if "age" in df.columns:
                logger.info(f"Dead Money Age Sample: {df['age'].dropna().unique()[:5]}")
        except Exception as e:
            logger.error(f"Dead Money Error: {e}")

        # 2. Contracts (BUF)
        try:
            logger.info("Scraping Contracts (BUF) 2025...")
            df = scraper.scrape_player_contracts(2025, team_list=["BUF"])
            logger.info(f"Contracts Columns: {df.columns.tolist()}")
            if "age" in df.columns:
                logger.info(f"Contracts Age Sample: {df['age'].dropna().unique()[:5]}")
        except Exception as e:
            logger.error(f"Contracts Error: {e}")


if __name__ == "__main__":
    inspect()
