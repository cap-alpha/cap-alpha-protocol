"""
Unit tests for post-ingestion data quality checks (SP29-2 / GH-#107).
No BigQuery required — all checks operate on in-memory DataFrames.
"""

import pytest
import pandas as pd
import numpy as np

from src.data_quality_tests import (
    CAP_FIGURE_MIN_COVERAGE,
    DataQualityAlert,
    QualityReport,
    QualityViolation,
    check_missing_cap_figures,
    check_stddev_outliers,
    run_post_ingestion_checks,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _contracts_df(cap_hit_values=None):
    """Build a silver_spotrac_contracts-shaped DataFrame for testing."""
    if cap_hit_values is None:
        cap_hit_values = [10.0, 12.0, 15.0, 11.0, 13.0]
    return pd.DataFrame(
        {
            "contract_id": [f"c{i}" for i in range(len(cap_hit_values))],
            "player_name": [f"Player {i}" for i in range(len(cap_hit_values))],
            "team": ["KC"] * len(cap_hit_values),
            "year": [2024] * len(cap_hit_values),
            "cap_hit_millions": cap_hit_values,
            "dead_cap_millions": [2.0] * len(cap_hit_values),
            "system_ingest_time": ["2024-01-01 00:00:00"] * len(cap_hit_values),
        }
    )


def _efficiency_df(cap_hit_values=None):
    """Build a fact_player_efficiency-shaped DataFrame for testing."""
    if cap_hit_values is None:
        cap_hit_values = [20.0, 25.0, 30.0, 22.0, 28.0]
    return pd.DataFrame(
        {
            "player_name": [f"Player {i}" for i in range(len(cap_hit_values))],
            "team": ["KC"] * len(cap_hit_values),
            "year": [2024] * len(cap_hit_values),
            "position": ["QB"] * len(cap_hit_values),
            "games_played": [17] * len(cap_hit_values),
            "cap_hit_millions": cap_hit_values,
        }
    )


# ---------------------------------------------------------------------------
# check_stddev_outliers
# ---------------------------------------------------------------------------


class TestCheckStddevOutliers:
    def test_no_violations_on_normal_data(self):
        df = _contracts_df([10.0, 12.0, 15.0, 11.0, 13.0])
        violations = check_stddev_outliers(df, "silver_spotrac_contracts")
        assert violations == []

    def test_extreme_outlier_flagged(self):
        # Insert a 1000M cap hit among normal 10-15M values
        df = _contracts_df([10.0, 12.0, 15.0, 11.0, 13.0, 1000.0])
        violations = check_stddev_outliers(df, "silver_spotrac_contracts")
        cap_violations = [v for v in violations if v.column == "cap_hit_millions"]
        assert len(cap_violations) == 1
        assert cap_violations[0].severity == "WARNING"

    def test_violation_contains_column_name(self):
        df = _contracts_df([10.0, 12.0, 15.0, 11.0, 13.0, 5000.0])
        violations = check_stddev_outliers(df, "silver_spotrac_contracts")
        assert any("cap_hit_millions" in v.column for v in violations)

    def test_unknown_table_returns_no_violations(self):
        df = pd.DataFrame({"some_col": [1, 2, 999]})
        violations = check_stddev_outliers(df, "nonexistent_table")
        assert violations == []

    def test_empty_dataframe_returns_no_violations(self):
        df = pd.DataFrame({"cap_hit_millions": []})
        violations = check_stddev_outliers(df, "silver_spotrac_contracts")
        assert violations == []

    def test_too_few_rows_skipped(self):
        # < 5 rows — can't compute meaningful stats
        df = _contracts_df([10.0, 100.0, 5.0])
        violations = check_stddev_outliers(df, "silver_spotrac_contracts")
        assert violations == []

    def test_missing_column_silently_skipped(self):
        df = pd.DataFrame({"player_name": ["A", "B", "C", "D", "E"]})
        # cap_hit_millions not in df — should not raise
        violations = check_stddev_outliers(df, "silver_spotrac_contracts")
        assert violations == []

    def test_custom_num_std_override(self):
        # With a very tight threshold of 0.1 sigma, any variance triggers a flag
        df = _contracts_df([10.0, 10.1, 10.2, 10.3, 10.4, 10.5])
        violations = check_stddev_outliers(df, "silver_spotrac_contracts", num_std=0.1)
        assert len(violations) > 0

    def test_fact_player_efficiency_checked(self):
        df = _efficiency_df([20.0, 22.0, 25.0, 21.0, 23.0, 9000.0])
        violations = check_stddev_outliers(df, "fact_player_efficiency")
        assert any(v.column == "cap_hit_millions" for v in violations)

    def test_all_violations_are_warning_severity(self):
        df = _contracts_df([10.0, 12.0, 15.0, 11.0, 13.0, 9999.0])
        violations = check_stddev_outliers(df, "silver_spotrac_contracts")
        for v in violations:
            assert v.severity == "WARNING"


# ---------------------------------------------------------------------------
# check_missing_cap_figures
# ---------------------------------------------------------------------------


class TestCheckMissingCapFigures:
    def test_all_positive_passes(self):
        df = _contracts_df([10.0, 12.0, 15.0, 11.0, 13.0])
        violations = check_missing_cap_figures(df, "silver_spotrac_contracts")
        assert violations == []

    def test_all_zero_raises_critical(self):
        df = _contracts_df([0.0, 0.0, 0.0, 0.0, 0.0])
        violations = check_missing_cap_figures(df, "silver_spotrac_contracts")
        assert any(v.severity == "CRITICAL" for v in violations)

    def test_mostly_zero_below_threshold_critical(self):
        # 1/10 positive = 10% coverage < 90% threshold
        values = [0.0] * 9 + [10.0]
        df = _contracts_df(values)
        violations = check_missing_cap_figures(df, "silver_spotrac_contracts")
        cap_v = [v for v in violations if v.column == "cap_hit_millions"]
        assert len(cap_v) == 1

    def test_coverage_above_threshold_passes(self):
        # 10/10 positive = 100% coverage
        df = _contracts_df([5.0] * 10)
        violations = check_missing_cap_figures(df, "silver_spotrac_contracts")
        assert violations == []

    def test_missing_column_raises_critical(self):
        df = pd.DataFrame({"player_name": ["A", "B", "C"]})
        violations = check_missing_cap_figures(df, "silver_spotrac_contracts")
        assert any(v.severity == "CRITICAL" for v in violations)
        assert any("missing entirely" in v.details for v in violations)

    def test_unknown_table_no_violations(self):
        df = pd.DataFrame({"some_col": [1, 2, 3]})
        violations = check_missing_cap_figures(df, "nonexistent_table")
        assert violations == []

    def test_null_values_treated_as_non_positive(self):
        values = [None, None, None, None, None, None, None, None, None, 10.0]
        df = _contracts_df(values)
        violations = check_missing_cap_figures(df, "silver_spotrac_contracts")
        cap_v = [v for v in violations if v.column == "cap_hit_millions"]
        assert len(cap_v) == 1

    def test_fact_player_efficiency_checked(self):
        df = _efficiency_df([0.0] * 10)
        violations = check_missing_cap_figures(df, "fact_player_efficiency")
        assert any(v.column == "cap_hit_millions" for v in violations)


# ---------------------------------------------------------------------------
# run_post_ingestion_checks
# ---------------------------------------------------------------------------


class TestRunPostIngestionChecks:
    def test_clean_data_returns_passing_report(self):
        df = _contracts_df([10.0, 12.0, 15.0, 11.0, 13.0])
        report = run_post_ingestion_checks(df, "silver_spotrac_contracts", raise_on_critical=False)
        assert isinstance(report, QualityReport)
        assert report.passed is True
        assert report.table_name == "silver_spotrac_contracts"
        assert report.row_count == 5

    def test_critical_violation_raises_when_raise_enabled(self):
        df = _contracts_df([0.0] * 10)
        with pytest.raises(DataQualityAlert, match="silver_spotrac_contracts"):
            run_post_ingestion_checks(df, "silver_spotrac_contracts", raise_on_critical=True)

    def test_critical_violation_no_raise_when_disabled(self):
        df = _contracts_df([0.0] * 10)
        report = run_post_ingestion_checks(df, "silver_spotrac_contracts", raise_on_critical=False)
        assert report.passed is False
        assert any(v.severity == "CRITICAL" for v in report.violations)

    def test_warning_only_does_not_raise(self):
        # Outlier triggers WARNING only
        df = _contracts_df([10.0, 12.0, 15.0, 11.0, 13.0, 9999.0])
        report = run_post_ingestion_checks(df, "silver_spotrac_contracts", raise_on_critical=True)
        assert report.passed is True  # CRITICAL=0, WARNING>0 → passed

    def test_warning_only_sets_passed_true(self):
        df = _contracts_df([10.0, 12.0, 15.0, 11.0, 13.0, 9999.0])
        report = run_post_ingestion_checks(df, "silver_spotrac_contracts", raise_on_critical=False)
        assert report.passed is True
        warnings = [v for v in report.violations if v.severity == "WARNING"]
        assert len(warnings) > 0

    def test_unknown_table_returns_clean_report(self):
        df = pd.DataFrame({"some_col": [1, 2, 3]})
        report = run_post_ingestion_checks(df, "unknown_table", raise_on_critical=False)
        assert report.passed is True
        assert report.violations == []

    def test_empty_dataframe_returns_clean_report(self):
        df = pd.DataFrame()
        report = run_post_ingestion_checks(df, "silver_spotrac_contracts", raise_on_critical=False)
        assert report.passed is True

    def test_report_bool_true_when_passed(self):
        df = _contracts_df([10.0, 12.0, 15.0, 11.0, 13.0])
        report = run_post_ingestion_checks(df, "silver_spotrac_contracts", raise_on_critical=False)
        assert bool(report) is True

    def test_report_bool_false_when_failed(self):
        df = _contracts_df([0.0] * 10)
        report = run_post_ingestion_checks(df, "silver_spotrac_contracts", raise_on_critical=False)
        assert bool(report) is False

    def test_report_summary_contains_table_name(self):
        df = _contracts_df([10.0, 12.0, 15.0, 11.0, 13.0])
        report = run_post_ingestion_checks(df, "silver_spotrac_contracts", raise_on_critical=False)
        assert "silver_spotrac_contracts" in report.summary()
