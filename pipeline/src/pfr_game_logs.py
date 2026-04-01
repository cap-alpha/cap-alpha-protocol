"""
Weekly Game Log Scraper for PFR.

Fetches boxscore data for every game in a given week/year to build a
comprehensive database of weekly player performance.
"""

import logging
import re
import time
from io import StringIO
from pathlib import Path
from typing import Dict, List, Optional

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


def get_boxscore_links(year: int, week: int) -> List[str]:
    """
    Get all boxscore URLs for a specific week.

    Args:
        year: Season year
        week: Week number (1-18)

    Returns:
        List of full URLs to boxscores
    """
    url = f"https://www.pro-football-reference.com/years/{year}/week_{week}.htm"
    logger.info(f"Fetching week {week} summary from {url}")

    resp = robust_request(url)
    if not resp:
        return []

    try:
        soup = BeautifulSoup(resp.text, "lxml")
        links = []

        # Find "Final" links usually in the game summaries
        # They look like: /boxscores/202409050kan.htm
        for a in soup.find_all("a", href=True):
            if "/boxscores/" in a["href"] and a.text == "Final":
                full_url = f"https://www.pro-football-reference.com{a['href']}"
                links.append(full_url)

        # Deduplicate
        links = list(set(links))
        logger.info(f"Found {len(links)} boxscores for Week {week}")
        return links

    except Exception as e:
        logger.error(f"Error parsing week {week} summary: {e}")
        return []


def parse_boxscore(url: str, week: int, year: int) -> pd.DataFrame:
    """
    Parse a PFR boxscore page to extract player stats.

    Args:
        url: URL of the boxscore
        week: Week number
        year: Season year

    Returns:
        DataFrame with combined player stats for the game
    """
    resp = robust_request(url)
    if not resp:
        return pd.DataFrame()

    try:
        # PFR uses comments to hide tables
        # robust approach: requests -> text -> remove comments -> read_html

        # Un-comment hidden tables
        html = resp.text.replace("<!--", "").replace("-->", "")

        dfs = []

        # Define tables we care about and their 'stat_type'
        # keys are table_id substrings to look for
        # Define tables we care about and their 'stat_type'
        # keys are table_id substrings to look for
        target_tables = {
            "player_offense": "offense",
            "player_defense": "defense",
            "returns": "returns",
            "kicking": "kicking",
        }

        soup = BeautifulSoup(html, "lxml")

        for table_id, stat_type in target_tables.items():
            tbl = soup.find("table", id=table_id)
            if tbl:
                try:
                    df = pd.read_html(StringIO(str(tbl)))[0]
                    # Clean up multi-index headers if present
                    if isinstance(df.columns, pd.MultiIndex):
                        df.columns = df.columns.map("_".join)

                    # Standardize columns
                    # We need: Player, Tm, (Stats)

                    df["stat_type"] = stat_type
                    df["game_url"] = url
                    df["week"] = week
                    df["year"] = year

                    # Add to list
                    dfs.append(df)
                    logger.info(f"    Extracted {table_id} with {len(df)} rows")
                except ValueError as e:
                    logger.warning(f"    Failed to read table {table_id}: {e}")
                    continue
            else:
                # It's common for some tables to be missing (e.g. no returns)
                pass

        if not dfs:
            return pd.DataFrame()

        # Concat all found tables
        # Note: A player might appear in multiple tables (e.g. rushing and receiving)
        # We will keep them separate rows for now to be safe, or we can merge.
        # Simplest for "efficiency" is simply to have a "Weekly AV" proxy or just raw stats.
        # But we need a unique identifier. 'Player' name matches are tricky.
        # For now, let's just return the raw stack.

        combined = pd.concat(dfs, ignore_index=True)
        return combined

    except Exception as e:
        logger.error(f"Error parsing boxscore {url}: {e}")
        return pd.DataFrame()


def scrape_season_logs(year: int, start_week: int = 1, end_week: int = 18):
    """Scrape all game logs for a season."""
    all_logs = []

    for week in range(start_week, end_week + 1):
        logger.info(f"Processing Week {week}...")
        links = get_boxscore_links(year, week)

        for link in links:
            logger.info(f"  Parsing {link}...")
            df = parse_boxscore(link, week, year)
            if not df.empty:
                all_logs.append(df)
            time.sleep(12.0)  # Respect rate limits

    if all_logs:
        final_df = pd.concat(all_logs, ignore_index=True)

        # Save raw data
        output_path = f"data/raw/pfr/game_logs_{year}.csv"
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        final_df.to_csv(output_path, index=False)
        logger.info(f"Saved {len(final_df)} rows to {output_path}")
    else:
        logger.warning("No data collected.")


def scrape_history(start_year: int, end_year: int):
    """
    Scrape game logs for a range of years, working backwards.

    Args:
        start_year: Most recent year (e.g. 2024)
        end_year: Oldest year (e.g. 2015)
    """
    logger.info(f"Starting historical scrape from {start_year} back to {end_year}...")

    for year in range(start_year, end_year - 1, -1):
        output_path = Path(f"data/raw/pfr/game_logs_{year}.csv")

        if output_path.exists():
            logger.info(f"Skipping {year}: File already exists at {output_path}")
            continue

        logger.info(f"--- Scraping Season {year} ---")
        try:
            # PFR seasons have 17 or 18 weeks depending on year
            # 2021-Present: 18 weeks
            # Pre-2021: 17 weeks
            last_week = 18 if year >= 2021 else 17

            scrape_season_logs(year, start_week=1, end_week=last_week)

            # Cool down between seasons
            time.sleep(5)

        except Exception as e:
            logger.error(f"Failed to scrape {year}: {e}")


if __name__ == "__main__":
    # Historical scrape working backwards
    # Range: 2025 -> 2015
    scrape_history(2025, 2015)
