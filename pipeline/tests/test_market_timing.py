"""
Unit tests for pipeline/src/market_timing.py (Issue #811).

No BigQuery or network calls required — DBManager is fully mocked.
"""

import re
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pandas as pd
import pytest

from src.market_timing import (
    MARKET_TIMING_TABLE,
    _build_merge_sql,
    compute_market_timing,
    get_market_timing_summary,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FIXED_TS = datetime(2026, 5, 8, 12, 0, 0, tzinfo=timezone.utc)
FIXED_TS_STR = "2026-05-08T12:00:00"
PROJECT_ID = "test-project"


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.project_id = PROJECT_ID
    db.execute.return_value = MagicMock(job=MagicMock(num_dml_affected_rows=5))
    db.fetch_df.return_value = pd.DataFrame()
    return db


# ---------------------------------------------------------------------------
# _build_merge_sql
# ---------------------------------------------------------------------------


class TestBuildMergeSql:
    def test_contains_project_id(self):
        sql = _build_merge_sql(PROJECT_ID, FIXED_TS_STR)
        assert PROJECT_ID in sql

    def test_targets_correct_table(self):
        sql = _build_merge_sql(PROJECT_ID, FIXED_TS_STR)
        assert "pundit_market_timing" in sql

    def test_uses_merge_syntax(self):
        sql = _build_merge_sql(PROJECT_ID, FIXED_TS_STR)
        assert "MERGE" in sql.upper()
        assert "WHEN MATCHED THEN" in sql.upper()
        assert "WHEN NOT MATCHED THEN" in sql.upper()

    def test_joins_ledger_and_resolutions(self):
        sql = _build_merge_sql(PROJECT_ID, FIXED_TS_STR)
        assert "prediction_ledger" in sql
        assert "prediction_resolutions" in sql

    def test_excludes_void_resolutions(self):
        sql = _build_merge_sql(PROJECT_ID, FIXED_TS_STR)
        # Must filter to CORRECT|INCORRECT only
        assert "CORRECT" in sql
        assert "INCORRECT" in sql
        assert "VOID" not in sql

    def test_uses_timestamp_diff_not_datediff(self):
        sql = _build_merge_sql(PROJECT_ID, FIXED_TS_STR)
        assert "TIMESTAMP_DIFF" in sql
        # BQ-native: no DATEDIFF
        assert "DATEDIFF" not in sql.upper()

    def test_uses_percentile_cont(self):
        sql = _build_merge_sql(PROJECT_ID, FIXED_TS_STR)
        assert "PERCENTILE_CONT" in sql

    def test_embeds_computed_at_timestamp(self):
        sql = _build_merge_sql(PROJECT_ID, FIXED_TS_STR)
        assert FIXED_TS_STR in sql

    def test_no_varchar(self):
        sql = _build_merge_sql(PROJECT_ID, FIXED_TS_STR)
        assert "VARCHAR" not in sql.upper()

    def test_no_try_cast(self):
        sql = _build_merge_sql(PROJECT_ID, FIXED_TS_STR)
        assert "TRY_CAST" not in sql.upper()

    def test_uses_float64_and_int64(self):
        sql = _build_merge_sql(PROJECT_ID, FIXED_TS_STR)
        assert "FLOAT64" in sql
        assert "INT64" in sql

    def test_non_negative_lead_time_filter(self):
        sql = _build_merge_sql(PROJECT_ID, FIXED_TS_STR)
        # Must guard against negative lead times (claim after resolution)
        assert ">= 0" in sql

    def test_upsert_columns_include_all_required(self):
        sql = _build_merge_sql(PROJECT_ID, FIXED_TS_STR)
        for col in [
            "pundit_id",
            "entity_class",
            "claim_type",
            "sport",
            "median_lead_hours",
            "sample_size",
            "computed_at",
        ]:
            assert col in sql, f"Missing column in SQL: {col}"


# ---------------------------------------------------------------------------
# compute_market_timing
# ---------------------------------------------------------------------------


class TestComputeMarketTiming:
    def test_dry_run_does_not_call_execute(self, mock_db):
        rows = compute_market_timing(mock_db, dry_run=True, computed_at=FIXED_TS)
        mock_db.execute.assert_not_called()
        assert rows == 0

    def test_executes_merge_on_normal_run(self, mock_db):
        compute_market_timing(mock_db, dry_run=False, computed_at=FIXED_TS)
        mock_db.execute.assert_called_once()

    def test_returns_rows_affected(self, mock_db):
        rows = compute_market_timing(mock_db, dry_run=False, computed_at=FIXED_TS)
        assert rows == 5

    def test_returns_zero_when_num_dml_none(self, mock_db):
        mock_db.execute.return_value = MagicMock(
            job=MagicMock(num_dml_affected_rows=None)
        )
        rows = compute_market_timing(mock_db, dry_run=False, computed_at=FIXED_TS)
        assert rows == 0

    def test_uses_provided_computed_at(self, mock_db):
        compute_market_timing(mock_db, dry_run=False, computed_at=FIXED_TS)
        call_sql = mock_db.execute.call_args[0][0]
        assert FIXED_TS_STR in call_sql

    def test_defaults_computed_at_to_now(self, mock_db):
        """No computed_at arg — should not raise and should call execute."""
        compute_market_timing(mock_db, dry_run=False)
        mock_db.execute.assert_called_once()

    def test_passes_project_id_from_db(self, mock_db):
        compute_market_timing(mock_db, dry_run=False, computed_at=FIXED_TS)
        call_sql = mock_db.execute.call_args[0][0]
        assert PROJECT_ID in call_sql


# ---------------------------------------------------------------------------
# get_market_timing_summary
# ---------------------------------------------------------------------------


class TestGetMarketTimingSummary:
    def test_calls_fetch_df_with_correct_table(self, mock_db):
        get_market_timing_summary(mock_db)
        mock_db.fetch_df.assert_called_once()
        sql = mock_db.fetch_df.call_args[0][0]
        assert "pundit_market_timing" in sql

    def test_empty_df_does_not_raise(self, mock_db):
        mock_db.fetch_df.return_value = pd.DataFrame()
        get_market_timing_summary(mock_db)  # Should not raise

    def test_non_empty_df_prints_summary(self, mock_db, capsys):
        mock_db.fetch_df.return_value = pd.DataFrame(
            {
                "sport": ["NFL"],
                "claim_type": ["trade"],
                "pundit_count": [3],
                "avg_median_lead_hours": [48.5],
                "total_predictions": [120],
                "last_computed": ["2026-05-08"],
            }
        )
        get_market_timing_summary(mock_db)
        out = capsys.readouterr().out
        assert "Pundit Market Timing Summary" in out
        assert "NFL" in out
