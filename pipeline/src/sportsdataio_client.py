import argparse
import logging
import os
from typing import Any, Dict, List, Optional

import pandas as pd
import requests
from google.cloud import bigquery
from src.db_manager import DBManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEFAULT_SEASONS = [2024, 2025]


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

    def fetch_scores(self, season: int) -> List[Dict[str, Any]]:
        """Fetches game scores for a given NFL season from SportsData.io."""
        logger.info(f"Fetching game scores for season {season} from SportsData.io...")
        endpoint = f"{self.base_url}/Scores/{season}"
        response = requests.get(endpoint, headers=self.headers)

        if response.status_code != 200:
            logger.error(
                f"Failed to fetch scores for season {season}. "
                f"HTTP {response.status_code}: {response.text}"
            )
            response.raise_for_status()

        return response.json()

    def fetch_player_season_stats(self, season: int) -> List[Dict[str, Any]]:
        """Fetches player season stats for a given NFL season from SportsData.io."""
        logger.info(
            f"Fetching player season stats for season {season} from SportsData.io..."
        )
        endpoint = f"{self.base_url}/PlayerSeasonStats/{season}"
        response = requests.get(endpoint, headers=self.headers)

        if response.status_code != 200:
            logger.error(
                f"Failed to fetch player season stats for season {season}. "
                f"HTTP {response.status_code}: {response.text}"
            )
            response.raise_for_status()

        return response.json()


def _sanitize_df(df: pd.DataFrame) -> pd.DataFrame:
    """Sanitize column names and cast object columns to string for BigQuery compatibility."""
    df_cleaned = df.copy()
    df_cleaned.columns = df_cleaned.columns.astype(str).str.replace(
        r"[^a-zA-Z0-9_]", "_", regex=True
    )
    for col in df_cleaned.columns:
        if df_cleaned[col].dtype == "object":
            df_cleaned[col] = df_cleaned[col].astype(str)
    return df_cleaned


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

        df_cleaned = _sanitize_df(df_players)

        # Write directly, replacing the table each run (Daily full refresh approach)
        job = db.client.load_table_from_dataframe(
            df_cleaned, table_ref, job_config=job_config
        )
        job.result()
        logger.info(
            f"Successfully truncated and rebuilt table {table_ref} with {len(df_cleaned)} records."
        )


def ingest_bronze_scores(seasons: Optional[List[int]] = None) -> dict:
    """Fetch game scores for given seasons and write to bronze_sportsdataio_scores.

    Each season replaces its own rows (partition by Season via WRITE_TRUNCATE on a
    temp table then merge) — implemented here as a per-season WRITE_TRUNCATE so
    each season's data is always fresh.  The table is rebuilt in full each run.

    Args:
        seasons: List of NFL season years to fetch (e.g. [2024, 2025]).
                 Defaults to [2024, 2025].

    Returns:
        dict with 'seasons_fetched', 'total_rows' keys.
    """
    if seasons is None:
        seasons = DEFAULT_SEASONS

    client = SportsDataIOCoreClient()
    all_frames: List[pd.DataFrame] = []

    for season in seasons:
        try:
            raw = client.fetch_scores(season)
            if not raw:
                logger.warning(f"No score data returned for season {season}.")
                continue
            df = pd.DataFrame(raw)
            df["_ingested_at"] = pd.Timestamp.utcnow()
            logger.info(f"Fetched {len(df)} game records for season {season}.")
            all_frames.append(df)
        except Exception as e:
            logger.error(f"Error fetching scores for season {season}: {e}")

    if not all_frames:
        logger.warning("No score data fetched for any season.")
        return {"seasons_fetched": 0, "total_rows": 0}

    df_all = pd.concat(all_frames, ignore_index=True)
    df_cleaned = _sanitize_df(df_all)

    with DBManager() as db:
        table_ref = f"{db.project_id}.{db.dataset_id}.bronze_sportsdataio_scores"
        job_config = bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE")
        job = db.client.load_table_from_dataframe(
            df_cleaned, table_ref, job_config=job_config
        )
        job.result()
        logger.info(
            f"Successfully wrote {len(df_cleaned)} game score records to {table_ref}."
        )

    return {"seasons_fetched": len(all_frames), "total_rows": len(df_cleaned)}


def ingest_bronze_player_season_stats(seasons: Optional[List[int]] = None) -> dict:
    """Fetch player season stats and write to bronze_sportsdataio_player_season_stats.

    Args:
        seasons: List of NFL season years to fetch (e.g. [2024, 2025]).
                 Defaults to [2024, 2025].

    Returns:
        dict with 'seasons_fetched', 'total_rows' keys.
    """
    if seasons is None:
        seasons = DEFAULT_SEASONS

    client = SportsDataIOCoreClient()
    all_frames: List[pd.DataFrame] = []

    for season in seasons:
        try:
            raw = client.fetch_player_season_stats(season)
            if not raw:
                logger.warning(f"No player season stats returned for season {season}.")
                continue
            df = pd.DataFrame(raw)
            df["_ingested_at"] = pd.Timestamp.utcnow()
            logger.info(f"Fetched {len(df)} player stat records for season {season}.")
            all_frames.append(df)
        except Exception as e:
            logger.error(f"Error fetching player season stats for season {season}: {e}")

    if not all_frames:
        logger.warning("No player season stats fetched for any season.")
        return {"seasons_fetched": 0, "total_rows": 0}

    df_all = pd.concat(all_frames, ignore_index=True)
    df_cleaned = _sanitize_df(df_all)

    with DBManager() as db:
        table_ref = (
            f"{db.project_id}.{db.dataset_id}.bronze_sportsdataio_player_season_stats"
        )
        job_config = bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE")
        job = db.client.load_table_from_dataframe(
            df_cleaned, table_ref, job_config=job_config
        )
        job.result()
        logger.info(
            f"Successfully wrote {len(df_cleaned)} player season stat records to {table_ref}."
        )

    return {"seasons_fetched": len(all_frames), "total_rows": len(df_cleaned)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SportsData.io bronze ingestion CLI")
    parser.add_argument(
        "--players",
        action="store_true",
        help="Ingest active players into bronze_sportsdataio_players",
    )
    parser.add_argument(
        "--scores",
        action="store_true",
        help="Ingest game scores into bronze_sportsdataio_scores",
    )
    parser.add_argument(
        "--player-stats",
        action="store_true",
        help="Ingest player season stats into bronze_sportsdataio_player_season_stats",
    )
    parser.add_argument(
        "--seasons",
        nargs="+",
        type=int,
        default=DEFAULT_SEASONS,
        help=f"Season years to fetch (default: {DEFAULT_SEASONS})",
    )
    args = parser.parse_args()

    # Default: run all if no specific flag is given
    run_all = not (args.players or args.scores or args.player_stats)

    if run_all or args.players:
        ingest_bronze_players()

    if run_all or args.scores:
        result = ingest_bronze_scores(seasons=args.seasons)
        logger.info(f"Scores ingestion result: {result}")

    if run_all or args.player_stats:
        result = ingest_bronze_player_season_stats(seasons=args.seasons)
        logger.info(f"Player season stats ingestion result: {result}")
