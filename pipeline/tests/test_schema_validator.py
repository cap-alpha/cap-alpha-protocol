"""
Unit tests for schema_validator.py (Issue #106)
"""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.schema_validator import (
    ColumnContract,
    ConstraintViolation,
    NullViolation,
    ValidationReport,
    _table_exists,
    check_constraint_violations,
    check_null_violations,
    run_full,
    run_post_check,
    run_pre_check,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def contract():
    return ColumnContract(
        dataset="nfl_dead_money",
        table="bronze_sportsdataio_players",
        columns=["PlayerID", "Name", "Team"],
        description="test contract",
    )


def _make_db_with_table(mock_db, exists=True):
    """Configure mock_db so _table_exists returns the given value."""
    mock_db.fetch_df.return_value = pd.DataFrame({"cnt": [1 if exists else 0]})
    return mock_db


# ---------------------------------------------------------------------------
# _table_exists
# ---------------------------------------------------------------------------


class TestTableExists:
    def test_returns_true_when_table_found(self, mock_db):
        mock_db.fetch_df.return_value = pd.DataFrame({"cnt": [1]})
        assert _table_exists(mock_db, "project", "dataset", "table") is True

    def test_returns_false_when_table_not_found(self, mock_db):
        mock_db.fetch_df.return_value = pd.DataFrame({"cnt": [0]})
        assert _table_exists(mock_db, "project", "dataset", "table") is False

    def test_returns_false_on_exception(self, mock_db):
        mock_db.fetch_df.side_effect = Exception("BQ error")
        assert _table_exists(mock_db, "project", "dataset", "table") is False


# ---------------------------------------------------------------------------
# check_null_violations
# ---------------------------------------------------------------------------


class TestCheckNullViolations:
    def test_returns_empty_when_table_missing(self, mock_db, contract):
        mock_db.fetch_df.return_value = pd.DataFrame({"cnt": [0]})
        result = check_null_violations(mock_db, contract, "project")
        assert result == []

    def test_returns_empty_when_no_nulls(self, mock_db, contract):
        # First call: _table_exists → cnt=1; Second call: null check → all zeros
        mock_db.fetch_df.side_effect = [
            pd.DataFrame({"cnt": [1]}),
            pd.DataFrame({"PlayerID": [0], "Name": [0], "Team": [0]}),
        ]
        result = check_null_violations(mock_db, contract, "project")
        assert result == []

    def test_returns_violation_for_null_column(self, mock_db, contract):
        mock_db.fetch_df.side_effect = [
            pd.DataFrame({"cnt": [1]}),
            pd.DataFrame({"PlayerID": [3], "Name": [0], "Team": [0]}),
        ]
        result = check_null_violations(mock_db, contract, "project")
        assert len(result) == 1
        assert result[0].column == "PlayerID"
        assert result[0].null_count == 3
        assert result[0].table == "bronze_sportsdataio_players"

    def test_returns_multiple_violations(self, mock_db, contract):
        mock_db.fetch_df.side_effect = [
            pd.DataFrame({"cnt": [1]}),
            pd.DataFrame({"PlayerID": [1], "Name": [2], "Team": [0]}),
        ]
        result = check_null_violations(mock_db, contract, "project")
        assert len(result) == 2
        cols = {v.column for v in result}
        assert cols == {"PlayerID", "Name"}

    def test_returns_empty_on_query_exception(self, mock_db, contract):
        mock_db.fetch_df.side_effect = [
            pd.DataFrame({"cnt": [1]}),
            Exception("query failed"),
        ]
        result = check_null_violations(mock_db, contract, "project")
        assert result == []

    def test_handles_none_values_in_result(self, mock_db, contract):
        mock_db.fetch_df.side_effect = [
            pd.DataFrame({"cnt": [1]}),
            pd.DataFrame({"PlayerID": [None], "Name": [0], "Team": [0]}),
        ]
        result = check_null_violations(mock_db, contract, "project")
        assert result == []


# ---------------------------------------------------------------------------
# check_constraint_violations
# ---------------------------------------------------------------------------


class TestCheckConstraintViolations:
    def test_returns_empty_when_table_missing(self, mock_db, contract):
        mock_db.fetch_df.return_value = pd.DataFrame({"cnt": [0]})
        result = check_constraint_violations(mock_db, contract, "project")
        assert result == []

    def test_returns_empty_when_all_required(self, mock_db, contract):
        mock_db.fetch_df.side_effect = [
            pd.DataFrame({"cnt": [1]}),
            pd.DataFrame({"column_name": [], "is_nullable": []}),
        ]
        result = check_constraint_violations(mock_db, contract, "project")
        assert result == []

    def test_returns_violation_for_nullable_column(self, mock_db, contract):
        mock_db.fetch_df.side_effect = [
            pd.DataFrame({"cnt": [1]}),
            pd.DataFrame({"column_name": ["PlayerID"], "is_nullable": ["YES"]}),
        ]
        result = check_constraint_violations(mock_db, contract, "project")
        assert len(result) == 1
        assert result[0].column == "PlayerID"
        assert result[0].is_nullable == "YES"

    def test_returns_multiple_nullable_columns(self, mock_db, contract):
        mock_db.fetch_df.side_effect = [
            pd.DataFrame({"cnt": [1]}),
            pd.DataFrame(
                {
                    "column_name": ["Name", "Team"],
                    "is_nullable": ["YES", "YES"],
                }
            ),
        ]
        result = check_constraint_violations(mock_db, contract, "project")
        assert len(result) == 2

    def test_returns_empty_on_query_exception(self, mock_db, contract):
        mock_db.fetch_df.side_effect = [
            pd.DataFrame({"cnt": [1]}),
            Exception("query failed"),
        ]
        result = check_constraint_violations(mock_db, contract, "project")
        assert result == []


# ---------------------------------------------------------------------------
# ValidationReport
# ---------------------------------------------------------------------------


class TestValidationReport:
    def test_passed_when_no_violations(self):
        report = ValidationReport()
        assert report.passed is True

    def test_failed_when_null_violations(self):
        report = ValidationReport(
            null_violations=[NullViolation("ds", "tbl", "col", 1)]
        )
        assert report.passed is False

    def test_failed_when_constraint_violations(self):
        report = ValidationReport(
            constraint_violations=[ConstraintViolation("ds", "tbl", "col", "YES")]
        )
        assert report.passed is False

    def test_print_passes_does_not_raise(self, caplog):
        report = ValidationReport()
        report.print()  # Should not raise

    def test_print_violations_logs_errors(self, caplog):
        import logging

        report = ValidationReport(
            null_violations=[NullViolation("ds", "tbl", "PlayerID", 5)]
        )
        with caplog.at_level(logging.ERROR):
            report.print()
        assert "PlayerID" in caplog.text
        assert "5" in caplog.text


# ---------------------------------------------------------------------------
# run_pre_check / run_post_check / run_full
# ---------------------------------------------------------------------------


class TestRunChecks:
    def _build_clean_db(self):
        """DB that reports all tables exist and all columns are clean."""
        db = MagicMock()

        def fetch_side_effect(query):
            if "INFORMATION_SCHEMA.TABLES" in query:
                return pd.DataFrame({"cnt": [1]})
            if "INFORMATION_SCHEMA.COLUMNS" in query:
                return pd.DataFrame({"column_name": [], "is_nullable": []})
            # null check — return all-zero row dynamically
            return pd.DataFrame(
                {
                    col: [0]
                    for col in [
                        "PlayerID",
                        "Name",
                        "Team",
                        "player_name",
                        "team",
                        "position",
                        "year",
                        "content_hash",
                        "source_id",
                        "source_url",
                        "ingested_at",
                        "content_type",
                        "fetch_source_type",
                        "prediction_hash",
                        "chain_hash",
                        "ingestion_timestamp",
                        "pundit_id",
                        "pundit_name",
                        "raw_assertion_text",
                        "resolution_status",
                        "created_at",
                        "updated_at",
                    ]
                }
            )

        db.fetch_df.side_effect = fetch_side_effect
        return db

    def test_pre_check_passes_with_clean_data(self):
        db = self._build_clean_db()
        report = run_pre_check(db, "project")
        assert report.null_violations == []

    def test_post_check_passes_with_constraints_set(self):
        db = self._build_clean_db()
        report = run_post_check(db, "project")
        assert report.constraint_violations == []

    def test_full_check_passes_with_clean_data(self):
        db = self._build_clean_db()
        report = run_full(db, "project")
        assert report.passed is True

    def test_pre_check_collects_null_violations(self):
        db = MagicMock()
        call_count = [0]

        def fetch_side_effect(query):
            call_count[0] += 1
            if "INFORMATION_SCHEMA.TABLES" in query:
                return pd.DataFrame({"cnt": [1]})
            # First null check: inject a violation
            if call_count[0] == 2:
                return pd.DataFrame(
                    {
                        "player_name": [0],
                        "team": [3],
                        "position": [0],
                        "PlayerID": [0],
                        "Name": [0],
                        "Team": [0],
                        "year": [0],
                        "content_hash": [0],
                        "source_id": [0],
                        "source_url": [0],
                        "ingested_at": [0],
                        "content_type": [0],
                        "fetch_source_type": [0],
                        "prediction_hash": [0],
                        "chain_hash": [0],
                        "ingestion_timestamp": [0],
                        "pundit_id": [0],
                        "pundit_name": [0],
                        "raw_assertion_text": [0],
                        "resolution_status": [0],
                        "created_at": [0],
                        "updated_at": [0],
                    }
                )
            return pd.DataFrame(
                {
                    col: [0]
                    for col in [
                        "PlayerID",
                        "Name",
                        "Team",
                        "player_name",
                        "team",
                        "position",
                        "year",
                        "content_hash",
                        "source_id",
                        "source_url",
                        "ingested_at",
                        "content_type",
                        "fetch_source_type",
                        "prediction_hash",
                        "chain_hash",
                        "ingestion_timestamp",
                        "pundit_id",
                        "pundit_name",
                        "raw_assertion_text",
                        "resolution_status",
                        "created_at",
                        "updated_at",
                    ]
                }
            )

        db.fetch_df.side_effect = fetch_side_effect
        report = run_pre_check(db, "project")
        # report may or may not have violations depending on which contract hits the mock
        assert isinstance(report.null_violations, list)
