"""
Pipeline Telemetry — observability for daily pipeline runs.

Tracks each stage's timing, row counts, and status, then writes
results to gold_layer.pipeline_runs in BigQuery.
"""

import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

PIPELINE_RUNS_TABLE = "pipeline_runs"

PIPELINE_RUNS_SCHEMA = """
CREATE TABLE IF NOT EXISTS pipeline_runs (
  run_id STRING NOT NULL,
  stage STRING NOT NULL,
  started_at TIMESTAMP NOT NULL,
  ended_at TIMESTAMP,
  rows_in INT64,
  rows_out INT64,
  status STRING NOT NULL,
  error STRING,
  run_date DATE NOT NULL
)
PARTITION BY run_date
"""


@dataclass
class StageResult:
    """Result of a single pipeline stage execution."""

    stage: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    rows_in: Optional[int] = None
    rows_out: Optional[int] = None
    status: str = "SUCCESS"
    error: Optional[str] = None


class PipelineRun:
    """Tracks a full pipeline invocation across multiple stages."""

    def __init__(self, run_id: Optional[str] = None):
        self.run_id = run_id or uuid.uuid4().hex
        self.run_date = datetime.now(timezone.utc).date()
        self.stages: list[StageResult] = []
        self._current_stage: Optional[StageResult] = None

    def begin_stage(self, stage: str, rows_in: Optional[int] = None):
        """Mark the start of a pipeline stage."""
        self._current_stage = StageResult(
            stage=stage,
            started_at=datetime.now(timezone.utc),
            rows_in=rows_in,
        )

    def end_stage(
        self,
        rows_out: Optional[int] = None,
        status: str = "SUCCESS",
        error: Optional[str] = None,
    ):
        """Mark the end of the current stage."""
        if self._current_stage is None:
            logger.warning("end_stage called without begin_stage")
            return
        self._current_stage.ended_at = datetime.now(timezone.utc)
        self._current_stage.rows_out = rows_out
        self._current_stage.status = status
        self._current_stage.error = error
        self.stages.append(self._current_stage)
        self._current_stage = None

    def check_row_delta(
        self, rows_in: Optional[int], rows_out: Optional[int], strict: bool = True
    ) -> bool:
        """Check if a stage produced zero rows from non-empty input.

        Returns True if the delta is acceptable, False if it looks like a failure.
        """
        if rows_in is None or rows_out is None:
            return True
        if rows_in > 0 and rows_out == 0 and strict:
            return False
        return True

    @property
    def has_failures(self) -> bool:
        return any(s.status == "FAILURE" for s in self.stages)

    def to_dataframe(self) -> pd.DataFrame:
        """Convert all stage results to a DataFrame for BigQuery insertion."""
        rows = []
        for s in self.stages:
            rows.append(
                {
                    "run_id": self.run_id,
                    "stage": s.stage,
                    "started_at": s.started_at,
                    "ended_at": s.ended_at,
                    "rows_in": s.rows_in,
                    "rows_out": s.rows_out,
                    "status": s.status,
                    "error": s.error,
                    "run_date": self.run_date,
                }
            )
        return pd.DataFrame(rows)

    def summary(self) -> str:
        """Structured JSON summary for stdout logging."""
        stages_summary = []
        for s in self.stages:
            entry = {
                "stage": s.stage,
                "status": s.status,
                "rows_in": s.rows_in,
                "rows_out": s.rows_out,
            }
            if s.error:
                entry["error"] = s.error[:500]
            if s.started_at and s.ended_at:
                entry["duration_s"] = round(
                    (s.ended_at - s.started_at).total_seconds(), 1
                )
            stages_summary.append(entry)

        return json.dumps(
            {
                "run_id": self.run_id,
                "run_date": str(self.run_date),
                "has_failures": self.has_failures,
                "stages": stages_summary,
            },
            indent=2,
        )

    def persist(self, db):
        """Write stage results to BigQuery pipeline_runs table."""
        if not self.stages:
            logger.warning("No stages to persist")
            return
        df = self.to_dataframe()
        try:
            db.append_dataframe_to_table(df, PIPELINE_RUNS_TABLE)
            logger.info(
                f"Persisted {len(self.stages)} stage results to {PIPELINE_RUNS_TABLE}"
            )
        except Exception as e:
            logger.error(f"Failed to persist pipeline telemetry: {e}")


def ensure_pipeline_runs_table(db):
    """Create the pipeline_runs table if it doesn't exist."""
    if not db.table_exists(PIPELINE_RUNS_TABLE):
        logger.info(f"Creating {PIPELINE_RUNS_TABLE} table...")
        db.execute(PIPELINE_RUNS_SCHEMA)
        logger.info(f"{PIPELINE_RUNS_TABLE} table created.")
    else:
        logger.info(f"{PIPELINE_RUNS_TABLE} table already exists.")
