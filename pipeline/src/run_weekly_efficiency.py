import logging
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load Data
LOGS_PATH = "data/raw/pfr/game_logs_2024.csv"
SPOTRAC_PATH = "data/raw/spotrac_player_rankings_2024_2026w05_20260130_183232.csv"

logger.info("Loading data...")
logs = pd.read_csv(LOGS_PATH)
financials = pd.read_csv(SPOTRAC_PATH)


# Clean Financials
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


financials["clean_name"] = financials["player_name"].apply(clean_name)

# Parse Cap Hit
if "total_contract_value_millions" in financials.columns:
    financials["cap_hit_m"] = financials["total_contract_value_millions"]
elif "value" in financials.columns:
    financials["cap_hit_m"] = (
        financials["value"].replace("[\$,]", "", regex=True).astype(float) / 1_000_000
    )
else:
    # Fallback
    financials["cap_hit_m"] = financials["total_contract_value_millions"]

# Weekly Cost
financials["weekly_cost_m"] = financials["cap_hit_m"] / 17


# Clean Logs
def clean_col(col):
    if "Player" in col:
        return "Player"
    if "_Tm" in col:
        return "Team"
    return col


logs.columns = [clean_col(c) for c in logs.columns]

# Fill NaNs
stat_cols = [
    "Passing_Yds",
    "Passing_TD",
    "Passing_Int",
    "Rushing_Yds",
    "Rushing_TD",
    "Receiving_Rec",
    "Receiving_Yds",
    "Receiving_TD",
    "Fumbles_FL",
]

for c in stat_cols:
    if c in logs.columns:
        logs[c] = pd.to_numeric(logs[c], errors="coerce").fillna(0)
    else:
        logs[c] = 0

# Calculate Fantasy Points (PPR)
logs["fantasy_points"] = (
    (logs["Passing_Yds"] * 0.04)
    + (logs["Passing_TD"] * 4)
    + (logs["Passing_Int"] * -2)
    + (logs["Rushing_Yds"] * 0.1)
    + (logs["Rushing_TD"] * 6)
    + (logs["Receiving_Rec"] * 1)
    + (logs["Receiving_Yds"] * 0.1)
    + (logs["Receiving_TD"] * 6)
    - (logs["Fumbles_FL"] * 2)
)

logs["clean_name"] = logs["Player"].apply(clean_name)

# Merge
logger.info("Merging data...")
merged = pd.merge(
    logs, financials, on="clean_name", how="inner", suffixes=("_log", "_fin")
)

# Efficiency: Points per $1M
# Floor cost to avoid division by zero
merged["weekly_efficiency"] = merged["fantasy_points"] / merged["weekly_cost_m"].clip(
    lower=0.03
)

logger.info(f"Merged {len(merged)} records.")

# Viz
top_players = [
    "Lamar Jackson",
    "Josh Allen",
    "Saquon Barkley",
    "Justin Jefferson",
    "CeeDee Lamb",
]
subset = merged[merged["Player"].isin(top_players)].sort_values(["Player", "week"])

plt.figure(figsize=(12, 6))
sns.lineplot(data=subset, x="week", y="weekly_efficiency", hue="Player", marker="o")
plt.title("Weekly Efficiency Trends (2024 Weeks 1-2 Sample)")
plt.ylabel("Efficiency (Points / $1M)")
plt.xlabel("Week")
plt.xticks([1, 2])
plt.legend(title="Player")

PLOT_PATH = "data/processed/weekly_efficiency_trends.png"
Path(PLOT_PATH).parent.mkdir(parents=True, exist_ok=True)
plt.savefig(PLOT_PATH)
logger.info(f"Saved plot to {PLOT_PATH}")
