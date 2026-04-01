import hashlib
import json
import logging
from datetime import datetime

from src.db_manager import DBManager

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


def generate_merkle_root(hashes: list) -> str:
    if not hashes:
        return ""
    if len(hashes) == 1:
        return hashes[0]

    new_level = []
    for i in range(0, len(hashes), 2):
        left = hashes[i]
        right = hashes[i + 1] if i + 1 < len(hashes) else left
        combined = left + right
        new_level.append(hashlib.sha256(combined.encode("utf-8")).hexdigest())

    return generate_merkle_root(new_level)


def hash_predictions_to_ledger():
    db = DBManager()

    db.execute("""
        CREATE TABLE IF NOT EXISTS audit_ledger_entries (
            entry_id VARCHAR PRIMARY KEY,
            player_name VARCHAR,
            year INTEGER,
            week INTEGER,
            payload JSON,
            payload_type VARCHAR,
            signature_hash VARCHAR,
            created_at TIMESTAMP
        );
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS audit_ledger_blocks (
            block_id VARCHAR PRIMARY KEY,
            year INTEGER,
            week INTEGER,
            merkle_root VARCHAR,
            transaction_count INTEGER,
            created_at TIMESTAMP
        );
    """)

    try:
        latest = db.fetch_df(
            "SELECT MAX(year) as y, 0 as w FROM prediction_results"
        ).to_dict("records")
        if not latest or not latest[0]["y"]:
            logger.warning("No predictions found to hash.")
            return

        year = latest[0]["y"]
        week = latest[0]["w"]

        existing = db.fetch_df(
            f"SELECT block_id FROM audit_ledger_blocks WHERE year = {year} AND week = {week}"
        ).to_dict("records")
        if existing and len(existing) > 0:
            logger.info(
                f"Block for {year} W{week} already exists in ledger. Skipping hashing."
            )
            return

        logger.info(
            f"Hashing predictions for {year} W{week} into Cryptographic Ledger..."
        )

        preds = db.fetch_df(f"""
            SELECT player_name, predicted_risk_score
            FROM prediction_results
            WHERE year = {year}
        """).to_dict("records")

        if not preds:
            return

        signatures = []
        timestamp = datetime.utcnow().isoformat()

        for p in preds:
            payload = {
                "player_name": p["player_name"],
                "year": year,
                "week": week,
                "risk_score": (
                    float(p["predicted_risk_score"])
                    if pd.notna(p["predicted_risk_score"])
                    else 0.0
                ),
                "fmv": 0.0,
                "edce": 0.0,
                "timestamp": timestamp,
            }
            payload_str = json.dumps(payload, sort_keys=True)
            signature = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()
            signatures.append(signature)

            db.execute(f"""
                INSERT INTO audit_ledger_entries
                VALUES (
                    '{signature[:16]}', 
                    '{p['player_name'].replace("'", "''")}', 
                    {year}, 
                    {week}, 
                    '{payload_str.replace("'", "''")}', 
                    'PREDICTION',
                    '{signature}',
                    CURRENT_TIMESTAMP
                )
            """)

        merkle_root = generate_merkle_root(signatures)
        block_id = f"BLK_{year}_{week}_{merkle_root[:8]}"

        db.execute(f"""
            INSERT INTO audit_ledger_blocks
            VALUES (
                '{block_id}',
                {year},
                {week},
                '{merkle_root}',
                {len(signatures)},
                CURRENT_TIMESTAMP
            )
        """)

        logger.info(
            f"Successfully minted Block {block_id} with {len(signatures)} prediction hashes."
        )
    except Exception as e:
        logger.error(f"Failed to hash ledger: {e}")


if __name__ == "__main__":
    import pandas as pd

    hash_predictions_to_ledger()
