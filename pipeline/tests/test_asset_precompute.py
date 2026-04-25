"""Unit tests for AssetPrecomputer (SP24-3, GH-#88)."""

from unittest.mock import MagicMock, call, patch

import pandas as pd
import pytest

from src.asset_precompute import AssetPrecomputer, run_precompute


def _make_db(count=32):
    db = MagicMock()
    db.project_id = "test-project"
    count_df = pd.DataFrame([{"n": count}])
    db.fetch_df.return_value = count_df
    return db


class TestComputeTeamCapSummary:
    def test_executes_create_or_replace_sql(self):
        db = _make_db(32)
        ac = AssetPrecomputer(db=db)
        ac.compute_team_cap_summary()
        sql = db.execute.call_args[0][0]
        assert "CREATE OR REPLACE TABLE" in sql
        assert "team_cap_summary" in sql

    def test_sql_groups_by_team(self):
        db = _make_db(32)
        ac = AssetPrecomputer(db=db)
        ac.compute_team_cap_summary()
        sql = db.execute.call_args[0][0]
        assert "GROUP BY team" in sql

    def test_sql_includes_risk_cap_threshold(self):
        db = _make_db(32)
        ac = AssetPrecomputer(db=db)
        ac.compute_team_cap_summary()
        sql = db.execute.call_args[0][0]
        assert "0.7" in sql  # RISK_CAP_THRESHOLD

    def test_returns_team_count(self):
        db = _make_db(28)
        ac = AssetPrecomputer(db=db)
        result = ac.compute_team_cap_summary()
        assert result == 28

    def test_queries_count_after_write(self):
        db = _make_db(32)
        ac = AssetPrecomputer(db=db)
        ac.compute_team_cap_summary()
        # execute once (CREATE OR REPLACE), then fetch_df once (COUNT)
        assert db.execute.call_count == 1
        assert db.fetch_df.call_count == 1


class TestComputePlayerRiskTiers:
    def test_executes_create_or_replace_sql(self):
        db = _make_db(450)
        ac = AssetPrecomputer(db=db)
        ac.compute_player_risk_tiers()
        sql = db.execute.call_args[0][0]
        assert "CREATE OR REPLACE TABLE" in sql
        assert "player_risk_tiers" in sql

    def test_sql_includes_row_number_dedup(self):
        db = _make_db(450)
        ac = AssetPrecomputer(db=db)
        ac.compute_player_risk_tiers()
        sql = db.execute.call_args[0][0]
        assert "ROW_NUMBER()" in sql
        assert "PARTITION BY player_name" in sql

    def test_sql_includes_risk_tier_case(self):
        db = _make_db(450)
        ac = AssetPrecomputer(db=db)
        ac.compute_player_risk_tiers()
        sql = db.execute.call_args[0][0]
        assert "'SAFE'" in sql
        assert "'HIGH'" in sql
        assert "'MODERATE'" in sql

    def test_returns_player_count(self):
        db = _make_db(873)
        ac = AssetPrecomputer(db=db)
        result = ac.compute_player_risk_tiers()
        assert result == 873


class TestRunAll:
    def test_returns_results_dict_with_both_keys(self):
        db = MagicMock()
        db.fetch_df.return_value = pd.DataFrame([{"n": 32}])
        ac = AssetPrecomputer(db=db)
        results = ac.run_all()
        assert "team_cap_summary" in results
        assert "player_risk_tiers" in results

    def test_raises_if_any_step_fails(self):
        db = MagicMock()
        db.fetch_df.return_value = pd.DataFrame([{"n": 32}])
        db.execute.side_effect = Exception("BQ unavailable")
        ac = AssetPrecomputer(db=db)
        with pytest.raises(RuntimeError, match="Asset pre-computation failed"):
            ac.run_all()

    def test_run_precompute_module_entry_point(self):
        db = MagicMock()
        db.fetch_df.return_value = pd.DataFrame([{"n": 32}])
        results = run_precompute(db=db)
        assert isinstance(results, dict)
        assert "team_cap_summary" in results
