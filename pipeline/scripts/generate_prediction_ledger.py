import os
import sys
import json
import uuid
import hashlib
import logging
from datetime import datetime
from pathlib import Path

# Ensure project root is in path
sys.path.append(str(Path(__file__).parent.parent))
from src.db_manager import DBManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def generate_ledger(year: int):
    """
    Extracts the latest predictions from fact_player_efficiency, 
    cryptographically hashes them to prevent hindsight bias,
    and appends them to the immutable BigQuery ledger.
    """
    with DBManager() as db:
        logger.info(f"Extracting Gold Layer predictions for {year}...")
        
        # We need to make sure the target table exists
        db.execute("""
            CREATE TABLE IF NOT EXISTS `nfl_dead_money.immutable_prediction_ledger` (
                ledger_id STRING,
                timestamp TIMESTAMP,
                player_name STRING,
                team STRING,
                year INT64,
                prediction_payload JSON,
                sha256_hash STRING
            )
        """)

        # Fetch current state of facts
        query = f"""
            SELECT 
                player_name, team, year,
                cap_hit_millions, potential_dead_cap_millions, 
                fair_market_value,
                ied_overpayment,
                edce_risk,
                combined_roi_score
            FROM fact_player_efficiency
            WHERE year = {year}
        """
        
        try:
            df = db.fetch_df(query)
            if df.empty:
                logger.warning(f"No records found in fact_player_efficiency for {year}. Cannot generate ledger.")
                return
        except Exception as e:
            logger.error(f"Failed to extract predictions: {e}")
            return
            
        current_time = datetime.utcnow().isoformat()
        
        ledger_records = []
        for _, row in df.iterrows():
            payload = {
                "cap_hit_millions": row.get("cap_hit_millions", 0),
                "potential_dead_cap_millions": row.get("potential_dead_cap_millions", 0),
                "fair_market_value": row.get("fair_market_value", 0),
                "ied_overpayment": row.get("ied_overpayment", 0),
                "edce_risk": row.get("edce_risk", 0),
                "combined_roi_score": row.get("combined_roi_score", 0),
            }
            # Canonical JSON serialization (sorted keys, no spaces)
            payload_str = json.dumps(payload, sort_keys=True, separators=(',', ':'))
            
            # Cryptographic signature
            signature_base = f"{row['player_name']}|{row['year']}|{current_time}|{payload_str}"
            sha256_hash = hashlib.sha256(signature_base.encode('utf-8')).hexdigest()
            
            ledger_records.append({
                "ledger_id": str(uuid.uuid4()),
                "timestamp": current_time,
                "player_name": row['player_name'],
                "team": row['team'],
                "year": int(row['year']),
                "prediction_payload": payload_str,
                "sha256_hash": sha256_hash
            })
            
        import pandas as pd
        df_ledger = pd.DataFrame(ledger_records)
        
        logger.info(f"Hashing complete. Appending {len(df_ledger)} cryptographic records to BigQuery Ledger...")
        
        db.execute("""
            INSERT INTO `nfl_dead_money.immutable_prediction_ledger`
            SELECT * FROM df_ledger
        """, {"df_ledger": df_ledger})
        
        logger.info("✓ SP19-1: Cryptographic Ledger snapshot successfully recorded.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=2026)
    args = parser.parse_args()
    
    generate_ledger(args.year)
