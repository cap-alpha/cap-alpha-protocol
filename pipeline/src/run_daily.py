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

    # Layer 1: Scrapers
    run_cmd(
        f"python -c \"import sys; sys.path.insert(0, '{PROJECT_ROOT}'); from src.spotrac_scraper_v2 import scrape_and_save_team_cap; scrape_and_save_team_cap({year})\""
    )
    run_cmd(
        f"python -c \"import sys; sys.path.insert(0, '{PROJECT_ROOT}'); from src.spotrac_scraper_v2 import scrape_and_save_player_rankings; scrape_and_save_player_rankings({year})\""
    )

    # Layer 2: Staging
    run_cmd(f"python src/ingestion.py --source spotrac-team-cap --year {year}")
    run_cmd(f"python src/ingestion.py --source pfr-rosters --year {year}")
    run_cmd(f"python src/ingestion.py --source spotrac-rankings --year {year}")
    run_cmd(f"python src/ingestion.py --source spotrac-contracts --year {year}")

    # Layer 3: Normalization & DuckDB
    run_cmd(f"python src/normalization.py --year {year}")
    run_cmd(f"python src/load_to_duckdb.py {year}")

    # Layer 4: dbt
    run_cmd("dbt seed --project-dir ./dbt --profiles-dir ./dbt")
    run_cmd("dbt run --project-dir ./dbt --profiles-dir ./dbt")

    # Layer 5: Data Quality
    run_cmd(
        "pytest tests/test_data_freshness.py tests/test_pipeline_idempotency.py -v --tb=short",
        ignore_failure=True,
    )

    # Layer 6: ML Flywheel
    run_cmd("python src/feature_factory.py")
    run_cmd("python src/train_model.py")

    # Layer 7: Ledger & Provenance Signature
    run_cmd("python src/cryptographic_ledger.py")

    # Layer 8: Proof of Alpha
    run_cmd("python ../scripts/generate_proof_of_alpha.py")

    logger.info("Daily Pipeline completed successfully.")


if __name__ == "__main__":
    main()
