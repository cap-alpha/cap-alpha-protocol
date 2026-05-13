"""
Unit tests for apply_kg_schema.py — Phase 1 KG schema apply + check (issue #920).

All BigQuery calls are mocked — no live BQ connection required.
Tests cover:
- Dry-run check lists all expected tables and columns without BQ
- _check_schema PASS when all tables+columns exist
- _check_schema FAIL when a table is missing
- _check_schema FAIL when a required column is missing from a table
- _check_schema FAIL when an ADD COLUMN target is missing from its base table
- _check_schema FAIL when an ADD COLUMN is missing from an existing table
- main() --check exits 0 on full pass
- main() --check exits 1 on partial failure
- main() --apply delegates to apply_migrations
- main() --check --dry-run prints expected info without BQ
"""

from __future__ import annotations

import os
import pathlib
import sys
import types
from unittest.mock import MagicMock, patch, call

import pytest

# ---------------------------------------------------------------------------
# Make scripts importable
# ---------------------------------------------------------------------------
_SCRIPTS_DIR = pathlib.Path(__file__).parent.parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_bq_client(columns_by_table: dict[str, list[str]] | None = None) -> MagicMock:
    """
    Build a mock bigquery.Client.

    columns_by_table: {"dataset.table": ["col1", "col2", ...]}
      — returns those column names when INFORMATION_SCHEMA.COLUMNS is queried
        for that table.  Missing keys return empty results (table not found).
    """
    columns_by_table = columns_by_table or {}
    client = MagicMock()

    def _make_job(rows):
        job = MagicMock()
        job.result.return_value = iter(rows)
        job.job_id = "mock-job-id"
        return job

    def _make_row(col_name: str) -> MagicMock:
        row = MagicMock()
        row.__getitem__ = lambda self, key: col_name if key == "column_name" else None
        return row

    def query_side_effect(sql, *args, **kwargs):
        # Parse "WHERE table_name = '<table>'" and dataset from the FROM clause
        import re

        ds_match = re.search(r"`[^`]+\.([^.`]+)\.INFORMATION_SCHEMA\.COLUMNS`", sql)
        tbl_match = re.search(r"table_name\s*=\s*'([^']+)'", sql)
        if ds_match and tbl_match:
            dataset = ds_match.group(1)
            table = tbl_match.group(1)
            key = f"{dataset}.{table}"
            cols = columns_by_table.get(key, [])
            rows = [_make_row(c) for c in cols]
            return _make_job(rows)
        return _make_job([])

    client.query.side_effect = query_side_effect
    return client


# ---------------------------------------------------------------------------
# Import the module under test
# ---------------------------------------------------------------------------


def _import_module():
    """Re-import apply_kg_schema with fresh state, mocking google.cloud.bigquery."""
    # Ensure the google.cloud stub is in place before the module tries to import it.
    if "apply_kg_schema" in sys.modules:
        del sys.modules["apply_kg_schema"]

    google_stub = types.ModuleType("google")
    google_cloud_stub = types.ModuleType("google.cloud")
    bq_stub = types.ModuleType("google.cloud.bigquery")
    bq_stub.Client = MagicMock
    google_stub.cloud = google_cloud_stub
    google_cloud_stub.bigquery = bq_stub

    api_core_stub = types.ModuleType("google.api_core")
    exceptions_stub = types.ModuleType("google.api_core.exceptions")
    exceptions_stub.NotFound = Exception
    api_core_stub.exceptions = exceptions_stub
    google_stub.api_core = api_core_stub

    with patch.dict(
        sys.modules,
        {
            "google": google_stub,
            "google.cloud": google_cloud_stub,
            "google.cloud.bigquery": bq_stub,
            "google.api_core": api_core_stub,
            "google.api_core.exceptions": exceptions_stub,
        },
    ):
        import importlib

        mod = importlib.import_module("apply_kg_schema")
        return mod


