from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

# Setup
pd.set_option("display.max_columns", 50)
pd.set_option("display.width", 1000)
pd.set_option("display.max_rows", 20)
sns.set_style("whitegrid")

# 1. Load Data
SPOTRAC_PATH = "data/raw/spotrac_player_rankings_2024_2026w05_20260130_183232.csv"
PFR_PATH = "data/raw/pfr/rosters_2024.csv"

print(f"Loading Spotrac data from {SPOTRAC_PATH}")
spotrac = pd.read_csv(SPOTRAC_PATH)
print(f"Loading PFR data from {PFR_PATH}")
pfr = pd.read_csv(PFR_PATH)

print(f"Spotrac rows: {len(spotrac)}")
print(f"PFR rows: {len(pfr)}")


# 2. Clean & Normalize
def clean_name(name):
    if pd.isna(name):
        return ""
    name = (
        name.replace(" Jr.", "")
        .replace(" Sr.", "")
        .replace(" III", "")
        .replace(" II", "")
    )
    return name.strip().lower()


spotrac["clean_name"] = spotrac["player_name"].apply(clean_name)
pfr["clean_name"] = pfr["Player"].apply(clean_name)

# Handle duplicates: keep highest value entry
spotrac = spotrac.sort_values(
    "total_contract_value_millions", ascending=False
).drop_duplicates(subset=["clean_name", "team"])
pfr = pfr.sort_values("AV", ascending=False).drop_duplicates(
    subset=["clean_name", "team"]
)

# Team Mapping Handling
# PFR uses 3 letter codes, Spotrac uses variable.
# We will trust the inner merge on 'clean_name' and 'team' if codes align,
# but we might need to map them if match rate is low.
# Let's check overlap first.
spotrac_teams = set(spotrac["team"].unique())
pfr_teams = set(pfr["team"].unique())
# Common mappings if needed (Spotrac -> PFR or vice versa)
# Spotrac often has 'GNB', 'KAN' etc. PFR has 'GB', 'KC'.
# Let's verify what we have in the loaded data.
print(f"Spotrac Teams Sample: {list(spotrac_teams)[:5]}")
print(f"PFR Teams Sample: {list(pfr_teams)[:5]}")

# 3. Merge
merged = pd.merge(
    spotrac,
    pfr,
    left_on=["clean_name", "team"],
    right_on=["clean_name", "team"],
    how="inner",
)
print(f"Merged rows: {len(merged)}")
print(f"Match rate: {len(merged)/len(spotrac):.1%}")

# 4. Feature Engineering
# Use pre-calculated millions column
if "total_contract_value_millions" in merged.columns:
    merged["salary_m"] = merged["total_contract_value_millions"]
elif "value" in merged.columns:
    merged["salary_m"] = merged["total_contract_value_millions"] = (
        merged["value"].replace("[\$,]", "", regex=True).astype(float) / 1_000_000
    )
else:
    print("Columns available:", merged.columns)
    raise KeyError("Could not find salary column")

# Filter for active
df_active = merged[merged["AV"] > 0].copy()

# Efficiency: AV / Salary ($M)
# Use a floor for salary to avoid exploding ratios for min-salary players
df_active["eff_salary_m"] = df_active["salary_m"].clip(lower=0.8)
df_active["efficiency"] = df_active["AV"] / df_active["eff_salary_m"]

# 5. Analysis
print("\n--- Top 10 High Value Players (AV >= 10) ---")
steals = (
    df_active[df_active["AV"] >= 10].sort_values("efficiency", ascending=False).head(10)
)
print(steals[["player_name", "team", "Pos", "AV", "salary_m", "efficiency"]])

print("\n--- Bottom 10 Low Value Players (AV < 5, Salary > 10M) ---")
overpays = (
    df_active[(df_active["AV"] < 5) & (df_active["salary_m"] > 10)]
    .sort_values("efficiency", ascending=True)
    .head(10)
)
print(overpays[["player_name", "team", "Pos", "AV", "salary_m", "efficiency"]])

# 6. Visualization
plt.figure(figsize=(12, 8))

# Define regions
plt.axvspan(0, 5, ymin=0.5, ymax=1, color="green", alpha=0.1, label="High Value Zone")
plt.axvspan(10, 60, ymin=0, ymax=0.25, color="red", alpha=0.1, label="Overvalued Zone")

