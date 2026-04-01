import pandas as pd

from src.spotrac_scraper_v2 import SpotracScraper


def main():
    print("Scraping KC 2025 contracts to check Age extraction...")
    with SpotracScraper(headless=True) as scraper:
        # Pass team_list to scrape only KC
        df = scraper.scrape_player_contracts(year=2025, team_list=["KC"])

        print(f"Extracted {len(df)} contracts.")
        if "age" in df.columns:
            print("SUCCESS: 'age' column found!")
            print(df[["player_name", "age", "total_contract_value_millions"]].head())

            # Check for Mahomes
            mahomes = df[df["player_name"].str.contains("Mahomes", case=False)]
            if not mahomes.empty:
                print("\nMahomes Data:")
                print(
                    mahomes[
                        [
                            "player_name",
                            "age",
                            "guaranteed_money_millions",
                            "dead_cap_millions",
                        ]
                    ]
                )
        else:
            print("FAILURE: 'age' column NOT found.")
            print("Columns:", df.columns.tolist())


if __name__ == "__main__":
    main()