# ---------------------------------------------------------------------------
# Tests: _dry_run_check
# ---------------------------------------------------------------------------


class TestDryRunCheck:
    def test_logs_all_expected_tables(self, caplog):
        import logging

        mod = _import_module()
        with caplog.at_level(logging.INFO, logger="apply_kg_schema"):
            mod._dry_run_check()

        messages = "\n".join(caplog.messages)
        assert "claim_entity_link" in messages
        assert "claim_state_history" in messages
        assert "entity_resolution_queue" in messages

    def test_logs_all_add_columns(self, caplog):
        import logging

        mod = _import_module()
        with caplog.at_level(logging.INFO, logger="apply_kg_schema"):
            mod._dry_run_check()

        messages = "\n".join(caplog.messages)
        assert "value_entity_id" in messages
        assert "legacy_prediction_hash" in messages
        assert "legacy_chain_hash" in messages


# ---------------------------------------------------------------------------
# Tests: _query_columns
# ---------------------------------------------------------------------------


class TestQueryColumns:
    def test_returns_column_set(self):
        mod = _import_module()
        client = _make_bq_client(
            {"silver_v2_claims.claim_entity_link": ["link_id", "claim_id"]}
        )
        cols = mod._query_columns(
            client, "proj", "silver_v2_claims", "claim_entity_link"
        )
        assert cols == {"link_id", "claim_id"}

    def test_returns_empty_on_not_found(self):
        mod = _import_module()
        # "not found" error from BQ
        client = MagicMock()
        client.query.side_effect = Exception("Table not found: bogus")
        cols = mod._query_columns(client, "proj", "bogus", "nonexistent")
        assert cols == set()

    def test_propagates_non_404_error(self):
        mod = _import_module()
        client = MagicMock()
        client.query.side_effect = Exception("network timeout")
        with pytest.raises(Exception, match="network timeout"):
            mod._query_columns(client, "proj", "silver_v2_claims", "claim_entity_link")


# ---------------------------------------------------------------------------
# Tests: _check_schema — full pass
# ---------------------------------------------------------------------------


def _all_columns_present() -> dict[str, list[str]]:
    """Return a columns_by_table dict that satisfies all 028 expectations."""
    return {
        "silver_v2_claims.claim_entity_link": [
            "link_id",
            "claim_id",
            "entity_id",
            "entity_role",
            "ordinal",
            "created_at",
        ],
        "silver_v2_claims.claim_state_history": [
            "history_id",
            "claim_id",
            "state",
            "effective_from",
            "effective_to",
            "effective_source",
            "resolution_id",
            "brier_score",
            "binary_correct",
            "notes",
            "created_at",
        ],
        "silver_v2_claims.entity_resolution_queue": [
            "queue_id",
            "raw_entity_string",
            "normalized_string",
            "domain",
            "placeholder_entity_id",
            "first_seen_at",
            "last_attempted_at",
            "attempt_count",
            "status",
            "resolved_entity_id",
            "resolved_by",
            "resolved_at",
            "notes",
            "created_at",
        ],
        # ADD COLUMN targets
        "silver_v2_core.entity_attribute_event": [
            "event_id",
            "entity_id",
            "value_entity_id",
        ],
        "silver_v2_claims.claim": [
            "claim_id",
            "legacy_prediction_hash",
            "legacy_chain_hash",
        ],
    }


class TestCheckSchemaPass:
    def test_all_present_returns_true(self):
        mod = _import_module()
        client = _make_bq_client(_all_columns_present())
        result = mod._check_schema(client, "test-proj")
        assert result is True

    def test_pass_logs_pass_for_each_table(self, caplog):
        import logging

        mod = _import_module()
        client = _make_bq_client(_all_columns_present())
        with caplog.at_level(logging.INFO, logger="apply_kg_schema"):
            mod._check_schema(client, "test-proj")
        messages = "\n".join(caplog.messages)
        assert "PASS" in messages
        assert "FAIL" not in messages


