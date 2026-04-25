"""
Tests for pipeline telemetry (Issue #188).

Unit tests — no BigQuery required.
"""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, call, patch

import pandas as pd
import pytest
from src.pipeline_telemetry import (
    PIPELINE_RUNS_TABLE,
    PipelineRun,
    StageResult,
    ensure_pipeline_runs_table,
)

# ---------------------------------------------------------------------------
# StageResult
# ---------------------------------------------------------------------------


class TestStageResult:
    def test_defaults(self):
        sr = StageResult(stage="test", started_at=datetime.now(timezone.utc))
        assert sr.status == "SUCCESS"
        assert sr.error is None
        assert sr.rows_in is None
        assert sr.rows_out is None


# ---------------------------------------------------------------------------
# PipelineRun — stage tracking
# ---------------------------------------------------------------------------


class TestPipelineRun:
    def test_run_id_auto_generated(self):
        run = PipelineRun()
        assert len(run.run_id) == 32  # hex UUID without dashes

    def test_custom_run_id(self):
        run = PipelineRun(run_id="custom-123")
        assert run.run_id == "custom-123"

    def test_begin_end_stage(self):
        run = PipelineRun()
        run.begin_stage("ingest", rows_in=100)
        run.end_stage(rows_out=50)

        assert len(run.stages) == 1
        stage = run.stages[0]
        assert stage.stage == "ingest"
        assert stage.rows_in == 100
        assert stage.rows_out == 50
        assert stage.status == "SUCCESS"
        assert stage.started_at is not None
        assert stage.ended_at is not None
        assert stage.ended_at >= stage.started_at

    def test_end_stage_without_begin(self):
        run = PipelineRun()
        run.end_stage(rows_out=10)  # should not raise
        assert len(run.stages) == 0

    def test_failure_stage(self):
        run = PipelineRun()
        run.begin_stage("extract")
        run.end_stage(status="FAILURE", error="Connection timeout")

        assert run.stages[0].status == "FAILURE"
        assert run.stages[0].error == "Connection timeout"

    def test_multiple_stages(self):
        run = PipelineRun()
        for name in ["ingest", "extract", "transform"]:
            run.begin_stage(name)
            run.end_stage()
        assert len(run.stages) == 3
        assert [s.stage for s in run.stages] == ["ingest", "extract", "transform"]

    def test_has_failures_false(self):
        run = PipelineRun()
        run.begin_stage("ok")
        run.end_stage(status="SUCCESS")
        assert run.has_failures is False

    def test_has_failures_true(self):
        run = PipelineRun()
        run.begin_stage("ok")
        run.end_stage(status="SUCCESS")
        run.begin_stage("bad")
        run.end_stage(status="FAILURE", error="boom")
        assert run.has_failures is True


# ---------------------------------------------------------------------------
# Row-delta checks
# ---------------------------------------------------------------------------


class TestRowDeltaCheck:
    def test_none_inputs_always_acceptable(self):
        run = PipelineRun()
        assert run.check_row_delta(None, 0) is True
        assert run.check_row_delta(100, None) is True
        assert run.check_row_delta(None, None) is True

    def test_zero_in_zero_out_is_ok(self):
        run = PipelineRun()
        assert run.check_row_delta(0, 0) is True

    def test_nonempty_in_zero_out_strict_fails(self):
        run = PipelineRun()
        assert run.check_row_delta(100, 0, strict=True) is False

    def test_nonempty_in_zero_out_not_strict_ok(self):
        run = PipelineRun()
        assert run.check_row_delta(100, 0, strict=False) is True

    def test_normal_delta_is_ok(self):
        run = PipelineRun()
        assert run.check_row_delta(100, 50) is True


# ---------------------------------------------------------------------------
# DataFrame conversion
# ---------------------------------------------------------------------------


class TestToDataFrame:
    def test_columns(self):
        run = PipelineRun(run_id="abc123")
        run.begin_stage("test_stage", rows_in=10)
        run.end_stage(rows_out=5)

        df = run.to_dataframe()
        expected_cols = {
            "run_id",
            "stage",
            "started_at",
            "ended_at",
            "rows_in",
            "rows_out",
            "status",
            "error",
            "run_date",
        }
        assert set(df.columns) == expected_cols

    def test_values(self):
        run = PipelineRun(run_id="abc123")
        run.begin_stage("test_stage", rows_in=10)
        run.end_stage(rows_out=5, status="SUCCESS")

        df = run.to_dataframe()
        assert len(df) == 1
        row = df.iloc[0]
        assert row["run_id"] == "abc123"
        assert row["stage"] == "test_stage"
        assert row["rows_in"] == 10
        assert row["rows_out"] == 5
        assert row["status"] == "SUCCESS"

    def test_empty_run(self):
        run = PipelineRun()
        df = run.to_dataframe()
        assert len(df) == 0


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


class TestSummary:
    def test_summary_is_valid_json(self):
        run = PipelineRun(run_id="test-run")
        run.begin_stage("ingest", rows_in=100)
        run.end_stage(rows_out=50)
        run.begin_stage("extract")
        run.end_stage(status="FAILURE", error="timeout")

        summary = run.summary()
        parsed = json.loads(summary)
        assert parsed["run_id"] == "test-run"
        assert parsed["has_failures"] is True
        assert len(parsed["stages"]) == 2

    def test_summary_truncates_errors(self):
        run = PipelineRun()
        run.begin_stage("bad")
        run.end_stage(status="FAILURE", error="x" * 1000)

        summary = json.loads(run.summary())
        assert len(summary["stages"][0]["error"]) == 500


# ---------------------------------------------------------------------------
# Persist
# ---------------------------------------------------------------------------


class TestPersist:
    def test_persist_calls_append(self):
        db = MagicMock()
        run = PipelineRun(run_id="persist-test")
        run.begin_stage("ingest")
        run.end_stage()

        run.persist(db)

        db.append_dataframe_to_table.assert_called_once()
        args = db.append_dataframe_to_table.call_args
        df = args[0][0]
        table = args[0][1]
        assert table == PIPELINE_RUNS_TABLE
        assert len(df) == 1

    def test_persist_empty_run_skips(self):
        db = MagicMock()
        run = PipelineRun()
        run.persist(db)
        db.append_dataframe_to_table.assert_not_called()

    def test_persist_handles_db_error(self):
        db = MagicMock()
        db.append_dataframe_to_table.side_effect = Exception("BQ down")
        run = PipelineRun()
        run.begin_stage("x")
        run.end_stage()
        # Should not raise
        run.persist(db)


# ---------------------------------------------------------------------------
# ensure_pipeline_runs_table
# ---------------------------------------------------------------------------


class TestEnsureTable:
    def test_creates_if_not_exists(self):
        db = MagicMock()
        db.table_exists.return_value = False
        ensure_pipeline_runs_table(db)
        db.execute.assert_called_once()

    def test_skips_if_exists(self):
        db = MagicMock()
        db.table_exists.return_value = True
        ensure_pipeline_runs_table(db)
        db.execute.assert_not_called()
