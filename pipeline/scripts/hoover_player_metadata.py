from src.db_manager import DBManager
import pandas as pd
import time
import random
import os
import logging
from pathlib import Path
from src.pfr_roster_scraper import PFRRosterScraper
from src.pfr_profile_scraper import PFRProfileScraper

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

DB_PATH = "data/nfl_data.db"
OUTPUT_METADATA = "data/raw/player_metadata.csv"


def get_roster_urls(year: int):
    """Scrape roster for a year and extract player URLs."""
    scraper = PFRRosterScraper()
    # Modify scraper to have longer sleep
    import time as t

    # Team codes for a subset or full run
    team_codes = [
        "ARI",
        "SF",
        "KC",
        "BAL",
        "PHI",
        "DET",
        "DAL",
        "GB",
        "LAR",
        "TB",
    ]  # Subset for now
    all_players = []

    for team in team_codes:
        logger.info(f"Scraping roster for {team} in {year}...")
        try:
            df = scraper._scrape_team_roster(team, year)
            if df is not None:
                all_players.append(df)
            # Strict Rate Limit
            t.sleep(random.uniform(8, 12))
        except Exception as e:
            logger.error(f"Failed {team}: {e}")
            t.sleep(60)  # Cooling down on error

    if all_players:
        return pd.concat(all_players, ignore_index=True)
    return pd.DataFrame()


def prioritized_hoover():
    """Hoover the top players first for immediate value."""
    con = DBManager()
    # Target players in our fact table (Gold Layer)
    query = """
    SELECT DISTINCT player_name FROM fact_player_efficiency 
    WHERE year IN (2024, 2025)
    ORDER BY edce_risk DESC, ied_overpayment DESC
    LIMIT 20
    """
    targets = con.execute(query).df()["player_name"].tolist()
    con.close()

    logger.info(f"Targeting top {len(targets)} players for priority hoovering.")

    # We still need the URLs from rosters first
    roster_df = get_roster_urls(2025)
    if roster_df.empty:
        logger.error("Roster scrape failed.")
        return

    # Match targets to URLs
    prioritized_df = roster_df[roster_df["player_name"].isin(targets)]
    urls = prioritized_df["player_url"].dropna().unique().tolist()

    logger.info(f"Found {len(urls)} URLs for prioritized hoovering.")

    p_scraper = PFRProfileScraper(delay_range=(8, 12))
    p_scraper.run_batch(urls, OUTPUT_METADATA)

    ingest_metadata_to_duckdb()


if __name__ == "__main__":
    # prioritized_hoover()
    # For now, let's just do a manual proof of concept for the user's favorite "bug"
    p_scraper = PFRProfileScraper()
    proof_urls = ["/players/M/MurrKy00.htm", "/players/W/WillTr00.htm"]
    p_scraper.run_batch(proof_urls, OUTPUT_METADATA)
    ingest_metadata_to_duckdb()
