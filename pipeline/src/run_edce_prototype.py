import pandas as pd

from src.config import DATA_PROCESSED_DIR
from src.value_metrics import calculate_edce


def main():
    print("Loading Canonical Timeline...")
    path = DATA_PROCESSED_DIR / "canonical_player_timeline.parquet"
    if not path.exists():
        print(f"Error: {path} not found.")
        return

    df = pd.read_parquet(path)

    # Filter for 2025 Active Contracts (Forward Looking)
    TARGET_YEAR = 2025
    d_active = df[df["season"] == TARGET_YEAR].copy()

    if d_active.empty:
        print(f"No {TARGET_YEAR} data found. Available years: {df['season'].unique()}")
        return

    print(f"Analyzing {len(d_active)} players from {TARGET_YEAR}...")

    # Calculate EDCE
    results = calculate_edce(d_active)

    # Sort by EDCE
    top_risk = results.sort_values("EDCE", ascending=False).head(20)

    print("\n-------------------------------------------------------------")
    print(f"TOP 20 CAP RISK FRONTIER (EDCE) - {TARGET_YEAR} Forecast")
    print("-------------------------------------------------------------")
    print(
        f"{'Player':<25} {'Pos':<5} {'Age':<5} {'Threshold':<10} {'Prob_Decline':<15} {'Exposure($M)':<15} {'EDCE($M)':<15}"
    )
    print("-" * 100)

    for _, row in top_risk.iterrows():
        print(
            f"{row['clean_name']:<25} {row['position']:<5} {row['age']:<5.1f} {row['risk_age_threshold']:<10.0f} {row['prob_decline']:<15.2%} {row['exposure_basis']:<15.1f} {row['EDCE']:<15.1f}"
        )

    # Outlier Check: Kyler Murray
    print("\n[Validation] Kyler Murray Check:")
    kyler = results[results["clean_name"] == "kyler murray"]
    if not kyler.empty:
        r = kyler.iloc[0]
        print(
            f"Name: {r['clean_name']}, Age: {r['age']}, Prob: {r['prob_decline']:.2f}, Exposure: {r['exposure_basis']}, EDCE: {r['EDCE']:.2f}"
        )


if __name__ == "__main__":
    main()
