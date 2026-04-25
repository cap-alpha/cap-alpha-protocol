#!/usr/bin/env python3
"""
The Middle Class Squeeze: Red List Generator
Author: Cap Alpha Protocol (Automated)

Objective: Identify players with Cap Hit > $10M who are delivering negative ROI.
Target Audience: GM, Owner
"""
from src.db_manager import DBManager
import pandas as pd
import sys

# Aesthetic formatting (Rich Text / ASCII)
def format_currency(val_millions):
    return f"${val_millions:.1f}M"

def run_squeeze_analysis():
    con = DBManager()
    
    print("running Middle Class Squeeze Analysis...", file=sys.stderr)
    
    # 1. Query: The "Risk Exposure" Logic
    # Source: silver_spotrac_contracts (Valid Cap) + prediction_results (Valid Risk)
    
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
            c.player_name,
            c.team,
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
        ORDER BY risk_exposure_millions DESC
        LIMIT 20
    """
    
    df = con.execute(query).df()
    
    if df.empty:
        print("No >$10M players found with risk data.")
        return

    # 2. "Chart Pop" - Beautiful Output Generation
    print("\n# The Red List: Top 20 Contract Risks (2025)")
    print("> **Directive**: Identify High-Value Assets (> $10M) with highest Model Risk.")
    print("> **Metric**: `Total Risk Exposure = Contract Value * Risk Score`")
    print("> *Note: Values reflect Total Contract Value committed.*\n")
    
    # Format for Markdown Table
    headers = ["Player", "Pos", "Team", "Contract Value", "Risk Score", "Total Risk Exposure"]
    
    # Create rows
    print(f"| {' | '.join(headers)} |")
    print(f"| {' | '.join(['---']*len(headers))} |")
    
    for _, row in df.iterrows():
        # Status icon
        score = row['risk_score']
        icon = "🟢"
        if score > 0.5: icon = "🟡"
        if score > 0.8: icon = "🔴"
        
        # Format values
        print(f"| {row['player_name']} | {row['position']} | {row['team']} | "
              f"{format_currency(row['contract_value'])} | {icon} {score:.2f} | "
              f"**{format_currency(row['risk_exposure_millions'])}** |")

    # 3. Summary Stats
    summary_query = """
        SELECT 
            COUNT(*) as count,
            SUM(c.cap_hit_millions * p.predicted_risk_score) as total_risk_exposure
        FROM silver_spotrac_contracts c
        JOIN prediction_results p 
          ON c.player_name = p.player_name AND c.year = p.year
        WHERE c.year = 2025
          AND c.cap_hit_millions >= 10.0
    """
    stats = con.execute(summary_query).df().iloc[0]
    
    print("\n## Executive Summary")
    print(f"- **High-Cap Assets Audited**: {stats['count']}")
    print(f"- **Total Capital Risk Exposure**: {format_currency(stats['total_risk_exposure'])}")

if __name__ == "__main__":
    run_squeeze_analysis()
