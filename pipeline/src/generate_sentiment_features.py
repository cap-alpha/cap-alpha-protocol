import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request

import pandas as pd
from tqdm import tqdm

# Add pipeline root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from pipeline.src.db_manager import DBManager
from pipeline.src.web_intelligence_hoover import WikipediaHoover

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Prototype targets removed in favor of dynamic DB querying


def generate_true_embedding(text_payload: str) -> list:
    """Hits the Gemini Embedding API natively to vectorize unstructured text."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.error("GEMINI_API_KEY not found in environment.")
        return None

    gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent?key={api_key}"

    payload = {
        "model": "models/gemini-embedding-001",
        "content": {"parts": [{"text": text_payload}]},
    }

    try:
        req = urllib.request.Request(
            gemini_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode("utf-8"))
            return data["embedding"]["values"]
    except Exception as e:
        logger.error(f"Error generating embedding: {e}")
        return None


def main():
    logger.info("Initializing NLP Sentiment Vector Pipeline (True Hydration)...")
    db = DBManager()
    hoover = WikipediaHoover()
    vector_results = []
    narrative_results = []

    # Dynamically fetch high-value targets
    targets_query = """
        SELECT DISTINCT player_name 
        FROM fact_player_efficiency 
        WHERE cap_hit_millions >= 10 OR risk_score > 0.65
    """
    try:
        df_targets = db.fetch_df(targets_query)
        targets = df_targets["player_name"].tolist()
        logger.info(f"Dynamically loaded {len(targets)} high-value targets.")
    except Exception as e:
        logger.warning(
            f"Could not load targets from fact_player_efficiency, falling back to prototype list. Error: {e}"
        )
        targets = [
            "Russell Wilson",
            "Aaron Rodgers",
            "Deshaun Watson",
            "Ezekiel Elliott",
            "Jamal Adams",
        ]

    for player in tqdm(targets, desc="Processing Sentiment Batch"):
        logger.info(f"Aggregating unstructured context for {player}...")

        # 0. Hoover fresh Wikipedia data
        try:
            hoover.gather_player_intelligence(player)
        except Exception as e:
            logger.warning(f"Wikipedia hover failed for {player}: {e}")

        # 1. Fetch Recent News/Media Baseline
        media_query = f"SELECT raw_text FROM bronze_layer.raw_media_sentiment WHERE player_name = '{player}' ORDER BY ingested_at DESC LIMIT 1"
        media_df = db.fetch_df(media_query)
        media_text = (
            media_df["raw_text"].iloc[0]
            if not media_df.empty
            else "No recent news data available."
        )

        # 2. Fetch Aggregated Injury History
        injury_query = f"SELECT report_primary_injury, practice_status, report_status FROM bronze_layer.nflverse_injuries WHERE full_name = '{player}' AND report_primary_injury IS NOT NULL LIMIT 50"
        injury_df = db.fetch_df(injury_query)
        injury_text = "No severe injuries reported."
        if not injury_df.empty:
            injury_logs = injury_df.to_dict("records")
            injury_text = "Historical Injury Log: " + " | ".join(
                [
                    f"Status: {log.get('report_status', 'Unknown')} due to {log.get('report_primary_injury', 'Unknown')}"
                    for log in injury_logs
                ]
            )

        # We need to truncate text slightly to avoid massive embedding payload failures
        compiled_narrative = media_text[:6000] + "\n\n" + injury_text[:2000]

        # Store for narrative table
        narrative_results.append(
            {
                "player_name": player,
                "ingested_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "news_summary": media_text[:1000],
                "injury_summary": injury_text[:1000],
                "full_context": compiled_narrative[:5000],
            }
        )

        logger.info(f"Embedding {len(compiled_narrative)} characters via Gemini API...")
        embedding_vector = generate_true_embedding(compiled_narrative)

        if embedding_vector:
            flat_record = {"player_name": player}
            for i, val in enumerate(embedding_vector):
                flat_record[f"dim_{i}"] = val
            vector_results.append(flat_record)

        time.sleep(1.5)  # rate limit buffer

    if vector_results:
        df_embeddings = pd.DataFrame(vector_results)
        df_narratives = pd.DataFrame(narrative_results)

        logger.info("Persisting Batch to MotherDuck Silver Layer...")
        db.execute("CREATE SCHEMA IF NOT EXISTS silver_layer")

        # Persist vectors for ML
        db.execute(
            "CREATE OR REPLACE TABLE silver_layer.nlp_sentiment_features_true AS SELECT * FROM df_embeddings",
            {"df_embeddings": df_embeddings},
        )

        # Persist narratives for UI
        db.execute(
            "CREATE OR REPLACE TABLE silver_layer.nlp_intelligence_narratives AS SELECT * FROM df_narratives",
            {"df_narratives": df_narratives},
        )

        logger.info(
            f"✅ Successfully hydrated Silver Layer for {len(vector_results)} elite targets."
        )
    else:
        logger.warning("No data generated in this batch.")


if __name__ == "__main__":
    main()
