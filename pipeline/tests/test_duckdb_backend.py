"""
Unit + integration tests for the DuckDB local backend.

Unit tests (always run):
  - _translate_bq_sql: backtick stripping, dataset mapping, type translation
  - get_db_manager factory: returns right class based on DB_BACKEND

Integration tests (gated on RUN_INTEGRATION=1):
  - init_local_db.py → DuckDB round-trip (INSERT + SELECT)
"""

import os
import tempfile
import importlib

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _import_translate():
    """Import _translate_bq_sql from src.duckdb_manager."""
    from src.duckdb_manager import _translate_bq_sql

    return _translate_bq_sql


def _import_get_db_manager():
    from src.db_manager import get_db_manager

    return get_db_manager


# ---------------------------------------------------------------------------
# Unit tests: _translate_bq_sql
# ---------------------------------------------------------------------------


class TestTranslateBqSql:
    """Tests for the BigQuery → DuckDB SQL translation helper."""

    def setup_method(self):
        self.translate = _import_translate()

    def test_backtick_project_dataset_table(self):
        """Strips project prefix, keeps dataset.table as double-quoted identifiers."""
        sql = "SELECT * FROM `myproject.nfl_dead_money.raw_pundit_media`"
        result = self.translate(sql)
        # Backtick refs become "schema"."table" double-quoted identifiers
        assert '"nfl_dead_money"."raw_pundit_media"' in result
        assert "`" not in result
        assert "myproject" not in result

    def test_backtick_dataset_table_no_project(self):
        """Handles `dataset.table` without project prefix."""
        sql = "SELECT * FROM `gold_layer.prediction_ledger`"
        result = self.translate(sql)
        assert '"gold_layer"."prediction_ledger"' in result
        assert "`" not in result

    def test_backtick_single_identifier(self):
        """Handles single-part backtick identifiers."""
        sql = "SELECT `pundit_id` FROM tbl"
        result = self.translate(sql)
        # Single-part backtick identifiers are stripped
        assert "pundit_id" in result
        assert "`" not in result

    def test_string_to_varchar(self):
        """STRING type keyword → VARCHAR."""
        sql = "CREATE TABLE t (name STRING)"
        result = self.translate(sql)
        assert "VARCHAR" in result
        assert "STRING" not in result

    def test_int64_to_bigint(self):
        """INT64 → BIGINT."""
        sql = "CREATE TABLE t (count INT64)"
        result = self.translate(sql)
        assert "BIGINT" in result
        assert "INT64" not in result

    def test_float64_to_double(self):
        """FLOAT64 → DOUBLE."""
        sql = "CREATE TABLE t (score FLOAT64)"
        result = self.translate(sql)
        assert "DOUBLE" in result
        assert "FLOAT64" not in result

    def test_bool_to_boolean(self):
        """BOOL → BOOLEAN."""
        sql = "CREATE TABLE t (active BOOL)"
        result = self.translate(sql)
        assert "BOOLEAN" in result
        # BOOL should not appear as a standalone word
        import re

        assert not re.search(r"\bBOOL\b", result)

    def test_array_string_to_varchar_array(self):
        """ARRAY<STRING> → VARCHAR[]."""
        sql = "CREATE TABLE t (tags ARRAY<STRING>)"
        result = self.translate(sql)
        assert "VARCHAR[]" in result

    def test_param_at_to_dollar(self):
        """@param_name → $param_name for DuckDB named params."""
        sql = "SELECT * FROM tbl WHERE pundit_id = @pundit_id"
        result = self.translate(sql)
        assert "$pundit_id" in result
        assert "@pundit_id" not in result

    def test_at_param_word_boundary(self):
        """@param substitution is word-boundary safe."""
        sql = "WHERE a = @ab AND b = @abc"
        result = self.translate(sql)
        assert "$ab " in result or result.endswith("$ab")
        assert "$abc" in result

    def test_safe_cast_to_try_cast(self):
        """SAFE_CAST → TRY_CAST."""
        sql = "SELECT SAFE_CAST(x AS INT64)"
        result = self.translate(sql)
        assert "TRY_CAST" in result
        assert "SAFE_CAST" not in result

    def test_current_timestamp_no_parens(self):
        """CURRENT_TIMESTAMP() → current_timestamp (DuckDB lowercase form)."""
        sql = "INSERT INTO t VALUES (CURRENT_TIMESTAMP())"
        result = self.translate(sql)
        assert "current_timestamp" in result.lower()
        # Should not have trailing ()
        assert "CURRENT_TIMESTAMP()" not in result.upper()

    def test_generate_uuid(self):
        """GENERATE_UUID() → gen_random_uuid()::VARCHAR."""
        sql = "SELECT GENERATE_UUID() AS id"
        result = self.translate(sql)
        assert "gen_random_uuid()" in result
        assert "GENERATE_UUID" not in result

    def test_partition_by_stripped(self):
        """PARTITION BY clause is removed."""
        sql = "CREATE TABLE t (id BIGINT) PARTITION BY DATE(created_at)"
        result = self.translate(sql)
        assert "PARTITION BY" not in result.upper()

    def test_cluster_by_stripped(self):
        """CLUSTER BY clause is removed."""
        sql = "CREATE TABLE t (id BIGINT) CLUSTER BY pundit_id, claim_category"
        result = self.translate(sql)
        assert "CLUSTER BY" not in result.upper()

    def test_options_stripped(self):
        """OPTIONS(...) is stripped."""
        sql = "CREATE TABLE t (id BIGINT) OPTIONS (description='test')"
        result = self.translate(sql)
        assert "OPTIONS" not in result.upper()

    def test_multiple_table_refs(self):
        """Multiple backtick refs in one query all translated."""
        sql = """
            SELECT l.pundit_id
            FROM `proj.gold_layer.prediction_ledger` l
            LEFT JOIN `proj.gold_layer.prediction_resolutions` r
                ON l.prediction_hash = r.prediction_hash
        """
        result = self.translate(sql)
        assert "`" not in result
        assert '"gold_layer"."prediction_ledger"' in result
        assert '"gold_layer"."prediction_resolutions"' in result
        assert "proj" not in result

    def test_idempotent_on_clean_sql(self):
        """Translation is idempotent on already-translated SQL."""
        sql = "SELECT * FROM gold_layer.prediction_ledger WHERE pundit_id = $pid"
        result1 = self.translate(sql)
        result2 = self.translate(result1)
        assert result1 == result2