# Main scatter plot
sns.scatterplot(data=df_active, x="salary_m", y="AV", hue="Pos", alpha=0.6, s=60)
plt.title("NFL 2024: Performance (AV) vs. Cost (Cap Hit) - Efficiency Analysis")
plt.xlabel("Cap Hit ($M)")
plt.ylabel("Approximate Value (AV)")

# Call out top 10 efficient players (Steals)
steals = (
    df_active[df_active["AV"] >= 10].sort_values("efficiency", ascending=False).head(10)
)
for i, row in steals.iterrows():
    plt.text(
        row["salary_m"] + 0.5,
        row["AV"],
        row["player_name"],
        fontsize=9,
        fontweight="bold",
        color="darkgreen",
    )
    plt.scatter(row["salary_m"], row["AV"], color="green", s=100, marker="*", zorder=5)

# Call out top 10 overrated players (Overpays) - minimal salary filter to focus on big contracts
overpays = (
    df_active[(df_active["salary_m"] >= 10)]
    .sort_values("efficiency", ascending=True)
    .head(10)
)
for i, row in overpays.iterrows():
    plt.text(
        row["salary_m"] + 0.5,
        row["AV"],
        row["player_name"],
        fontsize=9,
        fontweight="bold",
        color="darkred",
    )
    plt.scatter(row["salary_m"], row["AV"], color="red", s=100, marker="X", zorder=5)

plt.legend(bbox_to_anchor=(1.05, 1), loc="upper left")
plt.tight_layout()

PLOT_PATH = "data/processed/efficiency_scatter_enhanced.png"
plt.savefig(PLOT_PATH, dpi=300)
print(f"Saved enhanced plot to {PLOT_PATH}")

# 7. Viz: Overvalued Players (High Salary, Low AV)
overpays = (
    df_active[df_active["salary_m"] >= 5]
    .sort_values("efficiency", ascending=True)
    .head(10)
)

plt.figure(figsize=(10, 6))
sns.barplot(data=overpays, y="player_name", x="efficiency", palette="magma")
plt.title("Top 10 Least Efficient Players (Salary >= $5M)")
plt.xlabel("Efficiency (AV / $1M)")

PLOT_OVER_PATH = "data/processed/overvalued_players.png"
plt.savefig(PLOT_OVER_PATH)
print(f"Saved overvalued plot to {PLOT_OVER_PATH}")

# 8. Viz: Star Power (High Salary, High AV - The Diagonal)
stars = (
    df_active[(df_active["salary_m"] >= 20) & (df_active["AV"] >= 12)]
    .sort_values("AV", ascending=False)
    .head(10)
)

print("\n--- Top 10 'Star Power' Players (The Diagonal) ---")
print(stars[["player_name", "team", "Pos", "AV", "salary_m", "efficiency"]])

# 9. Viz: Positional Clustering (Where do they live?)
# Filter for major positions to avoid clutter
major_positions = ["QB", "WR", "RB", "CB", "DE", "TE", "LB"]
subset = df_active[df_active["Pos"].isin(major_positions)]

plt.figure(figsize=(12, 8))
# Use KDE plot to show density/clusters
sns.kdeplot(
    data=subset,
    x="salary_m",
    y="AV",
    hue="Pos",
    fill=False,
    levels=3,
    thresh=0.2,
    linewidth=2,
)
# Overlay scatter for reference
sns.scatterplot(
    data=subset, x="salary_m", y="AV", hue="Pos", alpha=0.3, s=30, legend=False
)

plt.title("Positional Value Clusters (Cost vs. Performance)")
plt.xlabel("Cap Hit ($M)")
plt.ylabel("Approximate Value (AV)")
plt.xlim(0, 60)
plt.ylim(0, 25)

PLOT_CLUSTER_PATH = "data/processed/positional_clusters.png"
plt.savefig(PLOT_CLUSTER_PATH, dpi=300)
print(f"Saved positional cluster plot to {PLOT_CLUSTER_PATH}")

# Save result
RESULT_PATH = "data/processed/nfl_fair_value_2024.csv"
Path(RESULT_PATH).parent.mkdir(parents=True, exist_ok=True)
merged.to_csv(RESULT_PATH, index=False)
print(f"\nSaved analysis to {RESULT_PATH}")
