"""
nflverse_client.py — Free NFL data ingestion via nfl_data_py (nflverse GitHub CSVs)

No API key required. Pulls seasonal stats, weekly stats, and draft picks from
the nflverse GitHub releases and writes them to BigQuery bronze tables.

Usage:
    python -m src.nflverse_client --all
    python -m src.nflverse_client --player-stats
    python -m src.nflverse_client --draft-picks
    python -m src.nflverse_client --weekly-stats
"""

import argparse
import logging

import nfl_data_py as nfl
import pandas as pd
from google.cloud import bigquery

from src.db_manager import DBManager

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
logger = logging.getLogger(__name__)


def _sanitize_df(df: pd.DataFrame) -> pd.DataFrame:
    """Sanitize column names and cast object columns to string for BigQuery compatibility."""
    df = df.copy()
    df.columns = df.columns.astype(str).str.replace(r"[^a-zA-Z0-9_]", "_", regex=True)
    df["_ingested_at"] = pd.Timestamp.utcnow()
    # Cast object columns to string to avoid Parquet type mismatch
    for col in df.columns:
        if df[col].dtype == "object":
            df[col] = df[col].astype(str)
    return df


def _write_to_bq(df: pd.DataFrame, table_name: str, db: DBManager) -> None:
    """Write a DataFrame to BigQuery with WRITE_TRUNCATE (full refresh)."""
    table_ref = f"{db.project_id}.{db.dataset_id}.{table_name}"
    job_config = bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE")
    job = db.client.load_table_from_dataframe(df, table_ref, job_config=job_config)
    job.result()
    logger.info(f"Wrote {len(df):,} rows to {table_ref}")


def _available_seasons(url_template: str, candidate_seasons: list[int]) -> list[int]:
    """Return only seasons whose parquet file actually exists on GitHub releases."""
    import urllib.request

    available = []
    for year in candidate_seasons:
        url = url_template.format(year)
        try:
            with urllib.request.urlopen(url) as r:
                if r.status == 200:
                    available.append(year)
        except Exception:
            logger.debug(f"Season {year} not yet available at {url}")
    return available


def ingest_bronze_player_season_stats(seasons: list[int] | None = None) -> None:
    """Ingest player seasonal stats from nflverse (free) into bronze_nflverse_player_stats.

    Key columns: player_id, player_name, season, completions, attempts,
    passing_yards, passing_tds, rushing_yards, rushing_tds,
    receptions, targets, receiving_yards, receiving_tds.
    """
    if seasons is None:
        seasons = [2023, 2024, 2025]

    # Filter to seasons that are actually available on GitHub releases
    url_tpl = "https://github.com/nflverse/nflverse-data/releases/download/player_stats/player_stats_{0}.parquet"
    seasons = _available_seasons(url_tpl, seasons)
    if not seasons:
        logger.warning("No seasonal stats available for the requested seasons.")
        return

    logger.info(f"Fetching nflverse seasonal stats for seasons: {seasons}")
    df = nfl.import_seasonal_data(seasons)
    if df.empty:
        logger.warning("No seasonal stats returned from nflverse.")
        return

    df = _sanitize_df(df)
    logger.info(f"Loaded {len(df):,} player-season rows. Writing to BigQuery…")

    with DBManager() as db:
        _write_to_bq(df, "bronze_nflverse_player_stats", db)


def ingest_bronze_draft_picks(seasons: list[int] | None = None) -> None:
    """Ingest draft picks from nflverse into bronze_nflverse_draft_picks.

    Covers the requested seasons (defaults to 2020–2026).
    """
    if seasons is None:
        seasons = [2020, 2021, 2022, 2023, 2024, 2025, 2026]

    logger.info(f"Fetching nflverse draft picks for seasons: {seasons}")
    df = nfl.import_draft_picks(seasons)
    if df.empty:
        logger.warning("No draft picks returned from nflverse.")
        return

    df = _sanitize_df(df)
    logger.info(f"Loaded {len(df):,} draft-pick rows. Writing to BigQuery…")

    with DBManager() as db:
        _write_to_bq(df, "bronze_nflverse_draft_picks", db)


def ingest_bronze_weekly_stats(seasons: list[int] | None = None) -> None:
    """Ingest weekly player stats from nflverse into bronze_nflverse_weekly_stats."""
    if seasons is None:
        seasons = [2023, 2024, 2025]

    url_tpl = "https://github.com/nflverse/nflverse-data/releases/download/player_stats/player_stats_{0}.parquet"
    seasons = _available_seasons(url_tpl, seasons)
    if not seasons:
        logger.warning("No weekly stats available for the requested seasons.")
        return

    logger.info(f"Fetching nflverse weekly stats for seasons: {seasons}")
    df = nfl.import_weekly_data(seasons)
    if df.empty:
        logger.warning("No weekly stats returned from nflverse.")
        return

    df = _sanitize_df(df)
    logger.info(f"Loaded {len(df):,} player-week rows. Writing to BigQuery…")

    with DBManager() as db:
        _write_to_bq(df, "bronze_nflverse_weekly_stats", db)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Ingest free NFL data from nflverse (nfl_data_py) into BigQuery bronze tables."
    )
    parser.add_argument(
        "--player-stats",
        action="store_true",
        help="Ingest seasonal player stats → bronze_nflverse_player_stats",
    )
    parser.add_argument(
        "--draft-picks",
        action="store_true",
        help="Ingest draft picks → bronze_nflverse_draft_picks",
    )
    parser.add_argument(
        "--weekly-stats",
        action="store_true",
        help="Ingest weekly player stats → bronze_nflverse_weekly_stats",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Ingest all three tables",
    )
    args = parser.parse_args()

    if not any([args.all, args.player_stats, args.draft_picks, args.weekly_stats]):
        parser.print_help()
        raise SystemExit(1)

    if args.all or args.player_stats:
        ingest_bronze_player_season_stats()
    if args.all or args.draft_picks:
        ingest_bronze_draft_picks()
    if args.all or args.weekly_stats:
        ingest_bronze_weekly_stats()

    logger.info("nflverse ingestion complete.")
