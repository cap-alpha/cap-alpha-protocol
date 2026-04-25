"""
Unit tests for validate_not_null_constraints() — no BigQuery required.
These run in all environments and serve as the first line of defense against
NULL identity values propagating into the Gold layer.
"""

import pandas as pd
import pytest
from src.data_quality_tests import NOT_NULL_CONTRACTS, validate_not_null_constraints


class TestValidateNotNullConstraints:
    def test_valid_dataframe_passes(self):
        df = pd.DataFrame(
            {
                "player_name": ["Patrick Mahomes", "Josh Allen"],
                "team": ["KAN", "BUF"],
                "year": [2024, 2024],
                "position": ["QB", "QB"],
                "cap_hit_millions": [45.0, 43.0],
            }
        )
        validate_not_null_constraints(df, "fact_player_efficiency")  # must not raise

    def test_null_in_identity_column_raises(self):
        df = pd.DataFrame(
            {
                "player_name": ["Patrick Mahomes", None],
                "team": ["KAN", "BUF"],
                "year": [2024, 2024],
                "position": ["QB", "QB"],
                "cap_hit_millions": [45.0, 43.0],
            }
        )
        with pytest.raises(ValueError, match="player_name"):
            validate_not_null_constraints(df, "fact_player_efficiency")

    def test_multiple_null_columns_reported(self):
        df = pd.DataFrame(
            {
                "player_name": [None, "Josh Allen"],
                "team": [None, None],
                "year": [2024, 2024],
                "position": ["QB", "QB"],
                "cap_hit_millions": [45.0, 43.0],
            }
        )
        with pytest.raises(ValueError) as exc_info:
            validate_not_null_constraints(df, "fact_player_efficiency")
        msg = str(exc_info.value)
        assert "player_name" in msg
        assert "team" in msg

    def test_unknown_table_passes_silently(self):
        df = pd.DataFrame({"some_col": [None, None]})
        validate_not_null_constraints(df, "nonexistent_table")  # must not raise

    def test_missing_required_column_raises(self):
        df = pd.DataFrame(
            {
                "player_name": ["Patrick Mahomes"],
                # 'team' is missing entirely
                "year": [2024],
                "position": ["QB"],
                "cap_hit_millions": [45.0],
            }
        )
        with pytest.raises(ValueError, match="team"):
            validate_not_null_constraints(df, "fact_player_efficiency")

    def test_silver_spotrac_contracts_valid(self):
        df = pd.DataFrame(
            {
                "contract_id": ["abc123"],
                "player_name": ["Travis Kelce"],
                "team": ["KAN"],
                "year": [2024],
                "cap_hit_millions": [14.3],
                "system_ingest_time": ["2024-01-01 00:00:00"],
            }
        )
        validate_not_null_constraints(df, "silver_spotrac_contracts")

    def test_silver_spotrac_contracts_null_contract_id_raises(self):
        df = pd.DataFrame(
            {
                "contract_id": [None],
                "player_name": ["Travis Kelce"],
                "team": ["KAN"],
                "year": [2024],
                "cap_hit_millions": [14.3],
                "system_ingest_time": ["2024-01-01 00:00:00"],
            }
        )
        with pytest.raises(ValueError, match="contract_id"):
            validate_not_null_constraints(df, "silver_spotrac_contracts")

    def test_not_null_contracts_covers_all_core_tables(self):
        core_tables = {
            "silver_spotrac_contracts",
            "fact_player_efficiency",
            "silver_team_cap",
            "silver_player_metadata",
            "silver_spotrac_salaries",
            "silver_pfr_draft_history",
        }
        missing = core_tables - set(NOT_NULL_CONTRACTS.keys())
        assert not missing, f"Core tables missing from NOT_NULL_CONTRACTS: {missing}"
