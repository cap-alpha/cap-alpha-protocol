#!/usr/bin/env python3
"""
League-Wide Cut Protocol
Author: Cap Alpha Protocol (Automated)

Objective: Generate a team-by-team audit of High-Cap Liabilities (> $10M) for potential release/trade.
"""

from src.db_manager import DBManager
import pandas as pd
import sys


def format_currency(val_millions):
    return f"${val_millions:.1f}M"


def run_league_audit():
    DB_PATH = "data/duckdb/nfl_production.db"
    con = DBManager()

    print("running League-Wide Cut Audit...", file=sys.stderr)

    # 1. Query: The "Risk Exposure" Logic (Same as Red List)
    # Grouped by Team
    query = """
        WITH unique_preds AS (
            SELECT player_name, year, MAX(predicted_risk_score) as risk_score
            FROM prediction_results
            GROUP BY player_name, year
        ),
        unique_contracts AS (
            SELECT player_name, year, team, position, MAX(cap_hit_millions) as cap_hit_millions
            FROM silver_spotrac_contracts
            GROUP BY player_name, year, team, position
        )
        SELECT 
            c.team,
            c.player_name,
            c.position,
            CAST(c.cap_hit_millions AS DECIMAL(10,1)) as contract_value,
            p.risk_score,
            (c.cap_hit_millions * p.risk_score) as risk_exposure_millions
        FROM unique_contracts c
        JOIN unique_preds p
          ON c.player_name = p.player_name
          AND c.year = p.year
        WHERE c.year = 2025
          AND c.cap_hit_millions >= 10.0
          AND p.risk_score > 0.5 -- Only show risky assets
        ORDER BY c.team, risk_exposure_millions DESC
    """

    df = con.execute(query).df()

    if df.empty:
        print("No high-risk players found.")
        return

    # 2. Report Generation
    print("# League-Wide Roster Audit: 2026 Cut Candidates")
    print(
        "> **Scope**: Players with Cap Hit > $10M and Risk Score > 0.5 (High Correctness Confidence)."
    )
    print("> **Metric**: `Risk Exposure = Contract Value * Risk Score`\n")

    teams = sorted(df["team"].unique())

    for team in teams:
        team_df = df[df["team"] == team]
        if team_df.empty:
            continue

        print(f"## {team}")
        headers = ["Player", "Pos", "Contract Value", "Risk Score", "Risk Exposure"]
        print(f"| {' | '.join(headers)} |")
        print(f"| {' | '.join(['---']*len(headers))} |")

        for _, row in team_df.iterrows():
            score = row["risk_score"]
            icon = "🟡"
            if score > 0.8:
                icon = "🔴"

            print(
                f"| {row['player_name']} | {row['position']} | "
                f"{format_currency(row['contract_value'])} | {icon} {score:.2f} | "
                f"**{format_currency(row['risk_exposure_millions'])}** |"
            )
        print("\n")


if __name__ == "__main__":
    run_league_audit()
