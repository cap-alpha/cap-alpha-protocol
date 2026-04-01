import json
import logging
import os
import sys
from datetime import datetime

import pandas as pd

# Add pipeline directory to path so we can import src
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.db_manager import DBManager

logger = logging.getLogger(__name__)

# Simulated raw ingest
MOCK_TWEETS = [
    {
        "timestamp": "2026-10-10",
        "raw_text": "Rumors circling that the team chemistry is collapsing after Baker's latest comments.",
        "source": "NFL_Insider",
    },
    {
        "timestamp": "2026-10-12",
        "raw_text": "Watson seen limping heavily at practice, HC downplays it.",
        "source": "Beat_Reporter",
    },
]

# Simulated LLM output
MOCK_SILVER = [
    {
        "player_id": 123,
        "player_name": "Baker Mayfield",
        "sentiment_score": -0.4,
        "event_type": "locker_room",
        "confidence": 0.8,
    },
    {
        "player_id": 456,
        "player_name": "Deshaun Watson",
        "sentiment_score": -0.9,
        "event_type": "injury_rumor",
        "confidence": 0.9,
    },
]


def run_ingestion():
    logger.info("Starting Rumor Mill Ingestion...")

    # 1. Ingest Bronze
    df_bronze = pd.DataFrame(MOCK_TWEETS)

    # 2. Extract Silver (Simulated LLM call)
    df_silver = pd.DataFrame(MOCK_SILVER)

    # 3. Create Gold feature (volatility multiplier)
    df_silver["volatility_multiplier"] = 1.0 + (df_silver["sentiment_score"] * 0.2)

    with DBManager() as db:
        # Save to DB
        db.execute(
            "CREATE TABLE IF NOT EXISTS rumor_mill_bronze (timestamp VARCHAR, raw_text VARCHAR, source VARCHAR)"
        )
        db.execute(
            "INSERT INTO rumor_mill_bronze SELECT * FROM df_bronze",
            {"df_bronze": df_bronze},
        )

        db.execute(
            "CREATE TABLE IF NOT EXISTS rumor_mill_silver (player_id INT, player_name VARCHAR, sentiment_score FLOAT, event_type VARCHAR, confidence FLOAT, volatility_multiplier FLOAT)"
        )
        db.execute(
            "INSERT INTO rumor_mill_silver SELECT * FROM df_silver",
            {"df_silver": df_silver},
        )

    logger.info("Rumor Mill pipeline completed and features written to DuckDB.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_ingestion()
