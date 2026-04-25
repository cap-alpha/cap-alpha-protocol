import sys
import os

# Add pipeline root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../")))

from src.db_manager import DBManager


def main():
    db = DBManager()
    print("Fetching overall stats from fact_player_efficiency...")
    try:
        df = db.fetch_df("SELECT MAX(year), COUNT(*) FROM fact_player_efficiency")
        print(f"Max Year: {df.iloc[0, 0]}, Total Rows: {df.iloc[0, 1]}")
    except Exception as e:
        print("Error:", e)

    print("\nChecking by year:")
    try:
        df = db.fetch_df(
            "SELECT year, COUNT(*) FROM fact_player_efficiency GROUP BY year ORDER BY year DESC"
        )
        print(df)
    except Exception as e:
        print("Error:", e)


if __name__ == "__main__":
    main()
