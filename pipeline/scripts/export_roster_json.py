from src.db_manager import DBManager
import json
import logging
from pathlib import Path
import pandas as pd
from src.config_loader import get_db_path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

EXPORT_PATH = Path("data/roster_dump.json")


def export_roster_json():
    db_path = get_db_path()
    logger.info(f"Connecting to {db_path} for JSON export...")
    con = DBManager()

    # DEBUG: Print columns to log to understand available fields for Cut Calculator
    try:
        logger.info(
            f"Fact Cols: {con.execute('DESCRIBE fact_player_efficiency').df()['column_name'].tolist()}"
        )
        logger.info(
            f"Silver Cols: {con.execute('DESCRIBE silver_spotrac_contracts').df()['column_name'].tolist()}"
        )
    except Exception as e:
        logger.warning(f"Could not describe tables: {e}")

    # Query matching the schema expected by web/app/actions.ts (reverted version)
    # actions.ts expects: player_name, team, position, cap_hit_millions, edce_risk, fair_market_value
    # It also handles 'ml_risk_score' if 'edce_risk' is missing or as alternative, but let's provide both or standard.
    # The actions.ts mapper: risk_score: d.ml_risk_score || d.edce_risk
    # surplus_value: d.fair_market_value

    query = """
        SELECT 
            f.player_name, 
            f.team, 
            f.position, 
            f.cap_hit_millions,
            f.dead_cap_millions as dead_cap_current_year, -- Likely just the 'Dead Cap' column from Spotrac (which is often 0 unless already cut)
            f.potential_dead_cap_millions as dead_cap_if_cut,
            f.signing_bonus_millions,
            -- Normalize Risk Score: (Risk $ / Cap Hit $) -> Ratio 0.0 to 1.0 (or >1.0 for toxic)
            CASE 
                WHEN f.cap_hit_millions > 0 THEN 
                    LEAST(GREATEST(COALESCE(p.predicted_risk_score, f.edce_risk) / f.cap_hit_millions, 0.0), 1.0)
                ELSE 0.0 
            END as risk_score,
            p.predicted_risk_score as raw_risk_dollars,
            f.edce_risk,
            f.fair_market_value,
            f.fair_market_value - f.cap_hit_millions as surplus_value
        FROM fact_player_efficiency f
        LEFT JOIN prediction_results p 
          ON f.player_name = p.player_name 
          AND f.year = p.year 
          AND f.team = p.team
        WHERE f.year = 2025
        ORDER BY f.cap_hit_millions DESC
    """

    df = con.execute(query).df()

    if df.empty:
        logger.warning("No data found for 2025! JSON dump will be empty.")

    # Calculate Cut Calculator Fields
    # Heuristic: Post-June 1 Dead Cap (Year 1) is typically the current year's prorated signing bonus.
    # The 'savings' is the Cap Hit minus this Dead Cap.
    # Future dead cap (acceleration) is pushed to Year 2.

    # Pre-June 1: Take it all on the chin now.
    df["dead_cap_pre_june1"] = df["dead_cap_if_cut"].fillna(0)
    df["savings_pre_june1"] = df["cap_hit_millions"] - df["dead_cap_pre_june1"]

    # Post-June 1: Split the pain.
    # We use 'signing_bonus_millions' as the proxy for the "Year 1 Dead Cap" content.
    df["dead_cap_post_june1"] = df["signing_bonus_millions"].fillna(0)
    df["savings_post_june1"] = df["cap_hit_millions"] - df["dead_cap_post_june1"]

    # CRITICAL: Sanitize NaN/Inf values before JSON export.
    # Python's json.dump outputs 'NaN' for float NaN, which is INVALID JSON
    # and will break webpack, browsers, and any downstream consumer.
    numeric_cols = df.select_dtypes(include=["float64", "float32"]).columns
    df[numeric_cols] = (
        df[numeric_cols].fillna(0).replace([float("inf"), float("-inf")], 0)
    )

    # Convert to list of dicts
    data = df.to_dict(orient="records")

    # Write to JSON
    EXPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with open(EXPORT_PATH, "w") as f:
        json.dump(data, f, indent=2)

    logger.info(f"✓ Roster data exported to {EXPORT_PATH} ({len(data)} records)")


if __name__ == "__main__":
    export_roster_json()
