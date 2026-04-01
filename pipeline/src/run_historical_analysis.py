import glob
import logging
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

from src.config import DATA_PROCESSED_DIR, VIZ_DIR

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Constants
YEARS = range(2015, 2025)
OUTPUT_DIR = VIZ_DIR
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Cap History (Approx)
CAP_HISTORY = {
    2015: 143.28,
    2016: 155.27,
    2017: 167.00,
    2018: 177.20,
    2019: 188.20,
    2020: 198.20,
    2021: 182.50,
    2022: 208.20,
    2023: 224.80,
    2024: 255.40,
}


def clean_name(name):
    if pd.isna(name):
        return ""
    name = (
        str(name)
        .replace(" Jr.", "")
        .replace(" Sr.", "")
        .replace(" III", "")
        .replace(" II", "")
    )
    return name.strip().lower()


def load_data():
    logger.info("Loading Canonical Player Timeline...")
    path = DATA_PROCESSED_DIR / "canonical_player_timeline.parquet"
    if not path.exists():
        logger.error(f"Dataset not found at {path}. Run src/player_timeline.py first.")
        return pd.DataFrame()
    return pd.read_parquet(path)


def generate_plots(merged):
    logger.info("Generating plots...")
    sns.set_style("whitegrid")

    # 1. Positional Trends
    # We rely on 'position' column. Canonical timeline has it.
    major_positions = ["QB", "WR", "RB", "CB", "DE", "TE", "OL"]
    subset = merged[merged["position"].isin(major_positions)]

    plt.figure(figsize=(14, 8))
    sns.lineplot(
        data=subset, x="year", y="efficiency", hue="position", marker="o", ci="sd"
    )
    plt.title("Positional Efficiency Trends (2015-2024)\n(Efficiency = Perf / Cap%)")
    plt.savefig(OUTPUT_DIR / "positional_trends_10yr.png")
    plt.close()

    # 2. Career Arcs
    stars = [
        "tom brady",
        "aaron rodgers",
        "patrick mahomes",
        "aaron donald",
        "todd gurley",
        "julio jones",
    ]
    subset = merged[merged["clean_name"].isin(stars)].sort_values(
        ["clean_name", "year"]
    )

    if not subset.empty:
        plt.figure(figsize=(12, 6))
        sns.lineplot(
            data=subset,
            x="year",
            y="efficiency",
            hue="clean_name",
            marker="o",
            linewidth=2.5,
        )
        plt.title("Career Efficiency Arcs")
        plt.axhline(y=1.0, color="gray", linestyle="--", label="Replacement")
        plt.legend()
        plt.savefig(OUTPUT_DIR / "career_arcs.png")
        plt.close()

    # 3. Replacement Trap (2023 focus for cleanliness)
    recent = (
        merged[(merged["year"] == 2023) & (merged["AV_Proxy"] < 4)]
        .sort_values("cap_pct", ascending=False)
        .head(20)
    )

    if not recent.empty:
        plt.figure(figsize=(10, 6))
        sns.scatterplot(data=recent, x="cap_pct", y="AV_Proxy", hue="position", s=100)
        for i, row in recent.iterrows():
            plt.text(
                row["cap_pct"], row["AV_Proxy"], row["clean_name"], fontsize=8
            )  # clean_name instead of player_name
        plt.title("The Replacement Trap (2023): High Cost, Low Output")
        plt.xlabel("Cap Hit %")
        plt.ylabel("Performance (Est. AV)")
        plt.savefig(OUTPUT_DIR / "replacement_trap.png")
        plt.close()


def main():
    merged = load_data()
    if merged.empty:
        return

    logger.info(f"Loaded {len(merged)} player-seasons.")

    # Calculate Metrics if not present (Cap Pct, Efficiency)
    # Map Cap History
    merged["salary_cap"] = merged["season"].map(CAP_HISTORY)
    merged["cap_pct"] = (merged["cap_hit"] / merged["salary_cap"]) * 100

    # Efficiency = AV / Cap Pct
    # Avoid div by zero
    merged["efficiency"] = merged["AV_Proxy"] / merged["cap_pct"].clip(lower=0.1)

    # Filter for valid data
    merged = merged.dropna(subset=["cap_pct", "efficiency"])

    # Generate Plots
    # Note: 'year' column in timeline is 'season'
    # Rename for compatibility with existing plotting code or update plotting code
    merged["year"] = merged["season"]

    generate_plots(merged)
    logger.info("Done.")


if __name__ == "__main__":
    main()
