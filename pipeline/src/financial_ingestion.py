from pathlib import Path
import logging

logger = logging.getLogger(__name__)


def load_team_financials(con, path: Path) -> None:
    con.execute(
        f"CREATE OR REPLACE TABLE silver_team_financials AS "
        f"SELECT * FROM read_csv_auto('{path}')"
    )
    logger.info(f"[financial_ingestion] Loaded team financials from {path}")


def load_player_merch(con, path: Path) -> None:
    con.execute(
        f"CREATE OR REPLACE TABLE silver_player_merch AS "
        f"SELECT * FROM read_csv_auto('{path}')"
    )
    logger.info(f"[financial_ingestion] Loaded player merch from {path}")