# ---------------------------------------------------------------------------
# Unit tests: get_db_manager factory
# ---------------------------------------------------------------------------


class TestGetDbManagerFactory:
    """Tests for the DB_BACKEND-driven factory function."""

    def test_default_is_bigquery(self, monkeypatch):
        """Without DB_BACKEND set, factory returns DBManager (BQ)."""
        monkeypatch.delenv("DB_BACKEND", raising=False)
        monkeypatch.delenv("USE_LOCAL_DB", raising=False)

        from src.db_manager import DBManager, get_db_manager

        # We can only test the *class* that would be constructed, not instantiate
        # it (BQ needs real credentials).  Patch _initialize_connection to no-op.
        import unittest.mock as mock

        with mock.patch.object(DBManager, "_initialize_connection", return_value=None):
            # Also prevent __new__ from redirecting to LocalDBManager
            monkeypatch.delenv("USE_LOCAL_DB", raising=False)
            db = get_db_manager()
            # After patching, the returned object should be a DBManager instance
            assert isinstance(db, DBManager)

    def test_duckdb_backend_returns_duckdb_manager(self, monkeypatch, tmp_path):
        """DB_BACKEND=duckdb returns a DuckDBManager."""
        monkeypatch.setenv("DB_BACKEND", "duckdb")
        monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "test.duckdb"))
        monkeypatch.delenv("USE_LOCAL_DB", raising=False)

        from src.db_manager import get_db_manager
        from src.duckdb_manager import DuckDBManager

        db = get_db_manager()
        try:
            assert isinstance(db, DuckDBManager)
        finally:
            db.close()

    def test_bigquery_backend_explicit(self, monkeypatch):
        """DB_BACKEND=bigquery explicitly selects BQ manager."""
        monkeypatch.setenv("DB_BACKEND", "bigquery")
        monkeypatch.delenv("USE_LOCAL_DB", raising=False)

        from src.db_manager import DBManager, get_db_manager

        import unittest.mock as mock

        with mock.patch.object(DBManager, "_initialize_connection", return_value=None):
            db = get_db_manager()
            assert isinstance(db, DBManager)

    def test_backend_env_var_case_insensitive(self, monkeypatch, tmp_path):
        """DB_BACKEND is case-insensitive (DUCKDB, DuckDB → DuckDBManager)."""
        monkeypatch.setenv("DB_BACKEND", "DUCKDB")
        monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "test.duckdb"))
        monkeypatch.delenv("USE_LOCAL_DB", raising=False)

        from src.db_manager import get_db_manager
        from src.duckdb_manager import DuckDBManager

        db = get_db_manager()
        try:
            assert isinstance(db, DuckDBManager)
        finally:
            db.close()


