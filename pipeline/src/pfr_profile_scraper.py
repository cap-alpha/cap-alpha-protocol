import logging
import random
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd
import requests
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


class PFRProfileScraper:
    BASE_URL = "https://www.pro-football-reference.com"

    def __init__(self, delay_range: tuple = (5, 10)):
        self.delay_range = delay_range
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def scrape_profile(self, player_url: str) -> Dict[str, Any]:
        """Hoover up all available player attributes from PFR."""
        if not player_url.startswith("http"):
            player_url = f"{self.BASE_URL}{player_url}"

        logger.info(f"Hoovering profile: {player_url}")

        try:
            resp = self.session.get(player_url, timeout=15)
            if resp.status_code == 429:
                logger.warning("Rate limited (429). Sleeping for 60s...")
                time.sleep(60)
                resp = self.session.get(player_url, timeout=15)
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "lxml")
            info = soup.find("div", id="meta")
            if not info:
                return {}

            data = {"player_url": player_url}

            # 1. Full Name
            name_tag = info.find("h1")
            if name_tag:
                data["full_name"] = name_tag.get_text().strip()

            # 2. Extract Bio Text (Hoovering pattern)
            p_tags = info.find_all("p")
            for p in p_tags:
                text = p.get_text()

                # Height/Weight
                if "lb" in text and ("cm" in text or '"' in text):
                    hw_match = re.search(r"(\d+-\d+),\s+(\d+)lb", text)
                    if hw_match:
                        data["height"] = hw_match.group(1)
                        data["weight"] = int(hw_match.group(2))

                # Born
                if "Born:" in text:
                    data["birth_date_raw"] = text.replace("Born:", "").strip()
                    # Try to extract date
                    date_match = re.search(r"([A-Z][a-z]+ \d+, \d{4})", text)
                    if date_match:
                        data["birth_date"] = date_match.group(1)

                # College
                if "College:" in text:
                    data["college"] = text.replace("College:", "").strip()

                # Draft
                if "Draft:" in text:
                    data["draft_raw"] = text.replace("Draft:", "").strip()
                    # Extract Round and Pick
                    round_match = re.search(r"(\d+).+round", text)
                    pick_match = re.search(r"(\d+).+overall", text)
                    if round_match:
                        data["draft_round"] = int(round_match.group(1))
                    if pick_match:
                        data["draft_pick"] = int(pick_match.group(1))

                # Experience
                if "Experience:" in text:
                    data["experience_years"] = text.replace("Experience:", "").strip()

            # 3. High School
            hs_tag = info.find("strong", string=re.compile("High School:", re.I))
            if hs_tag:
                data["high_school"] = (
                    hs_tag.parent.get_text().replace("High School:", "").strip()
                )

            return data

        except Exception as e:
            logger.error(f"Error scraping {player_url}: {e}")
            return {}

    def run_batch(self, urls: list, output_file: str):
        """Run a batch of profiles with strict rate-limiting."""
        results = []
        path = Path(output_file)

        # Load existing if exists to resume
        if path.exists():
            results = pd.read_csv(path).to_dict("records")
            processed_urls = {r["player_url"] for r in results}
            urls = [u for u in urls if u not in processed_urls]
            logger.info(f"Resuming... {len(urls)} remaining.")

        for url in urls:
            res = self.scrape_profile(url)
            if res:
                results.append(res)
                # Periodic save
                pd.DataFrame(results).to_csv(output_file, index=False)

            # Strict Jitter (PFR requirement: < 20 req/min)
            sleep_time = random.uniform(*self.delay_range)
            logger.info(f"Waiting {sleep_time:.2f}s...")
            time.sleep(sleep_time)


if __name__ == "__main__":
    # Example usage (to be integrated into the pipeline)
    import sys

    if len(sys.argv) > 1:
        scraper = PFRProfileScraper()
        urls = [sys.argv[1]]
        scraper.run_batch(urls, "data/raw/pfr_test_profiles.csv")
