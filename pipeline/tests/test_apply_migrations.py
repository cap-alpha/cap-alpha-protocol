"""
Unit tests for apply_migrations.py — idempotent migration runner.

Tests run without a live BigQuery connection; all BQ calls are mocked.
"""

from __future__ import annotations

import hashlib
import os
import pathlib
import sys
import types
import unittest
from unittest.mock import MagicMock, call, patch

import pytest

# ---------------------------------------------------------------------------
# Make sure the runner module is importable regardless of PYTHONPATH.
# ---------------------------------------------------------------------------
_SCRIPTS_DIR = pathlib.Path(__file__).parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from apply_migrations import (  # noqa: E402
    _creates_table,
    _discover_migrations,
    _parse_backfill_declaration,
    _sha256,
    _split_statements,
    apply_migrations,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sha(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Unit tests — no BigQuery needed
# ---------------------------------------------------------------------------


class TestSplitStatements:
    def test_splits_on_semicolons(self):
        sql = "SELECT 1; SELECT 2; SELECT 3"
        parts = _split_statements(sql)
        assert len(parts) == 3

    def test_strips_comment_lines(self):
        sql = "-- comment\nSELECT 1; -- inline\nSELECT 2"
        parts = _split_statements(sql)
        assert len(parts) == 2

    def test_ignores_empty_trailing_segments(self):
        sql = "SELECT 1;"
        parts = _split_statements(sql)
        assert len(parts) == 1
        assert parts[0] == "SELECT 1"

    def test_semicolons_inside_string_literals_not_split(self):
        # BigQuery OPTIONS(description="...") clauses frequently contain semicolons
        sql = (
            'CREATE TABLE t (a STRING OPTIONS(description="x; y"), '
            'b BOOL OPTIONS(description="p; q"));'
        )
        parts = _split_statements(sql)
        assert len(parts) == 1, f"Expected 1 statement, got {len(parts)}: {parts}"

    def test_semicolons_inside_double_quotes_not_split(self):
        sql = 'INSERT INTO t VALUES ("a;b;c");'
        parts = _split_statements(sql)
        assert len(parts) == 1

    def test_real_statement_boundary_after_quoted_semicolons(self):
        sql = 'ALTER TABLE t ADD COLUMN a STRING OPTIONS(description="x; y"); ALTER TABLE t ADD COLUMN b INT64;'
        parts = _split_statements(sql)
        assert len(parts) == 2


class TestSha256:
    def test_deterministic(self):
        assert _sha256("hello") == _sha256("hello")

    def test_different_inputs(self):
        assert _sha256("hello") != _sha256("world")


class TestParseBackfillDeclaration:
    def test_returns_value_when_present(self):
        sql = "-- backfill: issue #874\nCREATE TABLE foo (id INT64)"
        assert _parse_backfill_declaration(sql) == "issue #874"

    def test_returns_none_when_absent(self):
        sql = "CREATE TABLE foo (id INT64)"
        assert _parse_backfill_declaration(sql) is None

    def test_case_insensitive_prefix(self):
        sql = "-- BACKFILL: none\nCREATE TABLE foo (id INT64)"
        assert _parse_backfill_declaration(sql) == "none"

    def test_strips_whitespace_from_value(self):
        sql = "--   backfill :   not needed  \nCREATE TABLE foo (id INT64)"
        assert _parse_backfill_declaration(sql) == "not needed"

    def test_only_scans_first_10_lines(self):
        # backfill header on line 11 — should not be detected
        lines = ["-- some comment"] * 10 + ["-- backfill: issue #999"]
        sql = "\n".join(lines)
        assert _parse_backfill_declaration(sql) is None

    def test_detects_header_on_line_10(self):
        lines = ["-- some comment"] * 9 + ["-- backfill: issue #999"]
        sql = "\n".join(lines)
        assert _parse_backfill_declaration(sql) == "issue #999"


class TestCreatesTable:
    def test_detects_create_table(self):
        assert _creates_table("CREATE TABLE foo (id INT64)")

    def test_detects_create_or_replace_table(self):
        assert _creates_table("CREATE OR REPLACE TABLE foo (id INT64)")

    def test_case_insensitive(self):
        assert _creates_table("create table foo (id INT64)")

    def test_returns_false_for_alter(self):
        assert not _creates_table("ALTER TABLE foo ADD COLUMN bar STRING")

    def test_returns_false_for_insert(self):
        assert not _creates_table("INSERT INTO foo VALUES (1)")

    def test_returns_false_for_select(self):
        assert not _creates_table("SELECT 1")

    def test_detects_create_table_if_not_exists(self):
        assert _creates_table("CREATE TABLE IF NOT EXISTS foo (id INT64)")


class TestDiscoverMigrations:
    def test_returns_sorted_list(self, tmp_path, monkeypatch):
        # Patch MIGRATIONS_DIR to a temp directory
        monkeypatch.setattr("apply_migrations.MIGRATIONS_DIR", tmp_path)
        (tmp_path / "002_b.sql").write_text("SELECT 2")
        (tmp_path / "001_a.sql").write_text("SELECT 1")
        (tmp_path / "README.md").write_text("ignore me")
        result = _discover_migrations()
        assert [f.name for f in result] == ["001_a.sql", "002_b.sql"]

    def test_ignores_non_numeric_prefix(self, tmp_path, monkeypatch):
        monkeypatch.setattr("apply_migrations.MIGRATIONS_DIR", tmp_path)
        (tmp_path / "001_good.sql").write_text("SELECT 1")
        (tmp_path / "no_prefix.sql").write_text("SELECT 2")
        result = _discover_migrations()
        assert len(result) == 1
        assert result[0].name == "001_good.sql"


# ---------------------------------------------------------------------------
# Integration-style unit tests with mocked BigQuery
# ---------------------------------------------------------------------------


def _make_bq_mock(applied_rows: list[dict] | None = None):
    """Return a mock BigQuery client."""
    client = MagicMock()

    # query().result() returns rows when fetching applied migrations
    rows = applied_rows or []
    fetch_result = MagicMock()
    fetch_result.__iter__ = MagicMock(return_value=iter(rows))

    job = MagicMock()
    job.result.return_value = fetch_result
    job.job_id = "mock-job-id"

    client.query.return_value = job
    return client


class TestApplyMigrationsBootstrap:
    """Test 1: fresh DB bootstraps and applies all migrations."""

    def test_fresh_db_applies_all_migrations(self, tmp_path, monkeypatch):
        """
        When infra.applied_migrations is empty, every discovered migration
        should be applied and a tracking row inserted for each.
        """
        # Create two fake migration files
        monkeypatch.setattr("apply_migrations.MIGRATIONS_DIR", tmp_path)
        (tmp_path / "001_init.sql").write_text("CREATE TABLE foo (id INT64)")
        (tmp_path / "002_add_col.sql").write_text(
            "ALTER TABLE foo ADD COLUMN bar STRING"
        )

        os.environ["GCP_PROJECT_ID"] = "test-project"
        os.environ.pop("GITHUB_SHA", None)  # ensure 'local' fallback

        mock_client = MagicMock()

        # _load_applied returns empty dict → no rows
        empty_result = MagicMock()
        empty_result.__iter__ = MagicMock(return_value=iter([]))

        exec_result = MagicMock()
        exec_result.__iter__ = MagicMock(return_value=iter([]))

        exec_job = MagicMock()
        exec_job.result.return_value = exec_result
        exec_job.job_id = "job-123"

        mock_client.query.return_value = exec_job
        mock_client.create_dataset = MagicMock()

        with patch("apply_migrations.bigquery") as mock_bq_module:
            mock_bq_module.Client.return_value = mock_client
            mock_bq_module.Dataset = MagicMock()
            apply_migrations(dry_run=False, mark_applied=False)

        # Verify query was called at least for: CREATE TABLE (bootstrap),
        # SELECT (load applied), and 2 migration + 2 INSERT statements.
        assert mock_client.query.call_count >= 6

        # Confirm INSERT tracking calls include both migration IDs
        all_queries = [str(c) for c in mock_client.query.call_args_list]
        insert_calls = [
            q for q in all_queries if "INSERT INTO" in q and "applied_migrations" in q
        ]
        assert len(insert_calls) == 2, (
            f"Expected 2 INSERT tracking calls, got {len(insert_calls)}: {insert_calls}"
        )


class TestApplyMigrationsSkipsApplied:
    """Test 2: already-applied migration with matching SHA is skipped."""

    def test_already_applied_migration_is_skipped(self, tmp_path, monkeypatch):
        """
        When a migration appears in applied_migrations with matching SHA,
        it must be skipped without executing its SQL.
        """
        monkeypatch.setattr("apply_migrations.MIGRATIONS_DIR", tmp_path)

        content = "CREATE TABLE bar (id INT64)"
        migration_file = tmp_path / "001_init.sql"
        migration_file.write_text(content)
        sha = _sha(content)

        os.environ["GCP_PROJECT_ID"] = "test-project"

        # Simulate already-applied row returned from BQ
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda self, key: {
            "migration_id": "001_init.sql",
            "sha256": sha,
        }[key]

        applied_result = MagicMock()
        applied_result.__iter__ = MagicMock(return_value=iter([mock_row]))

        generic_result = MagicMock()
        generic_result.__iter__ = MagicMock(return_value=iter([]))

        mock_client = MagicMock()

        def query_side_effect(sql, *args, **kwargs):
            job = MagicMock()
            job.job_id = "job-x"
            if "SELECT migration_id" in sql:
                job.result.return_value = applied_result
            else:
                job.result.return_value = generic_result
            return job

        mock_client.query.side_effect = query_side_effect
        mock_client.create_dataset = MagicMock()

        with patch("apply_migrations.bigquery") as mock_bq_module:
            mock_bq_module.Client.return_value = mock_client
            mock_bq_module.Dataset = MagicMock()
            apply_migrations(dry_run=False, mark_applied=False)

        # No INSERT into applied_migrations should have been made
        all_sql = [str(c) for c in mock_client.query.call_args_list]
        insert_calls = [
            q for q in all_sql if "INSERT INTO" in q and "applied_migrations" in q
        ]
        assert len(insert_calls) == 0, (
            f"Expected 0 INSERT tracking calls for already-applied migration, "
            f"got {len(insert_calls)}"
        )


class TestApplyMigrationsChangedShaExits:
    """SHA mismatch on existing migration must exit non-zero."""

    def test_changed_sha_raises_system_exit(self, tmp_path, monkeypatch):
        monkeypatch.setattr("apply_migrations.MIGRATIONS_DIR", tmp_path)

        content = "CREATE TABLE baz (id INT64)"
        migration_file = tmp_path / "001_init.sql"
        migration_file.write_text(content)
        wrong_sha = "deadbeef" * 8  # 64 chars of wrong SHA

        mock_row = MagicMock()
        mock_row.__getitem__ = lambda self, key: {
            "migration_id": "001_init.sql",
            "sha256": wrong_sha,
        }[key]

        applied_result = MagicMock()
        applied_result.__iter__ = MagicMock(return_value=iter([mock_row]))

        generic_result = MagicMock()
        generic_result.__iter__ = MagicMock(return_value=iter([]))

        mock_client = MagicMock()

        def query_side_effect(sql, *args, **kwargs):
            job = MagicMock()
            job.job_id = "job-x"
            if "SELECT migration_id" in sql:
                job.result.return_value = applied_result
            else:
                job.result.return_value = generic_result
            return job

        mock_client.query.side_effect = query_side_effect
        mock_client.create_dataset = MagicMock()

        os.environ["GCP_PROJECT_ID"] = "test-project"

        with patch("apply_migrations.bigquery") as mock_bq_module:
            mock_bq_module.Client.return_value = mock_client
            mock_bq_module.Dataset = MagicMock()
            with pytest.raises(SystemExit) as exc_info:
                apply_migrations(dry_run=False, mark_applied=False)

        assert exc_info.value.code != 0


class TestDryRun:
    """--dry-run must not connect to BQ at all."""

    def test_dry_run_does_not_call_bigquery(self, tmp_path, monkeypatch):
        monkeypatch.setattr("apply_migrations.MIGRATIONS_DIR", tmp_path)
        (tmp_path / "001_init.sql").write_text("SELECT 1")

        os.environ["GCP_PROJECT_ID"] = "test-project"

        with patch("apply_migrations.bigquery") as mock_bq_module:
            apply_migrations(dry_run=True)
            mock_bq_module.Client.assert_not_called()

    def test_dry_run_shows_backfill_declared(self, tmp_path, monkeypatch, caplog):
        monkeypatch.setattr("apply_migrations.MIGRATIONS_DIR", tmp_path)
        (tmp_path / "001_create.sql").write_text(
            "-- backfill: issue #874\nCREATE TABLE foo (id INT64)"
        )

        os.environ["GCP_PROJECT_ID"] = "test-project"

        import logging

        with patch("apply_migrations.bigquery"):
            with caplog.at_level(logging.INFO, logger="apply_migrations"):
                apply_migrations(dry_run=True)

        assert any("[backfill: issue #874]" in r.message for r in caplog.records)

    def test_dry_run_shows_backfill_undeclared(self, tmp_path, monkeypatch, caplog):
        monkeypatch.setattr("apply_migrations.MIGRATIONS_DIR", tmp_path)
        (tmp_path / "001_create.sql").write_text("CREATE TABLE foo (id INT64)")

        os.environ["GCP_PROJECT_ID"] = "test-project"

        import logging

        with patch("apply_migrations.bigquery"):
            with caplog.at_level(logging.INFO, logger="apply_migrations"):
                apply_migrations(dry_run=True)

        assert any("[BACKFILL UNDECLARED]" in r.message for r in caplog.records)

    def test_dry_run_no_backfill_marker_for_non_create(
        self, tmp_path, monkeypatch, caplog
    ):
        monkeypatch.setattr("apply_migrations.MIGRATIONS_DIR", tmp_path)
        (tmp_path / "001_alter.sql").write_text("ALTER TABLE foo ADD COLUMN bar STRING")

        os.environ["GCP_PROJECT_ID"] = "test-project"

        import logging

        with patch("apply_migrations.bigquery"):
            with caplog.at_level(logging.INFO, logger="apply_migrations"):
                apply_migrations(dry_run=True)

        assert not any("[BACKFILL" in r.message for r in caplog.records)


class TestBackfillWarning:
    """After applying a migration, warn if CREATE TABLE has no backfill header."""

    def _make_client_mock(self, tmp_path):
        """Return a mock BQ client that simulates empty applied_migrations."""
        mock_client = MagicMock()
        empty_result = MagicMock()
        empty_result.__iter__ = MagicMock(return_value=iter([]))
        exec_job = MagicMock()
        exec_job.result.return_value = empty_result
        exec_job.job_id = "job-123"
        mock_client.query.return_value = exec_job
        mock_client.create_dataset = MagicMock()
        return mock_client

    def test_warns_when_create_table_lacks_backfill_header(
        self, tmp_path, monkeypatch, caplog
    ):
        monkeypatch.setattr("apply_migrations.MIGRATIONS_DIR", tmp_path)
        (tmp_path / "001_create.sql").write_text("CREATE TABLE foo (id INT64)")
        os.environ["GCP_PROJECT_ID"] = "test-project"

        import logging

        mock_client = self._make_client_mock(tmp_path)
        with patch("apply_migrations.bigquery") as mock_bq_module:
            mock_bq_module.Client.return_value = mock_client
            mock_bq_module.Dataset = MagicMock()
            with caplog.at_level(logging.WARNING, logger="apply_migrations"):
                apply_migrations(dry_run=False, mark_applied=False)

        assert any("BACKFILL UNDECLARED" in r.message for r in caplog.records)

    def test_no_warning_when_create_table_has_backfill_header(
        self, tmp_path, monkeypatch, caplog
    ):
        monkeypatch.setattr("apply_migrations.MIGRATIONS_DIR", tmp_path)
        (tmp_path / "001_create.sql").write_text(
            "-- backfill: none\nCREATE TABLE foo (id INT64)"
        )
        os.environ["GCP_PROJECT_ID"] = "test-project"

        import logging

        mock_client = self._make_client_mock(tmp_path)
        with patch("apply_migrations.bigquery") as mock_bq_module:
            mock_bq_module.Client.return_value = mock_client
            mock_bq_module.Dataset = MagicMock()
            with caplog.at_level(logging.WARNING, logger="apply_migrations"):
                apply_migrations(dry_run=False, mark_applied=False)

        assert not any("BACKFILL UNDECLARED" in r.message for r in caplog.records)

    def test_no_warning_for_non_create_migration(self, tmp_path, monkeypatch, caplog):
        monkeypatch.setattr("apply_migrations.MIGRATIONS_DIR", tmp_path)
        (tmp_path / "001_alter.sql").write_text("ALTER TABLE foo ADD COLUMN bar STRING")
        os.environ["GCP_PROJECT_ID"] = "test-project"

        import logging

        mock_client = self._make_client_mock(tmp_path)
        with patch("apply_migrations.bigquery") as mock_bq_module:
            mock_bq_module.Client.return_value = mock_client
            mock_bq_module.Dataset = MagicMock()
            with caplog.at_level(logging.WARNING, logger="apply_migrations"):
                apply_migrations(dry_run=False, mark_applied=False)

        assert not any("BACKFILL UNDECLARED" in r.message for r in caplog.records)
