import pandas as pd
import uuid
import logging
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.db_manager import DBManager

logger = logging.getLogger(__name__)

# Simulated LLM interactions based on Personas
MOCK_LEDGER = [
    {
        "simulation_id": str(uuid.uuid4()),
        "persona": "Bettor",
        "asset_id": "player_watson_123",
        "feature_viewed": "Cap Impact",
        "credits_spent": 5,
        "reasoning": "High variance asset, needed deeper insight into injury baseline.",
        "timestamp": "2026-02-20T10:00:00"
    },
    {
        "simulation_id": str(uuid.uuid4()),
        "persona": "NFL Agent",
        "asset_id": "player_mayfield_123",
        "feature_viewed": "Trade Machine",
        "credits_spent": 10,
        "reasoning": "Simulating contract extensions for leverage in negotiations.",
        "timestamp": "2026-02-20T10:05:00"
    },
    {
        "simulation_id": str(uuid.uuid4()),
        "persona": "Fan",
        "asset_id": "player_wilson_123",
        "feature_viewed": "Cap Impact",
        "credits_spent": 0,
        "reasoning": "Paywall hit. Decided not to spend credits on a cut player.",
        "timestamp": "2026-02-20T10:15:00"
    }
]

def run_simulation():
    logger.info("Starting Market Demand Simulation...")
    
    df_ledger = pd.DataFrame(MOCK_LEDGER)
    
    with DBManager() as db:
        # SQLite or DuckDB table
        db.execute("""
            CREATE TABLE IF NOT EXISTS persona_simulation_ledger (
                simulation_id VARCHAR,
                persona VARCHAR,
                asset_id VARCHAR,
                feature_viewed VARCHAR,
                credits_spent INT,
                reasoning VARCHAR,
                timestamp VARCHAR
            )
        """)
        db.execute("INSERT INTO persona_simulation_ledger SELECT * FROM df_ledger", {"df_ledger": df_ledger})
        
    logger.info("Simulation completed and ledger updated.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_simulation()
