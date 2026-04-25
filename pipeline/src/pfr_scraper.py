"""
Pro Football Reference (PFR) scraping utilities.

This module provides functions to scrape player and team data from
Pro Football Reference, including roster information and statistics.
"""

import logging
import re
import time
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Dict, Optional

import pandas as pd
import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


PFR_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def fetch_pfr_tables(url: str, rate_limit: float = 3.0) -> Dict[str, pd.DataFrame]:
    """
    Fetch all tables from a PFR page (including commented tables).

    PFR often wraps tables in HTML comments to prevent easy scraping.
    This function extracts both visible and commented tables.

    Args:
        url: Pro Football Reference URL
        rate_limit: Seconds to wait after request (be respectful)

    Returns:
        Dictionary mapping table IDs to DataFrames
    """
    try:
        resp = requests.get(url, headers=PFR_HEADERS, timeout=20)
        resp.raise_for_status()
        html = resp.text
        tables = {}

        # Parse visible tables
        soup = BeautifulSoup(html, "html.parser")
        for tbl in soup.find_all("table"):
            try:
                df = pd.read_html(StringIO(str(tbl)), flavor="bs4")[0]
                tbl_id = tbl.get("id") or f"table_{len(tables) + 1}"
                tables[tbl_id] = df
                logger.debug(f"Extracted visible table: {tbl_id}")
            except ValueError:
                continue

        # Parse tables inside HTML comments
        comments = re.findall(r"<!--(.*?)-->", html, flags=re.S)
        for block in comments:
            block_soup = BeautifulSoup(block, "html.parser")
            for tbl in block_soup.find_all("table"):
                try:
                    df = pd.read_html(StringIO(str(tbl)), flavor="bs4")[0]
                    tbl_id = tbl.get("id") or f"comment_table_{len(tables) + 1}"
                    if tbl_id not in tables:  # Avoid duplicates
                        tables[tbl_id] = df
                        logger.debug(f"Extracted commented table: {tbl_id}")
                except ValueError:
                    continue

        time.sleep(rate_limit)
        logger.info(f"Extracted {len(tables)} tables from {url}")
        return tables

    except requests.RequestException as e:
        logger.error(f"Error fetching {url}: {e}")
        return {}


# PFR team code mapping
PFR_TEAM_MAP = {
    "ARI": "crd",
    "ATL": "atl",
    "BAL": "rav",
    "BUF": "buf",
    "CAR": "car",
    "CHI": "chi",
    "CIN": "cin",
    "CLE": "cle",
    "DAL": "dal",
    "DEN": "den",
    "DET": "det",
    "GNB": "gnb",
    "HOU": "htx",
    "IND": "clt",
    "JAX": "jax",
    "KAN": "kan",
    "LAC": "sdg",
    "LAR": "ram",
    "LVR": "rai",
    "MIA": "mia",
    "MIN": "min",
    "NOR": "nor",
    "NWE": "nwe",
    "NYG": "nyg",
    "NYJ": "nyj",
    "PHI": "phi",
    "PIT": "pit",
    "SFO": "sfo",
    "SEA": "sea",
    "TAM": "tam",
    "TEN": "oti",
    "WAS": "was",
}

INVERSE_PFR_TEAM_MAP = {v: k for k, v in PFR_TEAM_MAP.items()}


def _extract_team_codes_from_standings(year: int) -> list:
    """Extract team code tuples (abbr, pfr_code) from the season standings page."""
    url = f"https://www.pro-football-reference.com/years/{year}/index.htm"
    resp = requests.get(url, headers=PFR_HEADERS, timeout=20)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "lxml")
    team_codes = []

    for table_id in ["AFC", "NFC"]:
        table = soup.find("table", {"id": table_id})
        if not table:
            continue
        for a in table.find_all("a", href=True):
            m = re.search(r"/teams/([a-z]{3})/\d{4}\.htm", a["href"])
            if not m:
                continue
            pfr_code = m.group(1)
            abbr = INVERSE_PFR_TEAM_MAP.get(pfr_code)
            if not abbr:
                continue
            team_codes.append((abbr, pfr_code))

    # Deduplicate while preserving order
    seen = set()
    deduped = []
    for abbr, code in team_codes:
        if code in seen:
            continue
        seen.add(code)
        deduped.append((abbr, code))
    return deduped


def _build_run_tags(run_timestamp: Optional[datetime] = None) -> tuple[str, str]:
    """Return iso-week tag and timestamp strings for consistent filenames."""
    ts = run_timestamp or datetime.utcnow()
    iso = ts.isocalendar()
    iso_week_tag = f"{iso.year}w{iso.week:02d}"
    timestamp = ts.strftime("%Y%m%d_%H%M%S")
    return iso_week_tag, timestamp


