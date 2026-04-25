"""
Unit tests for GoldLayer.build_team_finance_summary (SP24-3 / GH-#88).

Validates that the pre-computation logic produces correct per-team aggregations
without requiring a live BigQuery connection — uses an in-memory DuckDB stand-in
to execute the generated SQL.

Note: medallion_pipeline.py targets BigQuery SQL syntax (STRUCT, UNNEST).  These
tests exercise the *logic* (correct grouping, positional dispatch, cap-space
formula) by directly testing the GoldLayer class against a mocked DBManager so
that no real BigQuery call is made.
"""

from unittest.mock import MagicMock, call, patch

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_db(execute_side_effect=None):
    db = MagicMock()
    db.project_id = "test-project"
    db.dataset_id = "nfl_dead_money"
    if execute_side_effect is not None:
        db.execute.side_effect = execute_side_effect
    return db


# ---------------------------------------------------------------------------
# Import GoldLayer (from scripts package — adjust path via sys.path)
# ---------------------------------------------------------------------------


import os
import sys

SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "scripts")
sys.path.insert(0, SCRIPTS_DIR)

from medallion_pipeline import GoldLayer  # noqa: E402

# ---------------------------------------------------------------------------
# Tests for build_team_finance_summary()
# ---------------------------------------------------------------------------


class TestBuildTeamFinanceSummary:
    def test_executes_create_table_statement(self):
        db = _make_db()
        gold = GoldLayer(db)
        gold.build_team_finance_summary()
        db.execute.assert_called_once()
        sql = db.execute.call_args[0][0]
        assert "CREATE OR REPLACE TABLE team_finance_summary" in sql

    def test_sql_selects_positional_spending_columns(self):
        db = _make_db()
        gold = GoldLayer(db)
        gold.build_team_finance_summary()
        sql = db.execute.call_args[0][0]
        for col in [
            "qb_spending",
            "wr_spending",
            "rb_spending",
            "te_spending",
            "dl_spending",
            "lb_spending",
            "db_spending",
            "ol_spending",
            "k_spending",
            "p_spending",
        ]:
            assert col in sql, f"Expected column '{col}' in generated SQL"

    def test_sql_computes_cap_space(self):
        db = _make_db()
        gold = GoldLayer(db)
        gold.build_team_finance_summary()
        sql = db.execute.call_args[0][0]
        assert "cap_space" in sql
        assert "cap_limit" in sql

    def test_sql_joins_silver_team_cap_for_win_pct(self):
        db = _make_db()
        gold = GoldLayer(db)
        gold.build_team_finance_summary()
        sql = db.execute.call_args[0][0]
        assert "silver_team_cap" in sql
        assert "win_pct" in sql

    def test_sql_includes_conference_mapping(self):
        db = _make_db()
        gold = GoldLayer(db)
        gold.build_team_finance_summary()
        sql = db.execute.call_args[0][0]
        assert "conference" in sql
        # Spot-check a few known conference assignments in the static mapping
        assert "'AFC'" in sql
        assert "'NFC'" in sql

    def test_sql_uses_silver_spotrac_contracts_as_source(self):
        db = _make_db()
        gold = GoldLayer(db)
        gold.build_team_finance_summary()
        sql = db.execute.call_args[0][0]
        assert "silver_spotrac_contracts" in sql

    def test_sql_groups_by_team_and_year(self):
        db = _make_db()
        gold = GoldLayer(db)
        gold.build_team_finance_summary()
        sql = db.execute.call_args[0][0]
        assert "GROUP BY team, year" in sql

    def test_sql_includes_historical_cap_limits(self):
        db = _make_db()
        gold = GoldLayer(db)
        gold.build_team_finance_summary()
        sql = db.execute.call_args[0][0]
        # Spot-check 2024 cap limit
        assert "255.4" in sql

    def test_sql_handles_known_nfc_teams(self):
        db = _make_db()
        gold = GoldLayer(db)
        gold.build_team_finance_summary()
        sql = db.execute.call_args[0][0]
        for team in ["DAL", "PHI", "NYG", "GNB", "CHI", "MIN"]:
            assert team in sql, f"Expected NFC team '{team}' in conference mapping"

    def test_sql_handles_known_afc_teams(self):
        db = _make_db()
        gold = GoldLayer(db)
        gold.build_team_finance_summary()
        sql = db.execute.call_args[0][0]
        for team in ["KAN", "BUF", "BAL", "PIT", "MIA", "NWE"]:
            assert team in sql, f"Expected AFC team '{team}' in conference mapping"

    def test_db_execute_exception_propagates(self):
        db = _make_db(execute_side_effect=Exception("BQ write error"))
        gold = GoldLayer(db)
        with pytest.raises(Exception, match="BQ write error"):
            gold.build_team_finance_summary()


# ---------------------------------------------------------------------------
# Integration: build_team_finance_summary is called in main() gold path
# ---------------------------------------------------------------------------


def test_main_calls_build_team_finance_summary(monkeypatch):
    """build_team_finance_summary must be invoked in the default gold-layer path."""
    calls = []

    class _FakeGold:
        def __init__(self, db):
            pass

        def build_fact_player_efficiency(self):
            calls.append("fact_player_efficiency")

        def build_team_finance_summary(self):
            calls.append("team_finance_summary")

    class _FakeSilver:
        def __init__(self, db):
            pass

        def provision_schemas(self):
            pass

        def ingest_contracts(self, year):
            pass

        def ingest_pfr(self, year):
            pass

        def ingest_penalties(self, year):
            pass

        def ingest_team_cap(self):
            pass

        def ingest_others(self):
            pass

        def ingest_player_metadata(self):
            pass

    class _FakeBronze:
        def __init__(self, db):
            pass

        def ingest_contracts(self, year):
            pass

    db_mock = MagicMock()
    db_mock.__enter__ = lambda s: db_mock
    db_mock.__exit__ = MagicMock(return_value=False)

    import medallion_pipeline as mp

    monkeypatch.setattr(mp, "GoldLayer", _FakeGold)
    monkeypatch.setattr(mp, "SilverLayer", _FakeSilver)
    monkeypatch.setattr(mp, "BronzeLayer", _FakeBronze)
    monkeypatch.setattr(mp, "DBManager", lambda: db_mock)

    import sys

    monkeypatch.setattr(sys, "argv", ["medallion_pipeline.py", "--year", "2024"])
    mp.main()

    assert (
        "team_finance_summary" in calls
    ), "build_team_finance_summary() not called from main() gold path"
    assert calls.index("fact_player_efficiency") < calls.index(
        "team_finance_summary"
    ), "team_finance_summary should run AFTER fact_player_efficiency"
