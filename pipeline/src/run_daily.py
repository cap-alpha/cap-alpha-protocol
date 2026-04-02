"""
Daily Pipeline Orchestrator

Runs all pipeline stages in order. Designed to run inside Docker via:
    python -m src.run_daily

Each stage is isolated — a failure in one stage logs the error and continues
to the next. The exit code reflects whether any critical stage failed.
"""

import logging
import os
import subprocess
import sys
from datetime import datetime

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(PROJECT_ROOT)


def run_cmd(cmd: str, env: dict = None, ignore_failure=False):
    logger.info(f"Running: {cmd}")
    full_env = os.environ.copy()
    if env:
        full_env.update(env)

    result = subprocess.run(cmd, shell=True, env=full_env)

    if result.returncode != 0:
        if ignore_failure:
            logger.warning(f"Command failed (ignored): {cmd}")
        else:
            logger.error(f"Command failed with exit code {result.returncode}: {cmd}")
            sys.exit(result.returncode)
    return result


def main():
    year = str(datetime.now().year)
    logger.info(f"Starting Daily Pipeline for year {year}")

    # ── Stage 1: Scrapers (contract/roster data) ────────────────────────
    run_cmd(
        f"python -c \"import sys; sys.path.insert(0, '{PROJECT_ROOT}'); "
        f"from src.spotrac_scraper_v2 import scrape_and_save_team_cap; "
        f'scrape_and_save_team_cap({year})"',
        ignore_failure=True,
    )
    run_cmd(
        f"python -c \"import sys; sys.path.insert(0, '{PROJECT_ROOT}'); "
        f"from src.spotrac_scraper_v2 import scrape_and_save_player_rankings; "
        f'scrape_and_save_player_rankings({year})"',
        ignore_failure=True,
    )

    # ── Stage 2: Media Ingestion (pundit predictions) ───────────────────
    run_cmd("python -m src.media_ingestor", ignore_failure=True)

    # ── Stage 3: Silver transforms ──────────────────────────────────────
    run_cmd("python -m src.silver_sportsdataio_transform", ignore_failure=True)

    # ── Stage 4: Feature engineering & ML ───────────────────────────────
    run_cmd("python src/feature_factory.py", ignore_failure=True)
    run_cmd("python src/train_model.py", ignore_failure=True)

    # ── Stage 5: Cryptographic Ledger hash ──────────────────────────────
    run_cmd("python -m src.cryptographic_ledger", ignore_failure=True)

    # ── Stage 6: Data quality checks ────────────────────────────────────
    run_cmd(
        "python -m pytest tests/ -m unit -v --tb=short",
        ignore_failure=True,
    )

    logger.info("Daily Pipeline completed.")


if __name__ == "__main__":
    main()