def scrape_pfr_player_rosters(
    year: int,
    save_path: Optional[str] = None,
    run_timestamp: Optional[datetime] = None,
    iso_week_tag: Optional[str] = None,
) -> pd.DataFrame:
    """
    Scrape player roster data from Pro Football Reference for all teams.

    Args:
        year: NFL season year (e.g., 2024)
        save_path: Optional path to save the data as CSV

    Returns:
        DataFrame with player roster information
    """
    url = f"https://www.pro-football-reference.com/years/{year}/index.htm"
    logger.info(f"Scraping PFR player rosters for {year}")

    all_player_data = []

    try:
        team_pairs = _extract_team_codes_from_standings(year)
        if not team_pairs:
            logger.error(f"Could not find team standings for {year}")
            return pd.DataFrame()

        logger.info(f"Found {len(team_pairs)} teams for {year}")

        # Scrape each team's roster
        for team_abbr, pfr_code in team_pairs:
            roster_url = f"https://www.pro-football-reference.com/teams/{pfr_code}/{year}_roster.htm"
            logger.info(f"Fetching roster for {team_abbr} ({pfr_code})")

            team_tables = fetch_pfr_tables(roster_url)

            # Look for roster table
            roster_df = team_tables.get(
                "games_played_team", team_tables.get("roster", pd.DataFrame())
            )

            if roster_df.empty and team_tables:
                # Try first table if specific one not found
                roster_df = list(team_tables.values())[0]

            if not roster_df.empty:
                roster_df["team"] = team_abbr
                roster_df["year"] = year
                all_player_data.append(roster_df)
                logger.info(f"  Collected {len(roster_df)} players from {team_abbr}")
            else:
                logger.warning(f"  No roster data found for {team_abbr}")

        if all_player_data:
            combined_df = pd.concat(all_player_data, ignore_index=True)

            if not save_path:
                iso_tag, timestamp = _build_run_tags(run_timestamp)
                if iso_week_tag:
                    iso_tag = iso_week_tag
                save_dir = Path("data/raw/pfr")
                save_dir.mkdir(parents=True, exist_ok=True)
                save_path = save_dir / f"pfr_rosters_{year}_{iso_tag}_{timestamp}.csv"

            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            combined_df.to_csv(save_path, index=False)
            logger.info(f"Saved {len(combined_df)} player records to {save_path}")

            return combined_df
        else:
            logger.error("No player data collected")
            return pd.DataFrame()

    except Exception as e:
        logger.error(f"Error scraping player rosters: {e}")
        return pd.DataFrame()


def scrape_pfr_team_data(year: int, save_path: Optional[str] = None) -> pd.DataFrame:
    """
    Scrape team data from Pro Football Reference.

    Args:
        year: NFL season year
        save_path: Optional path to save the data as CSV

    Returns:
        DataFrame with team statistics
    """
    url = f"https://www.pro-football-reference.com/years/{year}/index.htm"
    logger.info(f"Scraping PFR team data for {year}")

    try:
        tables = fetch_pfr_tables(url)

        # Extract team stats tables
        team_stats = []
        for table_id, df in tables.items():
            if any(
                keyword in table_id.lower()
                for keyword in ["team", "standings", "afc", "nfc"]
            ):
                df["year"] = year
                df["table_source"] = table_id
                team_stats.append(df)

        if team_stats:
            combined_df = pd.concat(team_stats, ignore_index=True)

            if save_path:
                Path(save_path).parent.mkdir(parents=True, exist_ok=True)
                combined_df.to_csv(save_path, index=False)
                logger.info(f"Saved team data to {save_path}")

            return combined_df
        else:
            logger.warning(f"No team data found for {year}")
            return pd.DataFrame()

    except Exception as e:
        logger.error(f"Error scraping team data: {e}")
        return pd.DataFrame()


def scrape_pfr_historical_data(
    start_year: int,
    end_year: int,
    save_dir: str = "../data/raw/pfr",
    data_type: str = "both",
) -> pd.DataFrame:
    """
    Scrape historical data for multiple years from Pro Football Reference.

    Args:
        start_year: First year to scrape
        end_year: Last year to scrape (inclusive)
        save_dir: Directory to save individual year files
        data_type: 'rosters', 'teams', or 'both'

    Returns:
        Combined DataFrame with all years
    """
    all_years = []

    for year in range(start_year, end_year + 1):
        logger.info(f"\n{'=' * 60}")
        logger.info(f"Processing year: {year}")
        logger.info(f"{'=' * 60}")

        if data_type in ["rosters", "both"]:
            roster_path = f"{save_dir}/rosters_{year}.csv"
            roster_df = scrape_pfr_player_rosters(year, roster_path)

            if not roster_df.empty:
                all_years.append(roster_df)

        if data_type in ["teams", "both"]:
            team_path = f"{save_dir}/teams_{year}.csv"
            team_df = scrape_pfr_team_data(year, team_path)

        # Be respectful with rate limiting
        time.sleep(5)

    if all_years:
        combined_df = pd.concat(all_years, ignore_index=True)

        # Save combined file
        combined_path = f"{save_dir}/combined_{data_type}_{start_year}_{end_year}.csv"
        Path(combined_path).parent.mkdir(parents=True, exist_ok=True)
        combined_df.to_csv(combined_path, index=False)
        logger.info(
            f"\nCombined data: {len(combined_df)} records saved to {combined_path}"
        )

        return combined_df
    else:
        logger.error("No data collected across all years")
        return pd.DataFrame()
