"""
Daily Pipeline Orchestrator

Runs all pipeline stages in order. Designed to run inside Docker via:
    python -m src.run_daily
    python -m src.run_daily --best-effort   # old behavior: ignore failures

Each stage is isolated — a failure in one stage logs the error and continues
to the next (in best-effort mode) or halts the pipeline (default fail-loud).

Exit codes:
  0 = all stages succeeded
  1 = one or more stages failed (fail-loud) or critical stage failed (best-effort)
"""

import argparse
import json
import logging
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(PROJECT_ROOT)


class StageResult:
    def __init__(self, stage: str, cmd: str):
        self.stage = stage
        self.cmd = cmd
        self.started_at = datetime.now(timezone.utc)
        self.ended_at = None
        self.returncode = None
        self.status = "running"  # ok | error | skipped
        self.error_message = None

    def finish(self, returncode: int, error_message: str = None):
        self.ended_at = datetime.now(timezone.utc)
        self.returncode = returncode
        self.status = "ok" if returncode == 0 else "error"
        self.error_message = error_message

    def to_dict(self) -> dict:
        return {
            "stage": self.stage,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "duration_s": (
                (self.ended_at - self.started_at).total_seconds()
                if self.ended_at
                else None
            ),
            "status": self.status,
            "returncode": self.returncode,
            "error_message": self.error_message,
        }


def run_stage(
    stage_name: str,
    cmd: str,
    best_effort: bool = False,
    env: dict = None,
) -> StageResult:
    """Run a pipeline stage and return its result."""
    result = StageResult(stage=stage_name, cmd=cmd)
    logger.info(f"[{stage_name}] Running: {cmd}")

    full_env = os.environ.copy()
    if env:
        full_env.update(env)

    try:
        proc = subprocess.run(
            cmd,
            shell=True,
            env=full_env,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            error_msg = (proc.stderr or proc.stdout or "")[-500:]
            result.finish(proc.returncode, error_msg)
            if best_effort:
                logger.warning(
                    f"[{stage_name}] FAILED (best-effort, continuing): "
                    f"exit={proc.returncode}"
                )
            else:
                logger.error(
                    f"[{stage_name}] FAILED: exit={proc.returncode}\n{error_msg}"
                )
        else:
            result.finish(0)
            logger.info(f"[{stage_name}] OK")
    except Exception as e:
        result.finish(1, str(e))
        logger.error(f"[{stage_name}] Exception: {e}")

    return result


class _StageFailed(Exception):
    """Raised inside the Healer-wrapped callable when a stage exits non-zero."""

    def __init__(self, returncode: int, error_message: str):
        self.returncode = returncode
        self.error_message = error_message
        super().__init__(error_message[:200])


def _run_stage_with_healing(
    stage_name: str, cmd: str, healer, best_effort: bool
) -> "StageResult":
    """Run a stage through the Healer so transient errors auto-retry."""
    final: dict = {}

    def attempt():
        result = run_stage(stage_name, cmd, best_effort=True)
        final["result"] = result
        if result.status == "error":
            raise _StageFailed(result.returncode or 1, result.error_message or "")
        return result

    outcome = healer.run(stage_name, attempt)
    if outcome.outcome in ("ok", "healed"):
        return final["result"]
    # Escalated — the last result is still in `final` from the last attempt
    return final.get("result") or run_stage(stage_name, cmd, best_effort=best_effort)


def main():
    parser = argparse.ArgumentParser(description="Daily Pipeline Orchestrator")
    parser.add_argument(
        "--best-effort",
        action="store_true",
        help="Continue on stage failure (old behavior). Default is fail-loud.",
    )
    parser.add_argument(
        "--self-heal",
        action="store_true",
        help="Wrap each stage in the Healer playbook framework "
        "(retry transient errors, escalate novel ones).",
    )
    args = parser.parse_args()

    best_effort = args.best_effort
    self_heal = args.self_heal
    mode = "best-effort" if best_effort else "fail-loud"
    if self_heal:
        mode += "+self-heal"

    healer = None
    if self_heal:
        from src.healing import Healer, register_default_playbooks

        healer = Healer()
        register_default_playbooks(healer)
        logger.info(
            "Self-healing enabled: %d playbooks registered", len(healer.playbooks)
        )
    year = str(datetime.now().year)
    run_id = str(uuid.uuid4())[:8]

    logger.info(f"Starting Daily Pipeline (run={run_id}, year={year}, mode={mode})")

    stages = [
        (
            "scrape_team_cap",
            f"python -c \"import sys; sys.path.insert(0, '{PROJECT_ROOT}'); "
            f"from src.spotrac_scraper_v2 import scrape_and_save_team_cap; "
            f'scrape_and_save_team_cap({year})"',
        ),
        (
            "scrape_player_rankings",
            f"python -c \"import sys; sys.path.insert(0, '{PROJECT_ROOT}'); "
            f"from src.spotrac_scraper_v2 import scrape_and_save_player_rankings; "
            f'scrape_and_save_player_rankings({year})"',
        ),
        ("media_ingest", "python -m src.media_ingestor"),
        ("assertion_extract", "python -m src.assertion_extractor --limit 50"),
        ("cross_article_dedup", "python -m src.cross_article_dedup"),
        ("silver_transform", "python -m src.silver_sportsdataio_transform"),
        ("feature_factory", "python src/feature_factory.py"),
        ("train_model", "python src/train_model.py"),
        ("ledger_hash", "python -m src.cryptographic_ledger"),
        ("quality_checks", "python -m pytest tests/ -m unit -v --tb=short"),
        ("bq_data_quality", "python -m src.bq_data_quality"),
    ]

    results = []
    failed = False

    for stage_name, cmd in stages:
        if healer is not None:
            stage_result = _run_stage_with_healing(
                stage_name, cmd, healer, best_effort=best_effort
            )
        else:
            stage_result = run_stage(stage_name, cmd, best_effort=best_effort)
        results.append(stage_result)

        if stage_result.status == "error":
            failed = True
            if not best_effort:
                logger.error(
                    f"Pipeline halted at stage '{stage_name}' (fail-loud mode). "
                    f"Use --best-effort to continue past failures."
                )
                break

    # Print run manifest
    logger.info("=" * 60)
    logger.info(f"Pipeline Run Summary (run={run_id}, mode={mode})")
    logger.info("=" * 60)
    for r in results:
        duration = r.to_dict().get("duration_s", "?")
        icon = "✓" if r.status == "ok" else "✗"
        logger.info(f"  {icon} {r.stage:<25} {r.status:<8} {duration:.1f}s")
        if r.error_message:
            logger.info(f"    └ {r.error_message[:120]}")
    logger.info("=" * 60)

    total_ok = sum(1 for r in results if r.status == "ok")
    total_err = sum(1 for r in results if r.status == "error")
    logger.info(
        f"Stages: {total_ok} passed, {total_err} failed, "
        f"{len(stages) - len(results)} skipped"
    )

    # Write manifest to JSON for observability
    manifest = {
        "run_id": run_id,
        "run_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "mode": mode,
        "stages": [r.to_dict() for r in results],
        "total_ok": total_ok,
        "total_error": total_err,
    }
    manifest_json = json.dumps(manifest, indent=2)
    logger.info(f"Run manifest:\n{manifest_json}")

    if failed:
        logger.error("Daily Pipeline completed with errors.")
        sys.exit(1)
    else:
        logger.info("Daily Pipeline completed successfully.")


if __name__ == "__main__":
    main()
