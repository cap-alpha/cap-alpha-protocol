"""
Tests for the BigQuery-backed FeatureStore (Issue #125).

Unit tests mock DBManager to verify SQL generation and logic flow
without requiring a live BigQuery connection.
"""

from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.feature_store import FeatureStore, _bq_int, _bq_str

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db():
    """Create a mock DBManager for unit testing."""
    db = MagicMock()
    # Default: execute returns a result proxy with fetchone returning (0,)
    result_proxy = MagicMock()
    result_proxy.fetchone.return_value = (0,)
    result_proxy.fetchall.return_value = []
    result_proxy.df.return_value = pd.DataFrame()
    db.execute.return_value = result_proxy
    db.fetch_df.return_value = pd.DataFrame()
    return db


@pytest.fixture
def store(mock_db):
    """Create a FeatureStore backed by a mock DBManager."""
    return FeatureStore(db=mock_db, read_only=False)


@pytest.fixture
def ro_store(mock_db):
    """Create a read-only FeatureStore."""
    return FeatureStore(db=mock_db, read_only=True)


# ---------------------------------------------------------------------------
# Schema initialization
# ---------------------------------------------------------------------------


class TestInitializeSchema:
    def test_creates_feature_registry_and_values(self, store, mock_db):
        store.initialize_schema()
        calls = [str(c) for c in mock_db.execute.call_args_list]
        sql_concat = " ".join(calls)
        assert "feature_registry" in sql_concat
        assert "feature_values" in sql_concat

    def test_uses_bq_types(self, store, mock_db):
        """Schema DDL should use BigQuery types (STRING, INT64, FLOAT64)."""
        store.initialize_schema()
        calls = [str(c) for c in mock_db.execute.call_args_list]
        sql_concat = " ".join(calls)
        assert "STRING" in sql_concat
        assert "INT64" in sql_concat
        assert "FLOAT64" in sql_concat
        # Should NOT contain DuckDB types
        assert "VARCHAR" not in sql_concat
        assert "DOUBLE" not in sql_concat

    def test_read_only_skips_schema(self, ro_store, mock_db):
        ro_store.initialize_schema()
        mock_db.execute.assert_not_called()


# ---------------------------------------------------------------------------
# Feature registration
# ---------------------------------------------------------------------------


class TestRegisterFeature:
    def test_register_uses_merge(self, store, mock_db):
        store.register_feature(
            feature_name="test_feat",
            feature_type="lag",
            source_column="total_tds",
            lag_periods=1,
            description="test",
        )
        sql = mock_db.execute.call_args[0][0]
        assert "MERGE INTO feature_registry" in sql
        assert "test_feat" in sql

    def test_register_handles_none_values(self, store, mock_db):
        store.register_feature(
            feature_name="bare_feat",
            feature_type="raw",
        )
        sql = mock_db.execute.call_args[0][0]
        assert "CAST(NULL AS STRING)" in sql
        assert "CAST(NULL AS INT64)" in sql


# ---------------------------------------------------------------------------
# Lag feature materialization
# ---------------------------------------------------------------------------


class TestMaterializeLagFeatures:
    def test_queries_information_schema(self, store, mock_db):
        """Should check available columns via INFORMATION_SCHEMA."""
        mock_db.fetch_df.return_value = pd.DataFrame(
            {"column_name": ["total_pass_yds", "total_tds", "age"]}
        )
        store.materialize_lag_features()
        info_call = mock_db.fetch_df.call_args_list[0]
        assert "INFORMATION_SCHEMA.COLUMNS" in info_call[0][0]

    def test_deletes_existing_lag_features(self, store, mock_db):
        mock_db.fetch_df.return_value = pd.DataFrame(
            {"column_name": ["total_pass_yds"]}
        )
        store.materialize_lag_features()
        # One of the execute calls should be the DELETE
        sqls = [c[0][0] for c in mock_db.execute.call_args_list]
        delete_sqls = [s for s in sqls if "DELETE FROM feature_values" in s]
        assert len(delete_sqls) == 1
        assert "LIKE '%_lag_%'" in delete_sqls[0]

    def test_materializes_three_lags_per_column(self, store, mock_db):
        """Each available column should produce lag_1, lag_2, lag_3."""
        mock_db.fetch_df.return_value = pd.DataFrame({"column_name": ["total_tds"]})
        store.materialize_lag_features()
        sqls = [c[0][0] for c in mock_db.execute.call_args_list]
        insert_sqls = [s for s in sqls if "INSERT INTO feature_values" in s]
        # 3 lags for 1 column
        assert len(insert_sqls) == 3

    def test_uses_date_function_not_make_date(self, store, mock_db):
        """BigQuery uses DATE() not make_date()."""
        mock_db.fetch_df.return_value = pd.DataFrame({"column_name": ["age"]})
        store.materialize_lag_features()
        sqls = [c[0][0] for c in mock_db.execute.call_args_list]
        insert_sqls = [s for s in sqls if "INSERT INTO feature_values" in s]
        for sql in insert_sqls:
            assert "DATE(source.year" in sql
            assert "make_date" not in sql

    def test_skips_missing_columns(self, store, mock_db):
        """Columns not in source table should be skipped."""
        mock_db.fetch_df.return_value = pd.DataFrame(
            {"column_name": ["some_other_col"]}
        )
        store.materialize_lag_features()
        sqls = [c[0][0] for c in mock_db.execute.call_args_list]
        insert_sqls = [s for s in sqls if "INSERT INTO feature_values" in s]
        assert len(insert_sqls) == 0


