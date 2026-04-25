"""Unit tests for validate_not_null_constraints (SP29-1)."""

import pandas as pd
import pytest

from src.data_validation import validate_not_null_constraints


def _base_contracts_df():
    """Minimal valid silver_spotrac_contracts DataFrame."""
    import pandas as pd
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    return pd.DataFrame(
        [
            {
                "contract_id": "abc123",
                "player_id": "def456",
                "player_name": "Patrick Mahomes",
                "team": "KC",
                "year": 2025,
                "position": "QB",
                "effective_start_date": now,
                "is_current": True,
                "source_name": "spotrac",
                "system_ingest_time": now,
            }
        ]
    )


class TestValidateNotNullConstraints:
    def test_valid_df_passes(self):
        df = _base_contracts_df()
        result = validate_not_null_constraints(df, "silver_spotrac_contracts")
        assert result["is_valid"] is True
        assert result["violations"] == []

    def test_null_player_name_raises(self):
        df = _base_contracts_df()
        df.at[0, "player_name"] = None
        with pytest.raises(ValueError, match="player_name"):
            validate_not_null_constraints(df, "silver_spotrac_contracts")

    def test_null_contract_id_raises(self):
        df = _base_contracts_df()
        df.at[0, "contract_id"] = None
        with pytest.raises(ValueError, match="contract_id"):
            validate_not_null_constraints(df, "silver_spotrac_contracts")

    def test_empty_string_team_raises(self):
        df = _base_contracts_df()
        df.at[0, "team"] = ""
        with pytest.raises(ValueError, match="team"):
            validate_not_null_constraints(df, "silver_spotrac_contracts")

    def test_whitespace_only_position_raises(self):
        df = _base_contracts_df()
        df.at[0, "position"] = "   "
        with pytest.raises(ValueError, match="position"):
            validate_not_null_constraints(df, "silver_spotrac_contracts")

    def test_no_raise_returns_violations(self):
        df = _base_contracts_df()
        df.at[0, "player_name"] = None
        result = validate_not_null_constraints(
            df, "silver_spotrac_contracts", raise_on_violation=False
        )
        assert result["is_valid"] is False
        assert any(v["column"] == "player_name" for v in result["violations"])

    def test_missing_required_column_is_violation(self):
        df = _base_contracts_df()
        df.drop(columns=["contract_id"], inplace=True)
        result = validate_not_null_constraints(
            df, "silver_spotrac_contracts", raise_on_violation=False
        )
        assert result["is_valid"] is False
        missing_violation = next(
            v for v in result["violations"] if v["column"] == "contract_id"
        )
        assert missing_violation["issue"] == "missing_column"

    def test_unknown_table_passes_with_warning(self):
        df = pd.DataFrame([{"foo": "bar"}])
        result = validate_not_null_constraints(df, "unknown_table_xyz")
        assert result["is_valid"] is True

    def test_multiple_null_violations_collected(self):
        df = _base_contracts_df()
        df.at[0, "player_name"] = None
        df.at[0, "team"] = None
        result = validate_not_null_constraints(
            df, "silver_spotrac_contracts", raise_on_violation=False
        )
        violated_cols = [v["column"] for v in result["violations"]]
        assert "player_name" in violated_cols
        assert "team" in violated_cols
