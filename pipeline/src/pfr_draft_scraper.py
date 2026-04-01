import logging
import time
from pathlib import Path
from typing import List, Optional

import pandas as pd
import requests
from bs4 import BeautifulSoup

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def robust_request(
    url: str, max_retries: int = 5, initial_backoff: float = 2.0
) -> Optional[requests.Response]:
    """
    Fetch a URL with exponential backoff for 429 (Rate Limit) errors.
    """
    backoff = initial_backoff
    for i in range(max_retries):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code == 429:
                wait_time = backoff * (2**i)
                logger.warning(
                    f"Rate limited (429) for {url}. Backing off for {wait_time:.1f}s..."
                )
                time.sleep(wait_time)
                continue
            resp.raise_for_status()
            return resp
        except requests.exceptions.RequestException as e:
            if i == max_retries - 1:
                logger.error(f"Failed to fetch {url} after {max_retries} attempts: {e}")
                return None
            wait_time = backoff * (2**i)
            logger.warning(
                f"Request failed for {url}: {e}. Retrying in {wait_time:.1f}s..."
            )
            time.sleep(wait_time)
    return None


def scrape_draft_class(year: int) -> pd.DataFrame:
    """
    Scrape the NFL Draft class for a specific year from PFR.
    URL: https://www.pro-football-reference.com/years/{year}/draft.htm
    """
    url = f"https://www.pro-football-reference.com/years/{year}/draft.htm"
    logger.info(f"Scraping {year} NFL Draft from {url}...")

    resp = robust_request(url)
    if not resp:
        return pd.DataFrame()

    try:
        # PFR Draft table id is 'drafts'
        soup = BeautifulSoup(resp.text, "lxml")
        table = soup.find("table", id="drafts")

        if not table:
            logger.error(f"Could not find draft table for {year}")
            return pd.DataFrame()

        df = pd.read_html(str(table))[0]

        # Clean up MultiIndex if present (usually not for draft page, but good safety)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.map("_".join)

        # Standardize Columns
        # PFR Draft Columns: Rnd, Pick, Tm, Player, Pos, Age, To, AP1, PB, St, ...
        # We need: year, round, pick, team, player_name, position

        # Filter out header repetition rows (PFR repeats headers every ~30 rows)
        if "Rnd" in df.columns:
            df = df[df["Rnd"] != "Rnd"]

        # Normalize
        df["year"] = year

        # Map Teams (PFR uses full names sometimes or abbreviations)
        # We will keep raw Tm for now, ingest_to_duckdb can normalize if needed.

        keep_cols = {
            "Rnd": "round",
            "Pick": "pick",
            "Tm": "team",
            "Player": "player_name",
            "Pos": "position",
            "year": "year",
        }

        df = df.rename(columns=keep_cols)

        # Keep only relevant columns
        df = df[list(keep_cols.values())]

        logger.info(f"✓ Extracted {len(df)} draft picks for {year}")
        return df

    except Exception as e:
        logger.error(f"Error parsing draft {year}: {e}")
        return pd.DataFrame()


def scrape_recent_drafts(start_year: int, end_year: int) -> pd.DataFrame:
    all_drafts = []
    for year in range(start_year, end_year + 1):
        df = scrape_draft_class(year)
        if not df.empty:
            all_drafts.append(df)
        time.sleep(3.0)  # Politeness

    if all_drafts:
        combined = pd.concat(all_drafts, ignore_index=True)
        # Save raw
        output_path = "data/raw/pfr/draft_history.csv"
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        combined.to_csv(output_path, index=False)
        logger.info(f"Saved {len(combined)} draft records to {output_path}")
        return combined
    return pd.DataFrame()


if __name__ == "__main__":
    scrape_recent_drafts(2023, 2025)
