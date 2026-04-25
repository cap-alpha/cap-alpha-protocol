#!/usr/bin/env python3
print("BOOTSTRAP", flush=True)
"""
Population Density Audit: High vs. Low Cap Coverage
Hypothesis: Our "Data Gap" (123k targets vs 28k features) is driven by missing data for low-cap players.
"""
from src.db_manager import DBManager
import pandas as pd
import sys
import numpy as np

DB_PATH = "data/duckdb/nfl_production.db"


def run_audit():
    import sys

    print("Connecting to DB...", flush=True)
    con = DBManager()

    # 1. Get ALL Targets (The Universe of Players we want to predict)
    print("Loading Target Population...")
    df_targets = con.execute("""
        SELECT player_name, year, cap_hit_millions, position
        FROM fact_player_efficiency
        WHERE year BETWEEN 2015 AND 2025
    """).df()

    # 2. Get Features (The Players we actually know about)
    # We use the same Diagonal Join logic from FeatureStore to be consistent
    print("Loading Feature Population (Diagonal Join)...")
    df_features = con.execute("""
        SELECT DISTINCT player_name, prediction_year as year
        FROM feature_values
        WHERE prediction_year BETWEEN 2015 AND 2025
          AND valid_from <= make_date(prediction_year, 9, 1)
          AND (valid_until > make_date(prediction_year, 9, 1) OR valid_until IS NULL)
    """).df()
    df_features["has_features"] = True

    # 3. Merge
    print(f"Merging {len(df_targets)} targets with {len(df_features)} feature-rows...")
    df = pd.merge(df_targets, df_features, on=["player_name", "year"], how="left")
    df["has_features"] = df["has_features"].fillna(False)

    # 4. Stratify by Cap Hit
    # Buckets: Low (<$2M), Mid ($2M-$10M), High (>$10M)
    conditions = [
        (df["cap_hit_millions"] < 2.0) | df["cap_hit_millions"].isna(),
        (df["cap_hit_millions"] >= 2.0) & (df["cap_hit_millions"] < 10.0),
        (df["cap_hit_millions"] >= 10.0),
    ]
    choices = ["Low Cap (<$2M)", "Mid Cap ($2M-$10M)", "High Cap (>$10M)"]
    df["cap_bucket"] = np.select(conditions, choices, default="Unknown")

    # 5. Calculate Coverage Rates
    summary = (
        df.groupby("cap_bucket")
        .agg(
            total_players=("player_name", "count"),
            players_with_features=("has_features", "sum"),
        )
        .reset_index()
    )

    summary["coverage_pct"] = (
        summary["players_with_features"] / summary["total_players"] * 100
    ).round(1)

    # Sort logically
    order = {"Low Cap (<$2M)": 0, "Mid Cap ($2M-$10M)": 1, "High Cap (>$10M)": 2}
    summary["sort_key"] = summary["cap_bucket"].map(order)
    summary = summary.sort_values("sort_key").drop(columns=["sort_key"])

    print("\n=== Population Coverage Strategy Audit ===")
    print(summary.to_string(index=False))

    # 6. Check Year Trend for Low Cap
    print("\n=== Low Cap (<$2M) Coverage by Year ===")
    low_cap = df[df["cap_bucket"] == "Low Cap (<$2M)"]
    trend = (
        low_cap.groupby("year").agg(coverage_pct=("has_features", "mean")).reset_index()
    )
    trend["coverage_pct"] = (trend["coverage_pct"] * 100).round(1)
    print(trend.to_string(index=False))

    # 7. Analyze Performance by Bucket (if predictions exist)
    print("\n=== Performance by Cap Bucket (R2 Analysis) ===")
    try:
        # Join predictions with actuals (since prediction_results lacks context)
        df_preds = con.execute("""
            SELECT 
                p.player_name, 
                p.year, 
                f.cap_hit_millions, 
                f.edce_risk, 
                p.predicted_risk_score
            FROM prediction_results p
            JOIN fact_player_efficiency f 
              ON p.player_name = f.player_name 
              AND p.year = f.year
            WHERE p.year BETWEEN 2018 AND 2025
        """).df()

        if df_preds.empty:
            print("No prediction results found.")
            return

        # Apply same buckets
        conditions = [
            (df_preds["cap_hit_millions"] < 2.0) | df_preds["cap_hit_millions"].isna(),
            (df_preds["cap_hit_millions"] >= 2.0)
            & (df_preds["cap_hit_millions"] < 10.0),
            (df_preds["cap_hit_millions"] >= 10.0),
        ]
        choices = ["Low Cap (<$2M)", "Mid Cap ($2M-$10M)", "High Cap (>$10M)"]
        df_preds["cap_bucket"] = np.select(conditions, choices, default="Unknown")

        def calc_r2(g):
            if len(g) < 2:
                return np.nan
            y_true = g["edce_risk"]
            y_pred = g["predicted_risk_score"]
            ss_res = np.sum((y_true - y_pred) ** 2)
            ss_tot = np.sum((y_true - np.mean(y_true)) ** 2)
            if ss_tot == 0:
                return 0.0  # Avoid div/0
            return 1 - (ss_res / ss_tot)

        perf = df_preds.groupby("cap_bucket").apply(calc_r2).reset_index()
        perf.columns = ["cap_bucket", "r2_score"]

        # Add counts
        counts = df_preds.groupby("cap_bucket").size().reset_index(name="n")
        perf = pd.merge(perf, counts, on="cap_bucket")

        # Sort
        order = {"Low Cap (<$2M)": 0, "Mid Cap ($2M-$10M)": 1, "High Cap (>$10M)": 2}
        perf["sort_key"] = perf["cap_bucket"].map(order)
        perf = perf.sort_values("sort_key").drop(columns=["sort_key"])

        print(perf.to_string(index=False))

        # --- SACROSANCT OBSERVABILITY GATE ---
        high_cap_r2 = perf[perf["cap_bucket"] == "High Cap (>$10M)"]["r2_score"].values
        if (
            len(high_cap_r2) > 0
            and not np.isnan(high_cap_r2[0])
            and high_cap_r2[0] < 0.85
        ):
            # Deliberately raise Exception so Dagster/Airflow halts all downstream deployments
            raise Exception(
                f"CRITICAL QUALITY FAILURE: High Cap ML Predictive Accuracy R² dropped to {high_cap_r2[0]:.3f} (Threshold >= 0.85). Pipeline execution halted manually via population_audit."
            )

        print(
            "✓ Observability Gate Passed: High-Cap Model precision is highly predictive."
        )

    except Exception as e:
        print(f"Could not analyze predictions: {e}")
        raise e


if __name__ == "__main__":
    run_audit()
