"""Unit tests for PostIngestionQualityGate (SP29-2)."""

from unittest.mock import MagicMock

import pytest

from src.post_ingestion_quality import PostIngestionQualityGate, QualityGateError


def _make_db():
    db = MagicMock()
    db.project_id = "test-project"
    db.dataset_id = "nfl_dead_money"
    return db


def _make_gate(db):
    return PostIngestionQualityGate(db, year=2025)


def _proxy(value):
    """Helper: return an execute() proxy whose fetchone() returns the given tuple."""
    p = MagicMock()
    p.fetchone.return_value = value
    return p


class TestNullCapFigures:
    def test_passes_when_null_rate_below_threshold(self):
        db = _make_db()
        db.execute.return_value = _proxy((5, 200))  # 2.5% null
        gate = _make_gate(db)
        result = gate.check_null_cap_figures()
        assert result.passed is True
        assert result.blocking is True

    def test_fails_when_null_rate_above_threshold(self):
        db = _make_db()
        db.execute.return_value = _proxy((50, 100))  # 50% null
        gate = _make_gate(db)
        result = gate.check_null_cap_figures()
        assert result.passed is False
        assert result.blocking is True

    def test_passes_when_no_rows(self):
        db = _make_db()
        db.execute.return_value = _proxy((0, 0))
        gate = _make_gate(db)
        result = gate.check_null_cap_figures()
        assert result.passed is True  # 0/0 = 0% null


class TestTeamCompleteness:
    def test_passes_when_all_32_teams_present(self):
        db = _make_db()
        db.execute.return_value = _proxy((32,))
        gate = _make_gate(db)
        result = gate.check_team_completeness()
        assert result.passed is True

    def test_fails_when_fewer_than_32_teams(self):
        db = _make_db()
        db.execute.return_value = _proxy((28,))
        gate = _make_gate(db)
        result = gate.check_team_completeness()
        assert result.passed is False
        assert result.blocking is True


class TestDuplicateContracts:
    def test_passes_when_no_duplicates(self):
        db = _make_db()
        db.execute.return_value = _proxy((0,))
        gate = _make_gate(db)
        result = gate.check_duplicate_contracts()
        assert result.passed is True

    def test_fails_when_duplicates_found(self):
        db = _make_db()
        db.execute.return_value = _proxy((3,))
        gate = _make_gate(db)
        result = gate.check_duplicate_contracts()
        assert result.passed is False
        assert result.blocking is True


class TestFreshness:
    def test_passes_when_recent(self):
        db = _make_db()
        db.execute.return_value = _proxy((2,))  # 2 hours old
        gate = _make_gate(db)
        result = gate.check_freshness()
        assert result.passed is True

    def test_fails_when_stale(self):
        db = _make_db()
        db.execute.return_value = _proxy((72,))  # 72 hours old
        gate = _make_gate(db)
        result = gate.check_freshness()
        assert result.passed is False
        assert result.blocking is True


class TestRunAll:
    def test_raises_quality_gate_error_on_blocking_failure(self):
        db = _make_db()
        gate = _make_gate(db)

        # Simulate check_null_cap_figures returning a blocking failure
        from src.post_ingestion_quality import QualityResult

        bad_result = QualityResult(
            check_name="null_cap_figures",
            passed=False,
            blocking=True,
            metric=0.5,
            threshold=0.15,
            message="50% nulls",
        )

        # Patch individual check methods
        gate.check_null_cap_figures = lambda: bad_result

        from src.post_ingestion_quality import QualityResult as QR

        def ok(name):
            return QR(
                check_name=name,
                passed=True,
                blocking=True,
                metric=0.0,
                threshold=0.0,
                message="ok",
            )

        gate.check_outlier_cap_figures = lambda: ok("outlier_cap_figures")
        gate.check_team_completeness = lambda: ok("team_completeness")
        gate.check_duplicate_contracts = lambda: ok("duplicate_contracts")
        gate.check_freshness = lambda: ok("freshness")

        with pytest.raises(QualityGateError):
            gate.run_all(raise_on_failure=True)

    def test_returns_results_without_raising_when_flag_off(self):
        db = _make_db()
        gate = _make_gate(db)

        from src.post_ingestion_quality import QualityResult as QR

        bad = QR(
            check_name="x",
            passed=False,
            blocking=True,
            metric=1.0,
            threshold=0.0,
            message="fail",
        )

        gate.check_null_cap_figures = lambda: bad
        gate.check_outlier_cap_figures = lambda: bad
        gate.check_team_completeness = lambda: bad
        gate.check_duplicate_contracts = lambda: bad
        gate.check_freshness = lambda: bad

        results = gate.run_all(raise_on_failure=False)
        assert len(results) == 5
        assert all(not r.passed for r in results)