# ---------------------------------------------------------------------------
# Integration tests: full round-trip
# ---------------------------------------------------------------------------

_INTEGRATION = pytest.mark.skipif(
    not os.environ.get("RUN_INTEGRATION"),
    reason="Set RUN_INTEGRATION=1 to run DuckDB integration tests",
)


@_INTEGRATION
class TestDuckDBRoundTrip:
    """Integration: init schema → insert row → fetch it back."""

    @pytest.fixture
    def local_db(self, tmp_path, monkeypatch):
        """Set up an isolated DuckDB file and return a DuckDBManager."""
        db_path = str(tmp_path / "test.duckdb")
        monkeypatch.setenv("DB_BACKEND", "duckdb")
        monkeypatch.setenv("DUCKDB_PATH", db_path)
        monkeypatch.delenv("USE_LOCAL_DB", raising=False)

        # Run the init script to bootstrap the schema
        import subprocess, sys

        result = subprocess.run(
            [sys.executable, "scripts/init_local_db.py"],
            cwd=str(tmp_path.parent),
            env={**os.environ, "DB_BACKEND": "duckdb", "DUCKDB_PATH": db_path},
            capture_output=True,
            text=True,
        )

        from src.duckdb_manager import DuckDBManager

        db = DuckDBManager(db_path=db_path)
        yield db
        db.close()

    def test_select_literal(self, local_db):
        """Basic SELECT 1 works."""
        df = local_db.fetch_df("SELECT 1 AS n")
        assert isinstance(df, pd.DataFrame)
        assert int(df.iloc[0]["n"]) == 1

    def test_insert_and_fetch(self, local_db):
        """Create a temp table, insert a row, read it back."""
        local_db.execute(
            "CREATE TABLE IF NOT EXISTS _test_rt (id BIGINT, name VARCHAR)"
        )
        local_db.execute("INSERT INTO _test_rt VALUES (42, 'hello')")
        df = local_db.fetch_df("SELECT * FROM _test_rt WHERE id = 42")
        assert len(df) == 1
        assert df.iloc[0]["name"] == "hello"

    def test_context_manager(self, tmp_path, monkeypatch):
        """DuckDBManager works as a context manager."""
        db_path = str(tmp_path / "ctx.duckdb")
        monkeypatch.setenv("DUCKDB_PATH", db_path)

        from src.duckdb_manager import DuckDBManager

        with DuckDBManager(db_path=db_path) as db:
            df = db.fetch_df("SELECT 2 AS n")
            assert int(df.iloc[0]["n"]) == 2
        # after __exit__, _conn should be None / closed
        assert db._conn is None

    def test_append_dataframe_to_table(self, local_db):
        """append_dataframe_to_table inserts rows correctly."""
        local_db.execute("CREATE TABLE IF NOT EXISTS _test_append (val BIGINT)")
        df = pd.DataFrame({"val": [1, 2, 3]})
        local_db.append_dataframe_to_table(df, "_test_append")
        result = local_db.fetch_df("SELECT COUNT(*) AS cnt FROM _test_append")
        assert int(result.iloc[0]["cnt"]) == 3

    def test_table_exists(self, local_db):
        """table_exists returns True for existing tables, False for missing."""
        local_db.execute("CREATE TABLE IF NOT EXISTS _test_exists (id BIGINT)")
        assert local_db.table_exists("_test_exists") is True
        assert local_db.table_exists("_nonexistent_table_xyz") is False

    def test_result_proxy(self, local_db):
        """execute() result proxy exposes .fetchall() and .fetchone()."""
        local_db.execute("CREATE TABLE IF NOT EXISTS _test_proxy (n BIGINT)")
        local_db.execute("INSERT INTO _test_proxy VALUES (10), (20)")

        proxy = local_db.execute("SELECT n FROM _test_proxy ORDER BY n")
        rows = proxy.fetchall()
        assert len(rows) == 2
        assert rows[0][0] == 10

        proxy2 = local_db.execute("SELECT n FROM _test_proxy ORDER BY n")
        one = proxy2.fetchone()
        assert one[0] == 10
