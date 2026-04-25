"""Unit tests for SourceReputationEngine (SP23-2, GH-#84)."""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.source_reputation import (
    HIGH_ACCURACY_THRESHOLD,
    LOW_ACCURACY_THRESHOLD,
    MIN_RESOLVED_PREDICTIONS,
    PENALTY_WEIGHT,
    SUPPRESS_THRESHOLD,
    UNVERIFIED_WEIGHT,
    SourceReputationEngine,
    _compute_weight,
    compute_and_persist,
    extract_domain,
)


def _make_db(domain_weights=None):
    db = MagicMock()
    db.project_id = "test-project"
    if domain_weights is not None:
        df = pd.DataFrame(
            [
                {"source_domain": d, "reputation_weight": w}
                for d, w in domain_weights.items()
            ]
        )
        db.fetch_df.return_value = df
    else:
        db.fetch_df.return_value = pd.DataFrame([{"n": 5}])
    return db


# ---------------------------------------------------------------------------
# _compute_weight unit tests
# ---------------------------------------------------------------------------


class TestComputeWeight:
    def test_unverified_source_gets_full_weight(self):
        weight = _compute_weight(accuracy_rate=0.1, resolved_count=3)
        assert weight == UNVERIFIED_WEIGHT

    def test_none_accuracy_gets_full_weight(self):
        weight = _compute_weight(accuracy_rate=None, resolved_count=100)
        assert weight == UNVERIFIED_WEIGHT

    def test_high_accuracy_gets_max_weight(self):
        weight = _compute_weight(
            accuracy_rate=HIGH_ACCURACY_THRESHOLD, resolved_count=50
        )
        assert weight == 1.0

    def test_above_high_threshold_gets_max_weight(self):
        weight = _compute_weight(accuracy_rate=0.85, resolved_count=100)
        assert weight == 1.0

    def test_below_suppress_threshold_gets_zero(self):
        weight = _compute_weight(
            accuracy_rate=SUPPRESS_THRESHOLD - 0.01, resolved_count=50
        )
        assert weight == 0.0

    def test_low_accuracy_gets_penalty_weight(self):
        # Between SUPPRESS_THRESHOLD and LOW_ACCURACY_THRESHOLD
        mid = (SUPPRESS_THRESHOLD + LOW_ACCURACY_THRESHOLD) / 2
        weight = _compute_weight(accuracy_rate=mid, resolved_count=50)
        assert weight == PENALTY_WEIGHT

    def test_mid_accuracy_gets_interpolated_weight(self):
        # Mid between LOW and HIGH threshold → should be ~0.75
        mid = (LOW_ACCURACY_THRESHOLD + HIGH_ACCURACY_THRESHOLD) / 2
        weight = _compute_weight(accuracy_rate=mid, resolved_count=50)
        assert 0.5 < weight < 1.0


# ---------------------------------------------------------------------------
# extract_domain
# ---------------------------------------------------------------------------


class TestExtractDomain:
    def test_extracts_domain_from_full_url(self):
        assert extract_domain("https://www.espn.com/nfl/story") == "espn.com"

    def test_strips_www(self):
        assert (
            extract_domain("http://www.profootballtalk.com/foo")
            == "profootballtalk.com"
        )

    def test_no_www(self):
        assert (
            extract_domain("https://theathletic.com/article/123") == "theathletic.com"
        )

    def test_empty_string(self):
        assert extract_domain("") == ""

    def test_domain_only(self):
        assert extract_domain("espn.com/nfl") == "espn.com"


# ---------------------------------------------------------------------------
# SourceReputationEngine
# ---------------------------------------------------------------------------


class TestComputeReputation:
    def test_executes_create_or_replace_sql(self):
        db = _make_db()
        engine = SourceReputationEngine(db=db)
        engine.compute_reputation()
        sql = db.execute.call_args[0][0]
        assert "CREATE OR REPLACE TABLE" in sql
        assert "source_reputation" in sql

    def test_sql_includes_reputation_weight_case(self):
        db = _make_db()
        engine = SourceReputationEngine(db=db)
        engine.compute_reputation()
        sql = db.execute.call_args[0][0]
        assert "reputation_weight" in sql
        assert "SUPPRESSED" in sql

    def test_returns_row_count(self):
        db = MagicMock()
        db.fetch_df.return_value = pd.DataFrame([{"n": 47}])
        engine = SourceReputationEngine(db=db)
        n = engine.compute_reputation()
        assert n == 47

    def test_invalidates_cache_after_compute(self):
        db = _make_db({"espn.com": 0.9})
        engine = SourceReputationEngine(db=db)
        # Load cache
        _ = engine.get_weight("espn.com")
        assert engine._cache is not None
        # After compute, cache is cleared
        db.fetch_df.return_value = pd.DataFrame([{"n": 3}])
        engine.compute_reputation()
        assert engine._cache is None


class TestGetWeight:
    def test_known_domain_returns_stored_weight(self):
        db = _make_db({"espn.com": 0.85, "lowquality.xyz": 0.0})
        engine = SourceReputationEngine(db=db)
        assert engine.get_weight("espn.com") == 0.85

    def test_unknown_domain_returns_full_weight(self):
        db = _make_db({"espn.com": 0.85})
        engine = SourceReputationEngine(db=db)
        assert engine.get_weight("newblog.com") == UNVERIFIED_WEIGHT

    def test_suppressed_domain_returns_zero(self):
        db = _make_db({"badactor.io": 0.0})
        engine = SourceReputationEngine(db=db)
        assert engine.get_weight("badactor.io") == 0.0

    def test_cache_is_populated_on_first_access(self):
        db = _make_db({"espn.com": 1.0})
        engine = SourceReputationEngine(db=db)
        assert engine._cache is None
        engine.get_weight("espn.com")
        assert engine._cache is not None
        # Second call does NOT re-query DB
        initial_call_count = db.fetch_df.call_count
        engine.get_weight("espn.com")
        assert db.fetch_df.call_count == initial_call_count

    def test_db_error_falls_back_to_full_weight(self):
        db = MagicMock()
        db.execute.return_value = MagicMock()
        db.fetch_df.side_effect = Exception("BQ unavailable")
        engine = SourceReputationEngine(db=db)
        weight = engine.get_weight("any.com")
        assert weight == UNVERIFIED_WEIGHT


class TestSuppressedSources:
    def test_returns_only_zero_weight_domains(self):
        db = _make_db({"good.com": 1.0, "ok.com": 0.5, "bad.io": 0.0, "evil.xyz": 0.0})
        engine = SourceReputationEngine(db=db)
        suppressed = engine.suppressed_sources()
        assert suppressed == {"bad.io", "evil.xyz"}

    def test_empty_when_no_suppressed(self):
        db = _make_db({"espn.com": 1.0, "nfl.com": 0.9})
        engine = SourceReputationEngine(db=db)
        assert engine.suppressed_sources() == set()


class TestModuleEntryPoint:
    def test_compute_and_persist_calls_engine(self):
        db = MagicMock()
        db.fetch_df.return_value = pd.DataFrame([{"n": 12}])
        result = compute_and_persist(db=db)
        assert result == 12