# ---------------------------------------------------------------------------
# Interaction feature materialization
# ---------------------------------------------------------------------------


class TestMaterializeInteractionFeatures:
    def test_inserts_interaction_features(self, store, mock_db):
        store.materialize_interaction_features()
        sqls = [c[0][0] for c in mock_db.execute.call_args_list]
        insert_sqls = [s for s in sqls if "INSERT INTO feature_values" in s]
        # 2 interaction features (age_cap_interaction, experience_risk)
        assert len(insert_sqls) == 2

    def test_uses_bq_date_function(self, store, mock_db):
        store.materialize_interaction_features()
        sqls = [c[0][0] for c in mock_db.execute.call_args_list]
        insert_sqls = [s for s in sqls if "INSERT INTO feature_values" in s]
        for sql in insert_sqls:
            assert "DATE(year, 3, 15)" in sql
            assert "make_date" not in sql


# ---------------------------------------------------------------------------
# Training matrix retrieval
# ---------------------------------------------------------------------------


class TestGetTrainingMatrix:
    def test_point_in_time_filter(self, store, mock_db):
        """Query should enforce valid_from <= as_of AND valid_until > as_of."""
        mock_db.fetch_df.return_value = pd.DataFrame()
        store.get_training_matrix(as_of_date=date(2024, 9, 1))
        sql = mock_db.fetch_df.call_args[0][0]
        assert "valid_from <= '2024-09-01'" in sql
        assert "valid_until > '2024-09-01'" in sql
        assert "valid_until IS NULL" in sql

    def test_empty_result_returns_empty_df(self, store, mock_db):
        mock_db.fetch_df.return_value = pd.DataFrame()
        result = store.get_training_matrix(as_of_date=date(2024, 9, 1))
        assert result.empty

    def test_pivots_to_wide_format(self, store, mock_db):
        """Non-empty results should be pivoted to wide format."""
        mock_db.fetch_df.return_value = pd.DataFrame(
            {
                "player_name": ["QB1", "QB1"],
                "year": [2023, 2023],
                "feature_name": ["feat_a", "feat_b"],
                "feature_value": [1.0, 2.0],
            }
        )
        result = store.get_training_matrix(as_of_date=date(2024, 9, 1))
        assert "feat_a" in result.columns
        assert "feat_b" in result.columns
        assert len(result) == 1  # One player-year after pivot


# ---------------------------------------------------------------------------
# Historical features (diagonal join)
# ---------------------------------------------------------------------------


class TestGetHistoricalFeatures:
    def test_diagonal_join_uses_dynamic_date(self, store, mock_db):
        """Diagonal join should use DATE(prediction_year, 9, 1)."""
        mock_db.fetch_df.return_value = pd.DataFrame()
        store.get_historical_features(min_year=2020, max_year=2024)
        sql = mock_db.fetch_df.call_args[0][0]
        assert "DATE(fv.prediction_year, 9, 1)" in sql

    def test_empty_result(self, store, mock_db):
        mock_db.fetch_df.return_value = pd.DataFrame()
        result = store.get_historical_features()
        assert result.empty


# ---------------------------------------------------------------------------
# Temporal integrity validation
# ---------------------------------------------------------------------------


class TestValidateTemporalIntegrity:
    def test_passes_when_zero_violations(self, store, mock_db):
        result_proxy = MagicMock()
        result_proxy.fetchone.return_value = (0,)
        mock_db.execute.return_value = result_proxy

        assert store.validate_temporal_integrity() is True

    def test_fails_when_violations_exist(self, store, mock_db):
        result_proxy = MagicMock()
        result_proxy.fetchone.return_value = (5,)
        mock_db.execute.return_value = result_proxy
        mock_db.fetch_df.return_value = pd.DataFrame(
            {
                "player_name": ["Leaky"],
                "prediction_year": [2023],
                "feature_name": ["bad_feat"],
                "valid_from": [date(2023, 12, 1)],
            }
        )

        assert store.validate_temporal_integrity() is False


# ---------------------------------------------------------------------------
# Feature stats
# ---------------------------------------------------------------------------


class TestGetFeatureStats:
    def test_returns_dataframe(self, store, mock_db):
        mock_db.fetch_df.return_value = pd.DataFrame(
            {
                "feature_type": ["lag"],
                "num_features": [24],
                "num_values": [5000],
                "min_year": [2015],
                "max_year": [2024],
            }
        )
        stats = store.get_feature_stats()
        assert not stats.empty
        assert "feature_type" in stats.columns


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_bq_str_none(self):
        assert _bq_str(None) == "CAST(NULL AS STRING)"

    def test_bq_str_value(self):
        assert _bq_str("hello") == "'hello'"

    def test_bq_str_escapes_quotes(self):
        assert _bq_str("it's") == "'it\\'s'"

    def test_bq_int_none(self):
        assert _bq_int(None) == "CAST(NULL AS INT64)"

    def test_bq_int_value(self):
        assert _bq_int(3) == "3"


# ---------------------------------------------------------------------------
# Constructor
# ---------------------------------------------------------------------------


class TestConstructor:
    @patch("src.feature_store.DBManager")
    def test_creates_default_db_when_none_provided(self, mock_dbm_cls):
        """When no db is passed, FeatureStore should create its own DBManager."""
        store = FeatureStore()
        mock_dbm_cls.assert_called_once()

    def test_uses_provided_db(self, mock_db):
        store = FeatureStore(db=mock_db)
        assert store.db is mock_db
