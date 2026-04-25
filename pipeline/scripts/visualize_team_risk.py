import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import glob
import os


def generate_risk_chart():
    # 1. Load Data
    path = "data/raw/dead_money/"
    all_files = glob.glob(os.path.join(path, "team_cap_*.csv"))

    dfs = []
    for filename in all_files:
        df = pd.read_csv(filename)
        dfs.append(df)

    if not dfs:
        print("No data found.")
        return

    full_df = pd.concat(dfs, ignore_index=True)

    # Ensure sorted by year
    full_df = full_df.sort_values("year")

    # 2. Key Metrics: Dead Cap % Over Time
    # We want to highlight specific teams:
    # - Risk Buckets: ARI, DEN, PHI (High Risk) vs SEA, DET (Efficient)
    # - Super Bowl Winners (to show if they had low dead cap)

    sb_winners = {
        2015: "DEN",  # actually 2015 season, SB 2016
        2016: "NE",
        2017: "PHI",
        2018: "NE",
        2019: "KC",
        2020: "TB",
        2021: "LAR",
        2022: "KC",
        2023: "KC",
        2024: "KC",  # Prediction? Or just 2023 season data. Let's use 2023 winner.
    }

    highlight_teams = ["ARI", "DEN", "SEA", "NE", "KC"]

    plt.figure(figsize=(12, 8))
    sns.set_theme(style="whitegrid")

    # Plot all teams faintly
    for team in full_df["team"].unique():
        team_data = full_df[full_df["team"] == team]
        if team not in highlight_teams:
            plt.plot(
                team_data["year"], team_data["dead_cap_pct"], color="grey", alpha=0.1
            )

    # Plot highlights
    colors = {
        "ARI": "red",
        "DEN": "orange",
        "SEA": "limegreen",
        "NE": "navy",
        "KC": "gold",
    }

    for team in highlight_teams:
        team_data = full_df[full_df["team"] == team]
        plt.plot(
            team_data["year"],
            team_data["dead_cap_pct"],
            label=team,
            color=colors.get(team, "blue"),
            linewidth=2.5,
            marker="o",
        )

    # Annotate SB Winners
    for year, team in sb_winners.items():
        if year in full_df["year"].values:
            # Find that team's dead cap that year
            winner_data = full_df[(full_df["year"] == year) & (full_df["team"] == team)]
            if not winner_data.empty:
                val = winner_data["dead_cap_pct"].values[0]
                plt.annotate(
                    f"🏆 {team}",
                    (year, val),
                    xytext=(0, 10),
                    textcoords="offset points",
                    ha="center",
                    fontsize=9,
                    fontweight="bold",
                )

    plt.title(
        "The 'Toxic Debt' Trap: Team Dead Cap % Over Time (2015-2024)",
        fontsize=16,
        fontweight="bold",
    )
    plt.ylabel("Dead Cap % (Wasted Payroll)", fontsize=12)
    plt.xlabel("Season", fontsize=12)
    plt.legend(title="Key Franshises", loc="upper left")

    # Highlight the "Safety Zone" (under 10%)
    plt.axhspan(0, 10, color="green", alpha=0.05, label="Efficient Zone")

    # Save
    output_path = "reports/team_risk_history.png"
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    print(f"Chart saved to {output_path}")


if __name__ == "__main__":
    generate_risk_chart()
