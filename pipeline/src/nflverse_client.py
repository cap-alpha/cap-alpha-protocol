"""
nflverse_client.py — Free NFL data ingestion via nfl_data_py (nflverse GitHub CSVs).
No API key required. Writes bronze tables to BigQuery dataset `nfl_dead_money`.

Tables produced:
  bronze_nflverse_player_stats   — seasonal aggregates (passing/rushing/receiving)
  bronze_nflverse_draft_picks    — draft pick history
  bronze_nflverse_weekly_stats   — per-week player stats
"""

import argparse
import logging

import nfl_data_py as nfl
import pandas as pd
from google.cloud import bigquery

from src.db_manager import DBManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _write_truncate(db: DBManager, df: pd.DataFrame, table_name: str) -> None:
    """Write a DataFrame to BigQuery with WRITE_TRUNCATE (full refresh)."""
    if df is None or df.empty:
        logger.warning(f"No data to write for {table_name} — skipping.")
        return

    df_clean = df.copy()

    # Sanitize column names for BigQuery
    df_clean.columns = df_clean.columns.astype(str).str.replace(
        r"[^a-zA-Z0-9_]", "_", regex=True
    )

    # Add ingestion timestamp
    df_clean["_ingested_at"] = pd.Timestamp.utcnow()

    # Cast object columns to string to avoid Parquet type mismatches
    for col in df_clean.columns:
        if df_clean[col].dtype == "object":
            df_clean[col] = df_clean[col].astype(str)

    table_ref = f"{db.project_id}.{db.dataset_id}.{table_name}"
    job_config = bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE")
    job = db.client.load_table_from_dataframe(
        df_clean, table_ref, job_config=job_config
    )
    job.result()
    logger.info(f"Loaded {len(df_clean)} rows into `{table_ref}` (WRITE_TRUNCATE).")


def ingest_bronze_player_season_stats(seasons: list[int] | None = None) -> None:
    """Ingest player seasonal stats from nflverse into bronze_nflverse_player_stats.

    Note: nflverse seasonal parquet files are published per-year. The 2025 NFL season
    (which ends Feb 2026) file may not be available yet if the season is in-progress.
    Default seasons are conservative — add 2025 once the file is published.
    """
    if seasons is None:
        seasons = [2023, 2024]

    logger.info(f"Fetching seasonal player stats for seasons: {seasons}")
    df = nfl.import_seasonal_data(seasons)
    logger.info(f"Fetched {len(df)} rows of seasonal player data.")

    with DBManager() as db:
        _write_truncate(db, df, "bronze_nflverse_player_stats")


def ingest_bronze_draft_picks(seasons: list[int] | None = None) -> None:
    """Ingest draft picks from nflverse into bronze_nflverse_draft_picks."""
    if seasons is None:
        seasons = [2020, 2021, 2022, 2023, 2024, 2025, 2026]

    logger.info(f"Fetching draft picks for seasons: {seasons}")
    df = nfl.import_draft_picks(seasons)
    logger.info(f"Fetched {len(df)} rows of draft pick data.")

    with DBManager() as db:
        _write_truncate(db, df, "bronze_nflverse_draft_picks")


def ingest_bronze_players() -> None:
    """Ingest all NFL players from nflverse into bronze_nflverse_players.

    Provides gsis_id (=player_id) to display_name mapping needed to join
    seasonal/weekly stats with player names.
    """
    logger.info("Fetching all NFL players from nflverse...")
    df = nfl.import_players()
    logger.info(f"Fetched {len(df)} player records.")

    with DBManager() as db:
        _write_truncate(db, df, "bronze_nflverse_players")


def ingest_bronze_weekly_stats(seasons: list[int] | None = None) -> None:
    """Ingest weekly player stats from nflverse into bronze_nflverse_weekly_stats.

    Note: 2025 weekly data is available mid-season but seasonal aggregates lag.
    """
    if seasons is None:
        seasons = [2023, 2024]

    logger.info(f"Fetching weekly player stats for seasons: {seasons}")
    df = nfl.import_weekly_data(seasons)
    logger.info(f"Fetched {len(df)} rows of weekly player data.")

    with DBManager() as db:
        _write_truncate(db, df, "bronze_nflverse_weekly_stats")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Ingest nflverse data into BigQuery bronze tables."
    )
    parser.add_argument(
        "--player-stats", action="store_true", help="Ingest seasonal player stats"
    )
    parser.add_argument("--draft-picks", action="store_true", help="Ingest draft picks")
    parser.add_argument(
        "--weekly-stats", action="store_true", help="Ingest weekly player stats"
    )
    parser.add_argument(
        "--players", action="store_true", help="Ingest all NFL players (name lookup)"
    )
    parser.add_argument("--all", action="store_true", help="Run all ingestion jobs")
    args = parser.parse_args()

    if not any(
        [args.player_stats, args.draft_picks, args.weekly_stats, args.players, args.all]
    ):
        parser.print_help()
    else:
        if args.all or args.player_stats:
            ingest_bronze_player_season_stats()
        if args.all or args.draft_picks:
            ingest_bronze_draft_picks()
        if args.all or args.weekly_stats:
            ingest_bronze_weekly_stats()
        if args.all or args.players:
            ingest_bronze_players()
