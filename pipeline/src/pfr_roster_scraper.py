"""
Scrape 2024 NFL rosters from Pro Football Reference (PFR).

PFR is much more reliable than Spotrac:
- Clean HTML (no JavaScript)
- Official data source for historical NFL stats
- Includes: player name, position, age, games played, AV (Approximate Value)

This gets us the demographic/performance data we need to enrich contracts.
"""

import logging
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

RAW_DIR = Path("data/raw")

TEAM_MAP = {
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
    "GB": "gnb",
    "HOU": "htx",
    "IND": "clt",
    "JAX": "jax",
    "KC": "kan",
    "LAC": "sdg",
    "LAR": "ram",
    "LV": "rai",
    "MIA": "mia",
    "MIN": "min",
    "NE": "nwe",
    "NO": "nor",
    "NYG": "nyg",
    "NYJ": "nyj",
    "PHI": "phi",
    "PIT": "pit",
    "SF": "sfo",
    "SEA": "sea",
    "TB": "tam",
    "TEN": "oti",
    "WAS": "was",
}


class PFRRosterScraper:
    """Scrape 2024 NFL rosters from Pro Football Reference"""

    BASE_URL = "https://www.pro-football-reference.com"

    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
        )

    def scrape_all_rosters(self, year: int = 2024) -> pd.DataFrame:
        """
        Scrape all 32 team rosters for a given year.

        Returns DataFrame with:
        - player_name
        - position
        - team (code)
        - year
        - age
        - games_played
        - performance_av (Approximate Value)
        - years_experience
        """
        all_rosters = []
        team_codes = sorted(TEAM_MAP.keys())

        logger.info(f"Scraping PFR rosters for {year} ({len(team_codes)} teams)")

        for team_code in team_codes:
            try:
                roster = self._scrape_team_roster(team_code, year)
                if roster is not None and len(roster) > 0:
                    all_rosters.append(roster)
                    logger.info(f"  ✓ {team_code}: {len(roster)} players")
                else:
                    logger.warning(f"  ⚠️ {team_code}: No roster data found")
            except Exception as e:
                logger.warning(f"  ✗ {team_code}: {e}")
                continue

            # Rate Limit (PFR requires < 20 req/min => > 3s/req)
            import time

            time.sleep(4.5)

        if not all_rosters:
            raise Exception("Failed to scrape any rosters")

        df = pd.concat(all_rosters, ignore_index=True)
        logger.info(f"✓ Total: {len(df)} players from {len(all_rosters)} teams")

        return df

    def _scrape_team_roster(self, team_code: str, year: int) -> pd.DataFrame:
        """Scrape roster for a single team"""

        pfr_team = TEAM_MAP.get(team_code)
        if not pfr_team:
            return None

        # PFR roster URL: /years/2024/teams/kan/2024_roster.htm
        url = f"{self.BASE_URL}/years/{year}/teams/{pfr_team}/{year}_roster.htm"

        logger.debug(f"  Fetching: {url}")

        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, "html.parser")

        # Find roster table
        table = None
        for tbl in soup.find_all("table"):
            if tbl.get("id") == "roster":
                table = tbl
                break

        if not table:
            logger.debug(f"    No roster table found for {team_code}")
            return None

        tbody = table.find("tbody")
        if not tbody:
            return None

        players = []

        for row in tbody.find_all("tr"):
            # Skip section headers
            if row.get("class") and "thead" in str(row.get("class")):
                continue

            cells = row.find_all(["td", "th"])
            if len(cells) < 5:
                continue

            try:
                player_cell = cells[0]
                player_name = player_cell.get_text().strip()
                player_link = player_cell.find("a", href=True)
                player_url = player_link["href"] if player_link else None

                position = cells[1].get_text().strip()

                # Skip if empty
                if not player_name or not position:
                    continue

                # Age and experience
                age_text = cells[4].get_text().strip() if len(cells) > 4 else ""
                age = self._parse_int(age_text)

                exp_text = cells[5].get_text().strip() if len(cells) > 5 else ""
                experience = self._parse_int(exp_text)

                # Games and AV (stats vary by position, but try to find them)
                games_text = cells[8].get_text().strip() if len(cells) > 8 else "0"
                games = self._parse_int(games_text)

                av_text = cells[9].get_text().strip() if len(cells) > 9 else "0"
                av = self._parse_float(av_text)

                players.append(
                    {
                        "player_name": player_name,
                        "player_url": player_url,
                        "position": position,
                        "team": team_code,
                        "year": year,
                        "age": age,
                        "games_played_prior_year": games,
                        "performance_av": av,
                        "years_experience": experience,
                    }
                )

            except Exception as e:
                logger.debug(f"    Error parsing row: {e}")
                continue

        if players:
            return pd.DataFrame(players)
        return None

    def _parse_int(self, text: str) -> int:
        """Parse integer from text"""
        try:
            return int(text.replace("+", "").strip())
        except:
            return None

    def _parse_float(self, text: str) -> float:
        """Parse float from text"""
        try:
            return float(text.strip())
        except:
            return None

    def scrape_and_save(self, year: int = 2024) -> Path:
        """Scrape all rosters and save to CSV"""
        df = self.scrape_all_rosters(year)

        if df.empty:
            raise Exception("Scraping returned empty DataFrame")

        # Save
        RAW_DIR.mkdir(parents=True, exist_ok=True)

        now = datetime.utcnow()
        iso = now.isocalendar()
        iso_week = f"{iso.year}w{iso.week:02d}"
        timestamp = now.strftime("%Y%m%d")

        out_path = RAW_DIR / f"pfr_rosters_{year}_{iso_week}_{timestamp}.csv"
        df.to_csv(out_path, index=False)

        logger.info(f"✓ Saved: {out_path}")
        logger.info(f"  Total players: {len(df)}")
        logger.info(f"  Teams: {df['team'].nunique()}")
        logger.info(f"  Avg age: {df['age'].mean():.1f}")
        logger.info(f"  Avg AV: {df['performance_av'].mean():.1f}")

        return out_path


def main():
    """CLI"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Scrape 2024 NFL rosters from Pro Football Reference"
    )
    parser.add_argument("--year", type=int, default=2024, help="Year to scrape")

    args = parser.parse_args()

    try:
        scraper = PFRRosterScraper()
        scraper.scrape_and_save(args.year)
        logger.info("✓ Scraping complete")
    except Exception as e:
        logger.error(f"✗ Failed: {e}")
        import traceback

        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()
