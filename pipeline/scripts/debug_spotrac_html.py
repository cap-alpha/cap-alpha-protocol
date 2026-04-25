import pandas as pd
from src.spotrac_scraper_v2 import SpotracScraper
from bs4 import BeautifulSoup
import os


def debug_parsing():
    year = 2025
    url = f"https://www.spotrac.com/nfl/rankings/player/_/year/{year}/sort/cap_total"

    with SpotracScraper(headless=True) as scraper:
        scraper.driver.get(url)
        import time

        time.sleep(5)
        html = scraper.driver.page_source

        soup = BeautifulSoup(html, "html.parser")
        items = soup.find_all("li", class_="list-group-item")
        if items:
            item = items[1]  # Stafford is usually #2 in 2025
            print("--- HTML BLOB ---")
            print(item.prettify())
            print("--- TEXT NODES ---")
            for s in item.find_all(string=True):
                if s.strip():
                    print(f"'{s.strip()}'")

            full_text = item.get_text(" ", strip=True)
            print(f"--- FULL TEXT: {full_text}")


if __name__ == "__main__":
    debug_parsing()
