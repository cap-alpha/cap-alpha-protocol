from src.db_manager import DBManager
import logging
import sys
import pandas as pd
from pathlib import Path

# Ensure project root is in path
sys.path.append(str(Path(__file__).parent.parent))
from src.config_loader import get_db_path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

DB_PATH = get_db_path()


def validate_gold_layer():
    logger.info("--- Starting Gold Layer Validation ---")
    db = DBManager(DB_PATH)
    con = db.con

    # 1. Existence Checks
    tables = con.execute("SHOW TABLES").df()["name"].tolist()
    if "fact_player_efficiency" not in tables:
        logger.error("❌ CRITICAL: fact_player_efficiency table missing!")
        return False

    # 2. Null Checks on Key Indicators
    null_counts = con.execute("""
        SELECT 
            COUNT(*) FILTER (WHERE player_name IS NULL) as null_names,
            COUNT(*) FILTER (WHERE year IS NULL) as null_years,
            COUNT(*) FILTER (WHERE age IS NULL) as missing_age_data,
            COUNT(*) FILTER (WHERE cap_hit_millions IS NULL) as null_caps
        FROM fact_player_efficiency
    """).df()

    if null_counts["null_names"].iloc[0] > 0:
        logger.error(
            f"❌ FAILED: {null_counts['null_names'].iloc[0]} null player names found."
        )
        return False

    # 3. Range Validation
    ranges = con.execute("""
        SELECT 
            MIN(year) as min_year,
            MAX(year) as max_year,
            MAX(age) as max_age,
            MIN(age) as min_age
        FROM fact_player_efficiency
    """).df()

    if ranges["max_age"].iloc[0] > 50 or ranges["min_age"].iloc[0] < 18:
        logger.warning(
            f"⚠️ WARNING: Unusual age range found: {ranges['min_age'].iloc[0]} to {ranges['max_age'].iloc[0]}"
        )

    # 4. Schema Consistency
    expected_cols = ["player_name", "year", "cap_hit_millions", "ml_risk_score"]
    actual_cols = (
        con.execute("DESCRIBE fact_player_efficiency").df()["column_name"].tolist()
    )
    missing_cols = [c for c in expected_cols if c not in actual_cols]
    if missing_cols:
        logger.error(f"❌ FAILED: Missing essential columns: {missing_cols}")
        return False

    logger.info("✓ Gold Layer Validation Successful.")
    return True


if __name__ == "__main__":
    if not validate_gold_layer():
        sys.exit(1)
