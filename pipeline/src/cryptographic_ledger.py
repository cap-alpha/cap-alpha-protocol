import hashlib
import json
import logging
from datetime import datetime
from src.db_manager import DatabaseManager

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

def generate_merkle_root(hashes: list) -> str:
    """Generate a simple Merkle Root from a list of SHA-256 hashes."""
    if not hashes:
        return ""
    if len(hashes) == 1:
        return hashes[0]
    
    new_level = []
    for i in range(0, len(hashes), 2):
        left = hashes[i]
        right = hashes[i+1] if i+1 < len(hashes) else left
        combined = left + right
        new_level.append(hashlib.sha256(combined.encode('utf-8')).hexdigest())
    
    return generate_merkle_root(new_level)

def hash_predictions_to_ledger():
    db = DatabaseManager()
    
    # 1. Ensure Audit Ledger tables exist
    db.execute("""
        CREATE TABLE IF NOT EXISTS gold_layer.audit_ledger_entries (
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
        CREATE TABLE IF NOT EXISTS gold_layer.audit_ledger_blocks (
            block_id VARCHAR PRIMARY KEY,
            year INTEGER,
            week INTEGER,
            merkle_root VARCHAR,
            transaction_count INTEGER,
            created_at TIMESTAMP
        );
    """)
    
    # 2. Extract latest un-hashed predictions
    try:
        latest = db.fetch_all("SELECT MAX(year) as y, MAX(week) as w FROM gold_layer.prediction_results;")
        if not latest or not latest[0]['y']:
            logger.warning("No predictions found to hash.")
            return
            
        year = latest[0]['y']
        week = latest[0]['w']
        
        # Check if this block already exists
        existing = db.fetch_all(f"SELECT block_id FROM gold_layer.audit_ledger_blocks WHERE year = {year} AND week = {week}")
        if existing and len(existing) > 0:
            logger.info(f"Block for {year} W{week} already exists in ledger. Skipping hashing.")
            return
            
        logger.info(f"Hashing predictions for {year} W{week} into Cryptographic Ledger...")
        
        preds = db.fetch_all(f"""
            SELECT player_name, predicted_risk_score, fair_market_value, edce_risk
            FROM gold_layer.prediction_results
            WHERE year = {year} AND week = {week}
        """)
        
        if not preds:
            logger.warning("No rows returned for the latest week.")
            return

        signatures = []
        timestamp = datetime.utcnow().isoformat()
        
        for p in preds:
            payload = {
                "player_name": p['player_name'],
                "year": year,
                "week": week,
                "risk_score": float(p['predicted_risk_score']) if p['predicted_risk_score'] is not None else 0.0,
                "fmv": float(p['fair_market_value']) if p['fair_market_value'] is not None else 0.0,
                "edce": float(p['edce_risk']) if p['edce_risk'] is not None else 0.0,
                "timestamp": timestamp
            }
            payload_str = json.dumps(payload, sort_keys=True)
            signature = hashlib.sha256(payload_str.encode('utf-8')).hexdigest()
            
            signatures.append(signature)
            
            # Insert entry
            db.execute(f"""
                INSERT INTO gold_layer.audit_ledger_entries
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
            
        # 3. Enhance ledger with intelligence signals
        logger.info("Hashing intelligence signals into Ledger...")
        signals = db.fetch_all("""
            SELECT player_name, event_type, resolution_high_level as intelligence_text, sentiment_score, event_date as recorded_at
            FROM player_timeline_events
            WHERE event_date >= CURRENT_DATE - INTERVAL '7 DAYS'
        """)
        
        if signals:
            for s in signals:
                signal_payload = {
                    "player_name": s['player_name'],
                    "year": year,
                    "week": week,
                    "event_type": s.get('event_type', 'Unknown'),
                    "intelligence_text": str(s.get('intelligence_text', '')),
                    "sentiment_score": float(s['sentiment_score']) if s.get('sentiment_score') is not None else 0.0,
                    "recorded_at": str(s.get('recorded_at', timestamp)),
                    "timestamp": timestamp
                }
                payload_str = json.dumps(signal_payload, sort_keys=True)
                signature = hashlib.sha256(payload_str.encode('utf-8')).hexdigest()
                
                signatures.append(signature)
                
                db.execute(f"""
                    INSERT INTO gold_layer.audit_ledger_entries
                    VALUES (
                        '{signature[:16]}', 
                        '{s['player_name'].replace("'", "''")}', 
                        {year}, 
                        {week}, 
                        '{payload_str.replace("'", "''")}', 
                        'INTELLIGENCE',
                        '{signature}',
                        CURRENT_TIMESTAMP
                    )
                """)
        
        
        # Generate Merkle Root
        merkle_root = generate_merkle_root(signatures)
        block_id = f"BLK_{year}_{week}_{merkle_root[:8]}"
        
        db.execute(f"""
            INSERT INTO gold_layer.audit_ledger_blocks
            VALUES (
                '{block_id}',
                {year},
                {week},
                '{merkle_root}',
                {len(signatures)},
                CURRENT_TIMESTAMP
            )
        """)
        
        logger.info(f"Successfully minted Block {block_id} with {len(signatures)} prediction hashes.")
        logger.info(f"Merkle Root: {merkle_root}")

    except Exception as e:
        logger.error(f"Failed to hash ledger: {e}")
        raise

if __name__ == "__main__":
    hash_predictions_to_ledger()