# ---------------------------------------------------------------------------
# Tests: _check_schema — failures
# ---------------------------------------------------------------------------


class TestCheckSchemaFail:
    def test_missing_table_returns_false(self):
        mod = _import_module()
        cols = _all_columns_present()
        del cols["silver_v2_claims.claim_entity_link"]
        client = _make_bq_client(cols)
        result = mod._check_schema(client, "test-proj")
        assert result is False

    def test_missing_required_column_returns_false(self):
        mod = _import_module()
        cols = _all_columns_present()
        # Remove 'entity_role' from claim_entity_link
        cols["silver_v2_claims.claim_entity_link"] = [
            c for c in cols["silver_v2_claims.claim_entity_link"] if c != "entity_role"
        ]
        client = _make_bq_client(cols)
        result = mod._check_schema(client, "test-proj")
        assert result is False

    def test_missing_add_column_target_table_returns_false(self):
        mod = _import_module()
        cols = _all_columns_present()
        del cols["silver_v2_core.entity_attribute_event"]
        client = _make_bq_client(cols)
        result = mod._check_schema(client, "test-proj")
        assert result is False

    def test_add_column_missing_from_existing_table_returns_false(self):
        mod = _import_module()
        cols = _all_columns_present()
        # Remove value_entity_id from entity_attribute_event
        cols["silver_v2_core.entity_attribute_event"] = ["event_id", "entity_id"]
        client = _make_bq_client(cols)
        result = mod._check_schema(client, "test-proj")
        assert result is False

    def test_legacy_prediction_hash_missing_returns_false(self):
        mod = _import_module()
        cols = _all_columns_present()
        cols["silver_v2_claims.claim"] = [
            "claim_id",
            "legacy_chain_hash",
        ]  # missing legacy_prediction_hash
        client = _make_bq_client(cols)
        result = mod._check_schema(client, "test-proj")
        assert result is False

    def test_missing_table_logs_fail(self, caplog):
        import logging

        mod = _import_module()
        cols = _all_columns_present()
        del cols["silver_v2_claims.claim_state_history"]
        client = _make_bq_client(cols)
        with caplog.at_level(logging.ERROR, logger="apply_kg_schema"):
            mod._check_schema(client, "test-proj")
        assert any("FAIL" in m and "claim_state_history" in m for m in caplog.messages)


# ---------------------------------------------------------------------------
# Tests: main() integration
# ---------------------------------------------------------------------------


class TestMainCheck:
    def test_check_passes_exits_0(self, monkeypatch):
        mod = _import_module()
        client = _make_bq_client(_all_columns_present())

        monkeypatch.setenv("GCP_PROJECT_ID", "test-proj")
        # Patch the module-level _bq_module.Client to return our mock client
        mock_bq = MagicMock()
        mock_bq.Client.return_value = client
        monkeypatch.setattr(mod, "_bq_module", mock_bq)

        with pytest.raises(SystemExit) as exc_info:
            with patch("sys.argv", ["apply_kg_schema.py", "--check"]):
                mod.main()
        assert exc_info.value.code == 0

    def test_check_fails_exits_1(self, monkeypatch):
        mod = _import_module()
        cols = _all_columns_present()
        del cols["silver_v2_claims.claim_entity_link"]
        client = _make_bq_client(cols)

        monkeypatch.setenv("GCP_PROJECT_ID", "test-proj")
        mock_bq = MagicMock()
        mock_bq.Client.return_value = client
        monkeypatch.setattr(mod, "_bq_module", mock_bq)

        with pytest.raises(SystemExit) as exc_info:
            with patch("sys.argv", ["apply_kg_schema.py", "--check"]):
                mod.main()
        assert exc_info.value.code == 1

    def test_check_no_project_id_exits_1(self, monkeypatch):
        mod = _import_module()
        monkeypatch.delenv("GCP_PROJECT_ID", raising=False)

        with pytest.raises(SystemExit) as exc_info:
            with patch("sys.argv", ["apply_kg_schema.py", "--check"]):
                mod.main()
        assert exc_info.value.code == 1

    def test_check_dry_run_does_not_connect(self, monkeypatch):
        mod = _import_module()
        mock_bq = MagicMock()
        monkeypatch.setattr(mod, "_bq_module", mock_bq)
        # --dry-run should return without calling Client()
        with patch("sys.argv", ["apply_kg_schema.py", "--check", "--dry-run"]):
            mod.main()  # should not raise
        mock_bq.Client.assert_not_called()


