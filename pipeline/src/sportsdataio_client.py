import logging
import os
from typing import Any, Dict, List

import pandas as pd
import requests
from google.cloud import bigquery

from src.db_manager import DBManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SportsDataIOCoreClient:
    """
    Client for interacting with the SportsData.io API (NFL V3).
    Specifically fetching Player and Team Reference Data.
    """

    def __init__(self):
        self.api_key = os.environ.get("SPORTS_DATA_IO_API_KEY")
        if not self.api_key:
            raise EnvironmentError(
                "SPORTS_DATA_IO_API_KEY is not set in the environment."
            )

        self.base_url = "https://api.sportsdata.io/v3/nfl/scores/json"
        self.headers = {"Ocp-Apim-Subscription-Key": self.api_key}

    def fetch_active_players(self) -> List[Dict[str, Any]]:
        """Fetches all active players from SportsData.io."""
        logger.info("Fetching Active Players from SportsData.io...")
        endpoint = f"{self.base_url}/Players"
        response = requests.get(endpoint, headers=self.headers)

        if response.status_code != 200:
            logger.error(
                f"Failed to fetch active players. HTTP {response.status_code}: {response.text}"
            )
            response.raise_for_status()

        return response.json()


def ingest_bronze_players():
    """Extracts from API and loads directly into Bronze architecture."""
    client = SportsDataIOCoreClient()
    players_raw_data = client.fetch_active_players()

    # Convert to DataFrame
    df_players = pd.DataFrame(players_raw_data)

    # Add metadata
    df_players["_ingested_at"] = pd.Timestamp.utcnow()

    logger.info(
        f"Loaded {len(df_players)} players into memory. Writing to BigQuery `bronze_sportsdataio_players`..."
    )

    with DBManager() as db:
        table_ref = f"{db.project_id}.{db.dataset_id}.bronze_sportsdataio_players"
        job_config = bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE")

        # Sanitize column names for BigQuery
        df_cleaned = df_players.copy()
        df_cleaned.columns = df_cleaned.columns.astype(str).str.replace(
            r"[^a-zA-Z0-9_]", "_", regex=True
        )
        # Cast all objects to string for safety
        for col in df_cleaned.columns:
            if df_cleaned[col].dtype == "object":
                df_cleaned[col] = df_cleaned[col].astype(str)

        # Write directly, replacing the table each run (Daily full refresh approach)
        job = db.client.load_table_from_dataframe(
            df_cleaned, table_ref, job_config=job_config
        )
        job.result()
        logger.info(
            f"Successfully truncated and rebuilt table {table_ref} with {len(df_cleaned)} records."
        )


if __name__ == "__main__":
    ingest_bronze_players()
