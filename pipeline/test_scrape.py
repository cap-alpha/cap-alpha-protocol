import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
from src.spotrac_scraper_v2 import SpotracScraper


def main():
    try:
        with SpotracScraper(headless=True) as scraper:
            df = scraper.scrape_player_rankings(2026, snapshot=False)
            if not df.empty:
                print(f"SUCCESS: Scraped {len(df)} 2026 player rankings!")
                print(df.head())
            else:
                print("FAILED: Dataframe is empty.")
    except Exception as e:
        print(f"ERROR: {e}")


if __name__ == "__main__":
    main()