class TestMainApply:
    def test_apply_delegates_to_apply_migrations(self, monkeypatch):
        mod = _import_module()
        mock_runner = MagicMock()

        # Patch apply_migrations import inside the function
        with patch.dict(
            sys.modules, {"apply_migrations": MagicMock(apply_migrations=mock_runner)}
        ):
            with patch("sys.argv", ["apply_kg_schema.py", "--apply"]):
                mod.main()

        mock_runner.assert_called_once_with(dry_run=False)

    def test_apply_dry_run_passes_flag(self, monkeypatch):
        mod = _import_module()
        mock_runner = MagicMock()

        with patch.dict(
            sys.modules, {"apply_migrations": MagicMock(apply_migrations=mock_runner)}
        ):
            with patch("sys.argv", ["apply_kg_schema.py", "--apply", "--dry-run"]):
                mod.main()

        mock_runner.assert_called_once_with(dry_run=True)

    def test_apply_missing_migration_file_exits_1(self, monkeypatch, tmp_path):
        mod = _import_module()
        # Point _MIGRATION_FILE to a path that doesn't exist
        monkeypatch.setattr(mod, "_MIGRATION_FILE", tmp_path / "nonexistent.sql")

        with pytest.raises(SystemExit) as exc_info:
            with patch("sys.argv", ["apply_kg_schema.py", "--apply"]):
                mod.main()
        assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# Tests: EXPECTED_TABLES / EXPECTED_NEW_COLUMNS completeness
# ---------------------------------------------------------------------------


class TestExpectedConstants:
    def test_all_three_new_tables_declared(self):
        mod = _import_module()
        table_fqns = {(s.dataset, s.table) for s in mod.EXPECTED_TABLES}
        assert ("silver_v2_claims", "claim_entity_link") in table_fqns
        assert ("silver_v2_claims", "claim_state_history") in table_fqns
        assert ("silver_v2_claims", "entity_resolution_queue") in table_fqns

    def test_all_add_columns_declared(self):
        mod = _import_module()
        cols = {(ds, tbl, col) for ds, tbl, col in mod.EXPECTED_NEW_COLUMNS}
        assert ("silver_v2_core", "entity_attribute_event", "value_entity_id") in cols
        assert ("silver_v2_claims", "claim", "legacy_prediction_hash") in cols
        assert ("silver_v2_claims", "claim", "legacy_chain_hash") in cols

    def test_claim_entity_link_required_columns(self):
        mod = _import_module()
        spec = next(s for s in mod.EXPECTED_TABLES if s.table == "claim_entity_link")
        assert "link_id" in spec.required_columns
        assert "entity_role" in spec.required_columns
        assert "ordinal" in spec.required_columns

    def test_claim_state_history_required_columns(self):
        mod = _import_module()
        spec = next(s for s in mod.EXPECTED_TABLES if s.table == "claim_state_history")
        assert "effective_from" in spec.required_columns
        assert "effective_source" in spec.required_columns
        assert "brier_score" in spec.required_columns
        assert "binary_correct" in spec.required_columns

    def test_entity_resolution_queue_required_columns(self):
        mod = _import_module()
        spec = next(
            s for s in mod.EXPECTED_TABLES if s.table == "entity_resolution_queue"
        )
        assert "placeholder_entity_id" in spec.required_columns
        assert "status" in spec.required_columns
        assert "resolved_entity_id" in spec.required_columns
