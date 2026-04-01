"""
Scrape ALL 2024 NFL contracts from Spotrac salary rankings page.

Much more efficient than per-team pages:
- Single page load instead of 32 team pages
- All players ranked by salary cap hit
- Selenium headless with extended waits
"""

import logging
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

RAW_DIR = Path("data/raw")


def get_current_nfl_year() -> int:
    now = datetime.now()
    return now.year if now.month >= 3 else now.year - 1


CURRENT_YEAR = get_current_nfl_year()


class SpotracRankingsScraper:
    """Scrape player contracts from Spotrac rankings page"""

    def __init__(self, headless: bool = True):
        self.headless = headless
        self.driver = None

    def __enter__(self):
        self._initialize_driver()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.driver:
            self.driver.quit()

    def _initialize_driver(self):
        """Initialize Selenium Chrome driver"""
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
        except ImportError:
            raise ImportError("Selenium not installed")

        options = Options()
        if self.headless:
            options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument(
            "user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
        )

        self.driver = webdriver.Chrome(options=options)
        logger.info("✓ Selenium driver initialized")

    def scrape_all_contracts(self, year: int = CURRENT_YEAR) -> pd.DataFrame:
        """
        Scrape salary rankings page - has ALL NFL players ranked by salary cap hit.

        URL: https://www.spotrac.com/nfl/rankings/player/_/year/{year}/sort/cap_total

        Returns DataFrame with:
        - player_name
        - team
        - position
        - year
        - cap_hit_millions (current year cap hit)
        """
        from bs4 import BeautifulSoup
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.support.ui import WebDriverWait

        url = (
            f"https://www.spotrac.com/nfl/rankings/player/_/year/{year}/sort/cap_total"
        )
        logger.info(f"Scraping Spotrac salary rankings: {url}")
        logger.info("  (This is ALL players ranked by salary cap hit - single page)")

        self.driver.set_page_load_timeout(60)
        self.driver.get(url)

        # Wait for table with extended timeout
        logger.info("  Waiting for table to load (up to 45 seconds)...")
        try:
            WebDriverWait(self.driver, 45).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "table tbody tr"))
            )
            logger.info("  ✓ Table found, waiting for full render...")
            time.sleep(5)
        except Exception as e:
            logger.warning(f"  ⚠️ Timeout: {e}")
            logger.info("  Attempting to scroll and trigger rendering...")
            try:
                self.driver.execute_script(
                    "window.scrollBy(0, document.body.scrollHeight);"
                )
                time.sleep(5)
            except:
                pass

        # Scroll through page to load all rows (DataTables lazy loading)
        logger.info("  Scrolling to load all player rows (may take 30+ seconds)...")
        last_height = self.driver.execute_script("return document.body.scrollHeight")
        scrolls = 0
        max_scrolls = 20

        while scrolls < max_scrolls:
            self.driver.execute_script("window.scrollBy(0, 500);")
            time.sleep(0.5)

            new_height = self.driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height
            scrolls += 1

            if scrolls % 5 == 0:
                logger.info(f"    ... scrolled {scrolls*500}px, loading more rows")

        logger.info(f"  ✓ Completed {scrolls} scrolls")

        # Parse page
        soup = BeautifulSoup(self.driver.page_source, "html.parser")

        # Find table
        table = None
        for tbl in soup.find_all("table"):
            if tbl.find("tbody") and tbl.find("tr"):
                # Check if this looks like the rankings table
                first_row = tbl.find("tr")
                cells = first_row.find_all(["td", "th"])
                if len(cells) >= 4:  # Should have player, team, pos, salary columns
                    table = tbl
                    break

        if not table:
            raise Exception("Could not find salary rankings table")

        tbody = table.find("tbody")
        if not tbody:
            raise Exception("Table missing tbody")

        # Extract rows
        rows = []
        logger.info("  Extracting player data...")

        for i, tr in enumerate(tbody.find_all("tr")):
            cells = tr.find_all("td")
            if len(cells) < 4:
                continue

            try:
                # Spotrac rankings table: [Rank] [Player] [Team] [Position] [Cap Hit] ...
                player_name = cells[1].get_text().strip() if len(cells) > 1 else ""
                team = cells[2].get_text().strip() if len(cells) > 2 else ""
                position = cells[3].get_text().strip() if len(cells) > 3 else ""
                cap_hit_text = cells[4].get_text().strip() if len(cells) > 4 else "0"

                if not player_name or not team:
                    continue

                # Parse cap hit (e.g., "$58,030,000" -> 58.03)
                cap_hit = self._parse_salary(cap_hit_text)

                rows.append(
                    {
                        "player_name": player_name,
                        "team": team,
                        "position": position,
                        "year": year,
                        "cap_hit_millions": cap_hit,
                    }
                )

            except Exception as e:
                logger.debug(f"    Error parsing row {i}: {e}")
                continue

        logger.info(f"  ✓ Extracted {len(rows)} player records")

        if len(rows) < 500:
            logger.warning(f"⚠️ Only {len(rows)} players found (expected 1000+)")
            logger.warning("   This may indicate the page didn't fully load")

        return pd.DataFrame(rows)

    def _parse_salary(self, text: str) -> float:
        """Parse salary string like '$58,030,000' to millions"""
        try:
            # Remove $ and commas
            clean = text.replace("$", "").replace(",", "").strip()
            dollars = float(clean)
            return dollars / 1_000_000
        except:
            return 0.0

    def scrape_and_save(self, year: int = CURRENT_YEAR) -> Path:
        """Scrape all contracts and save to CSV"""
        df = self.scrape_all_contracts(year)

        if df.empty or len(df) < 100:
            raise Exception(f"Scraping failed: only {len(df)} records (expected 1000+)")

        # Save
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        now = datetime.utcnow()
        iso = now.isocalendar()
        iso_week = f"{iso.year}w{iso.week:02d}"
        timestamp = now.strftime("%Y%m%d")

        out_path = RAW_DIR / f"spotrac_all_contracts_{year}_{iso_week}_{timestamp}.csv"
        df.to_csv(out_path, index=False)

        logger.info(f"✓ Saved: {out_path}")
        logger.info(f"  Total records: {len(df)}")
        logger.info(f"  Teams: {df['team'].nunique()}")
        logger.info(f"  Avg cap hit: ${df['cap_hit_millions'].mean():.1f}M")
        logger.info(f"  Total cap: ${df['cap_hit_millions'].sum():.1f}M")

        return out_path


def main():
    """CLI"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Scrape NFL player salaries from Spotrac rankings"
    )
    parser.add_argument(
        "--year",
        type=int,
        default=CURRENT_YEAR,
        help="Year to scrape (defaults to active NFL year)",
    )

    args = parser.parse_args()

    try:
        with SpotracRankingsScraper() as scraper:
            scraper.scrape_and_save(args.year)
            logger.info("✓ Scraping complete")
    except Exception as e:
        logger.error(f"✗ Failed: {e}")
        import traceback

        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()
