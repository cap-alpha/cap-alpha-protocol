import sys
import os
import pandas as pd

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from src.pfr_scraper import fetch_pfr_tables


def check_pfr_columns():
    # Check Kansas City 2024 as robust test case
    url = "https://www.pro-football-reference.com/teams/kan/2024_roster.htm"
    print(f"Fetching tables from {url}...")

    tables = fetch_pfr_tables(url)
    print(f"Found {len(tables)} tables: {list(tables.keys())}")

    for name, df in tables.items():
        print(f"\n--- Table: {name} ---")
        print(f"Columns: {list(df.columns)}")
        # Check for keywords
        if any(
            c
            for c in df.columns
            if "Sack" in str(c) or "Int" in str(c) or "Sk" in str(c)
        ):
            print(">>> FOUND DEFENSIVE STATS CANDIDATE")
            print(df.head(3))


if __name__ == "__main__":
    check_pfr_columns()
