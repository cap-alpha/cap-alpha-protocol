"""
Daily Pipeline Orchestrator

Runs all pipeline stages in order. Designed to run inside Docker via:
    python -m src.run_daily
    python -m src.run_daily --best-effort   # old behavior: ignore failures

Each stage is isolated — a failure in one stage logs the error and continues
to the next (in best-effort mode) or halts the pipeline (default fail-loud).

Telemetry: each stage writes timing, row counts, and status to
gold_layer.pipeline_runs via PipelineRun.

Exit codes:
  0 = all stages succeeded
  1 = one or more stages failed
"""

import argparse
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


# Stages that treat zero-rows-on-nonempty-input as failure.
STRICT_ZERO_ROW_STAGES = {
    "media_ingestor",
    "assertion_extractor",
    "silver_transform",
}


def run_cmd(cmd: str, env: dict = None, ignore_failure=False):
    logger.info(f"Running: {cmd}")
    full_env = os.environ.copy()
    if env:
        full_env.update(env)

    result = subprocess.run(
        cmd, shell=True, env=full_env, capture_output=True, text=True
    )

    if result.stdout:
        logger.info(result.stdout[-2000:])
    if result.stderr:
        logger.warning(result.stderr[-2000:])

    if result.returncode != 0:
        if ignore_failure:
            logger.warning(f"Command failed (ignored): {cmd}")
        else:
            logger.error(f"Command failed with exit code {result.returncode}: {cmd}")
    return result


def _get_table_count(db, table_name: str):
    """Get row count for a table, or None if it doesn't exist."""
    try:
        if not db.table_exists(table_name):
            return None
        result = db.execute(f"SELECT COUNT(*) FROM `{table_name}`")
        row = result.fetchone()
        return row[0] if row else None
    except Exception as e:
        logger.warning(f"Could not get row count for {table_name}: {e}")
        return None


def _run_stage(
    pipeline_run,
    stage_name,
    cmd,
    db=None,
    input_table=None,
    output_table=None,
    env=None,
):
    """Run a single stage with telemetry tracking. Returns True if successful."""
    rows_in = _get_table_count(db, input_table) if db and input_table else None
    pipeline_run.begin_stage(stage_name, rows_in=rows_in)

    result = run_cmd(cmd, env=env, ignore_failure=True)

    rows_out = _get_table_count(db, output_table) if db and output_table else None

    if result.returncode != 0:
        error_text = (result.stderr or "")[-500:]
        pipeline_run.end_stage(rows_out=rows_out, status="FAILURE", error=error_text)
        return False
    else:
        strict = stage_name in STRICT_ZERO_ROW_STAGES
        if not pipeline_run.check_row_delta(rows_in, rows_out, strict=strict):
            pipeline_run.end_stage(
                rows_out=rows_out,
                status="FAILURE",
                error=f"Zero rows written from {rows_in} input rows",
            )
            return False
        else:
            pipeline_run.end_stage(rows_out=rows_out, status="SUCCESS")
            return True


def main():
    parser = argparse.ArgumentParser(description="Daily Pipeline Orchestrator")
    parser.add_argument(
        "--best-effort",
        action="store_true",
        help="Continue on stage failure (old behavior). Default is fail-loud.",
    )
    args = parser.parse_args()
    best_effort = args.best_effort

    from src.pipeline_telemetry import PipelineRun, ensure_pipeline_runs_table

    year = str(datetime.now().year)
    mode = "best-effort" if best_effort else "fail-loud"

    # Initialize telemetry
    pipeline_run = PipelineRun()
    logger.info(
        f"Starting Daily Pipeline (run={pipeline_run.run_id}, year={year}, mode={mode})"
    )

    # Try to connect to BigQuery for telemetry (non-fatal if unavailable)
    db = None
    try:
        from src.db_manager import DBManager

        db = DBManager()
        ensure_pipeline_runs_table(db)
    except Exception as e:
        logger.warning(f"BigQuery unavailable for telemetry: {e}")

    def ok():
        """In fail-loud mode, skip remaining stages after first failure."""
        return best_effort or not pipeline_run.has_failures

    # ── Stage 1: Scrapers (contract/roster data) ────────────────────────
    if ok():
        _run_stage(
            pipeline_run,
            "scraper_team_cap",
            f"python -c \"import sys; sys.path.insert(0, '{PROJECT_ROOT}'); "
            f"from src.spotrac_scraper_v2 import scrape_and_save_team_cap; "
            f'scrape_and_save_team_cap({year})"',
            db=db,
            output_table="team_cap_data",
        )
    if ok():
        _run_stage(
            pipeline_run,
            "scraper_player_rankings",
            f"python -c \"import sys; sys.path.insert(0, '{PROJECT_ROOT}'); "
            f"from src.spotrac_scraper_v2 import scrape_and_save_player_rankings; "
            f'scrape_and_save_player_rankings({year})"',
            db=db,
            output_table="player_rankings",
        )

    # ── Stage 2: Media Ingestion (pundit predictions) ───────────────────
    if ok():
        _run_stage(
            pipeline_run,
            "media_ingestor",
            "python -m src.media_ingestor",
            db=db,
            output_table="raw_pundit_media",
        )

    # ── Stage 3: NLP Assertion Extraction ───────────────────────────────
    if ok():
        _run_stage(
            pipeline_run,
            "assertion_extractor",
            "python -m src.assertion_extractor --limit 50",
            db=db,
            input_table="raw_pundit_media",
            output_table="pundit_assertions",
        )

    # ── Stage 4: Silver transforms ──────────────────────────────────────
    if ok():
        _run_stage(
            pipeline_run,
            "silver_transform",
            "python -m src.silver_sportsdataio_transform",
            db=db,
        )

    # ── Stage 5: Feature engineering & ML ───────────────────────────────
    if ok():
        _run_stage(
            pipeline_run,
            "feature_factory",
            "python src/feature_factory.py",
            db=db,
        )
    if ok():
        _run_stage(
            pipeline_run,
            "train_model",
            "python src/train_model.py",
            db=db,
        )

    # ── Stage 6: Cryptographic Ledger hash ──────────────────────────────
    if ok():
        _run_stage(
            pipeline_run,
            "cryptographic_ledger",
            "python -m src.cryptographic_ledger",
            db=db,
        )

    # ── Stage 7: Data quality checks ────────────────────────────────────
    if ok():
        _run_stage(
            pipeline_run,
            "data_quality_tests",
            "python -m pytest tests/ -m unit -v --tb=short",
        )

    # ── Persist telemetry & summary ─────────────────────────────────────
    logger.info(f"Pipeline summary:\n{pipeline_run.summary()}")

    if db:
        try:
            pipeline_run.persist(db)
        except Exception as e:
            logger.error(f"Failed to persist telemetry: {e}")
        finally:
            db.close()

    if pipeline_run.has_failures:
        logger.error("Daily Pipeline completed with FAILURES.")
        sys.exit(1)

    logger.info("Daily Pipeline completed successfully.")


if __name__ == "__main__":
    main()
