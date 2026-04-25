from src.db_manager import DBManager
import pandas as pd
from sklearn.metrics import r2_score
import sys
import os

# Set DB Path (assuming local execution from project root)
DB_PATH = os.getenv("DB_PATH", "data/duckdb/nfl_production.db")


def analyze_r2_by_segment():
    print(f"Connecting to database at {DB_PATH}...")

    if not os.path.exists(DB_PATH):
        print(f"Error: Database not found at {DB_PATH}")
        sys.exit(1)

    try:
        con = DBManager()

        # Query: Get Actual vs Predicted (Fair Market Value)
        # Assuming 'fair_market_value' is the 'prediction' and we need a ground truth 'production' value?
        # OR: Is 'fair_market_value' the ground truth and 'cap_hit_millions' the cost?
        #
        # Re-reading the "Insight": "high cap players over 2M were the ones with the real signal"
        # This implies the MODEL (predicting value) works better on high cap players.
        # R2 usually compares (Actual Value) vs (Predicted Value).
        # We need to know what the 'Target' was.
        #
        # Let's check the schema or assumption.
        # Usually: Target = AAV (Average Annual Value) or future Cap Hit?
        # Or is it: Prediction = Performance Metric (Value) vs Actual = Contract (Cost)?
        #
        # Let's assume we are validating the "Market Efficiency" model.
        # R2 = 1 - (SS_res / SS_tot)
        # where y_true = actual production value (calculated from stats)
        # and y_pred = contract APY (market value).
        #
        # If 'fair_market_value' in the gold table IS the production value (calculated from stats),
        # and 'cap_hit_millions' is the market cost.
        # Then R2 checks how well 'Cost' explains 'Production' (Market Efficiency).

        print("Fetching data (Cap Hit vs FMV)...")
        df = con.execute("""
            SELECT 
                player_name, 
                year, 
                cap_hit_millions as cv,  -- Contract Value (Cost)
                fair_market_value as pv  -- Production Value (Stats)
            FROM fact_player_efficiency
            WHERE year >= 2015 
              AND cap_hit_millions > 0 
              AND fair_market_value IS NOT NULL
        """).df()

        print(f"Total Rows: {len(df)}")

        # Segment 1: High Cap (> $2M)
        df_high = df[df["cv"] > 2.0]

        # Segment 2: Low Cap (<= $2M)
        df_low = df[df["cv"] <= 2.0]

        print("\n--- RESULTS ---")

        if not df_high.empty:
            r2_high = r2_score(df_high["pv"], df_high["cv"])  # Does Cost predict Value?
            # Or is it Does Value predict Cost? (Usually Value -> Cost in efficient market)
            # Let's treat 'CV' as the Prediction of 'PV' (Value).
            # Actually, standard is: y_true (outcome) vs y_pred (model).
            # If we claim "Market is Efficient", then Cost (Market) should predict Value (Production).
            # Let's stick to standard: r2_score(y_true=pv, y_pred=cv)

            print(f"Segment: High Cap (>$2M) | N={len(df_high)}")
            print(f"R2 Score: {r2_high:.4f}")
        else:
            print("Segment: High Cap (>$2M) | N=0")

        if not df_low.empty:
            r2_low = r2_score(df_low["pv"], df_low["cv"])
            print(f"Segment: Low Cap (<=$2M) | N={len(df_low)}")
            print(f"R2 Score: {r2_low:.4f}")
        else:
            print("Segment: Low Cap (<=$2M) | N=0")

        print("\n----------------\n")

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    analyze_r2_by_segment()
