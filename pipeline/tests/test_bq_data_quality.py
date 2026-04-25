"""
Unit tests for bq_data_quality module (SP29-2).

Tests that do not require BigQuery use plain logic tests.
BQ integration tests are skipped when GCP_PROJECT_ID is unset.
"""

import os

import pytest

from src.bq_data_quality import CheckResult, format_report, to_json


# ---------------------------------------------------------------------------
# CheckResult helpers
# ---------------------------------------------------------------------------


def make_result(status="OK", table="t", column="c", check="null_rate", detail=""):
    return CheckResult(
        table=table, column=column, check=check, status=status, detail=detail
    )


class TestCheckResult:
    def test_ok_result(self):
        r = make_result(status="OK", detail="0/1000 rows NULL (0.0%)")
        assert r.status == "OK"
        assert r.table == "t"

    def test_warning_result(self):
        r = make_result(status="WARNING", detail="60/1000 rows NULL (6.0%)")
        assert r.status == "WARNING"

    def test_error_result(self):
        r = make_result(status="ERROR", detail="250/1000 rows NULL (25.0%)")
        assert r.status == "ERROR"

    def test_null_column_allowed(self):
        r = CheckResult(table="t", column=None, check="row_count", status="OK", detail="ok")
        assert r.column is None


# ---------------------------------------------------------------------------
# format_report
# ---------------------------------------------------------------------------


class TestFormatReport:
    def test_includes_table_and_check(self):
        results = [make_result(table="silver_spotrac_contracts", check="null_rate", status="OK")]
        report = format_report(results)
        assert "silver_spotrac_contracts" in report
        assert "null_rate" in report

    def test_counts_in_footer(self):
        results = [
            make_result(status="OK"),
            make_result(status="WARNING"),
            make_result(status="ERROR"),
        ]
        report = format_report(results)
        assert "1 OK" in report
        assert "1 WARNING" in report
        assert "1 ERROR" in report

    def test_all_ok_report(self):
        results = [make_result(status="OK") for _ in range(3)]
        report = format_report(results)
        assert "3 OK" in report
        assert "0 WARNING" in report
        assert "0 ERROR" in report

    def test_status_icons(self):
        results = [
            make_result(status="OK"),
            make_result(status="WARNING"),
            make_result(status="ERROR"),
        ]
        report = format_report(results)
        assert "✓" in report
        assert "⚠" in report
        assert "✗" in report

    def test_no_column_result_in_report(self):
        r = CheckResult(
            table="silver_spotrac_contracts",
            column=None,
            check="row_count",
            status="OK",
            detail="54870 rows",
        )
        report = format_report([r])
        # Should not produce ".None" in output
        assert ".None" not in report


# ---------------------------------------------------------------------------
# to_json
# ---------------------------------------------------------------------------


class TestToJson:
    def test_valid_json(self):
        import json
        results = [make_result()]
        data = json.loads(to_json(results))
        assert isinstance(data, list)
        assert len(data) == 1

    def test_json_has_required_keys(self):
        import json
        results = [make_result(status="WARNING", detail="some detail")]
        data = json.loads(to_json(results))[0]
        for key in ("table", "column", "check", "status", "detail"):
            assert key in data

    def test_json_null_column(self):
        import json
        r = CheckResult(table="t", column=None, check="row_count", status="OK", detail="ok")
        data = json.loads(to_json([r]))[0]
        assert data["column"] is None

    def test_json_outlier_count(self):
        import json
        r = CheckResult(
            table="t", column="cap_hit_millions", check="cap_outliers",
            status="WARNING", detail="3 rows exceed 3σ", outlier_count=3
        )
        data = json.loads(to_json([r]))[0]
        assert data["outlier_count"] == 3

    def test_json_missing_years(self):
        import json
        r = CheckResult(
            table="t", column="year", check="year_coverage",
            status="ERROR", detail="Missing years: [2012, 2013]",
            missing_years=[2012, 2013]
        )
        data = json.loads(to_json([r]))[0]
        assert data["missing_years"] == [2012, 2013]


# ---------------------------------------------------------------------------
# BQ integration tests (skipped without GCP_PROJECT_ID)
# ---------------------------------------------------------------------------


BQ_AVAILABLE = bool(os.environ.get("GCP_PROJECT_ID"))


@pytest.mark.skipif(not BQ_AVAILABLE, reason="GCP_PROJECT_ID not set")
class TestBQIntegration:
    """Live BQ checks — only run in CI with GCP access."""

    def setup_method(self):
        from src.bq_data_quality import _client_and_project
        self.client, self.project = _client_and_project()

    def test_null_rate_returns_check_result(self):
        from src.bq_data_quality import check_null_rate
        result = check_null_rate(
            self.client, self.project, "silver_spotrac_contracts", "player_name"
        )
        assert isinstance(result, CheckResult)
        assert result.check == "null_rate"
        assert result.status in ("OK", "WARNING", "ERROR")
        assert result.value is not None

    def test_cap_outliers_returns_check_result(self):
        from src.bq_data_quality import check_cap_outliers
        result = check_cap_outliers(
            self.client, self.project, "silver_spotrac_contracts", "cap_hit_millions"
        )
        assert isinstance(result, CheckResult)
        assert result.check == "cap_outliers"
        assert result.outlier_count is not None

    def test_year_coverage_returns_check_result(self):
        from src.bq_data_quality import check_year_coverage
        result = check_year_coverage(
            self.client, self.project, "silver_spotrac_contracts"
        )
        assert isinstance(result, CheckResult)
        assert result.check == "year_coverage"

    def test_row_count_returns_check_result(self):
        from src.bq_data_quality import check_row_count
        result = check_row_count(
            self.client, self.project, "silver_spotrac_contracts", min_rows=100
        )
        assert isinstance(result, CheckResult)
        assert result.status == "OK"  # we know it has 54k rows

    def test_run_all_checks_returns_list(self):
        from src.bq_data_quality import run_all_checks
        results = run_all_checks(self.client, self.project)
        assert isinstance(results, list)
        assert len(results) > 0
        assert all(isinstance(r, CheckResult) for r in results)
