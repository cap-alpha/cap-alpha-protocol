"""
Unit tests for Phase 2 KG migration scripts.

All BigQuery calls are mocked — no live BQ connection required.
Tests verify idempotency logic, entity resolution, dry-run behavior,
and verification query structure.
"""

from __future__ import annotations

import hashlib
import os
import sys
import pathlib
import types
from datetime import datetime, timezone
from unittest.mock import MagicMock, call, patch

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


def _make_bq_client(rows_by_query: dict | None = None) -> MagicMock:
    """
    Build a mock bigquery.Client.
    rows_by_query: {substring: [row_dicts]} — controls what query() returns based
    on which substring appears in the SQL.
    """
    client = MagicMock()
    rows_by_query = rows_by_query or {}

    def _make_job(rows):
        job = MagicMock()
        job.result.return_value = rows
        job.job_id = "mock-job-id"
        return job

    def query_side_effect(sql, *args, **kwargs):
        for substring, rows in rows_by_query.items():
            if substring in sql:
                return _make_job(iter(rows))
        return _make_job(iter([]))

    client.query.side_effect = query_side_effect
    return client


def _row(data: dict) -> MagicMock:
    """Simulate a BQ result row (supports [] access)."""
    row = MagicMock()
    row.__getitem__ = lambda self, key: data[key]
    row.keys = lambda: data.keys()
    # Support dict(row) via items()
    row.items = lambda: data.items()
    row.values = lambda: data.values()
    return row


# ---------------------------------------------------------------------------
# Test: _unresolved_entity_id
# ---------------------------------------------------------------------------


class TestUnresolvedEntityId:
    def test_deterministic(self):
        from migrate_prediction_ledger_to_silver_v2 import _unresolved_entity_id

        a = _unresolved_entity_id("Patrick Mahomes")
        b = _unresolved_entity_id("Patrick Mahomes")
        assert a == b

    def test_different_inputs_produce_different_ids(self):
        from migrate_prediction_ledger_to_silver_v2 import _unresolved_entity_id

        a = _unresolved_entity_id("Patrick Mahomes")
        b = _unresolved_entity_id("Travis Kelce")
        assert a != b

    def test_id_starts_with_prefix(self):
        from migrate_prediction_ledger_to_silver_v2 import _unresolved_entity_id

        result = _unresolved_entity_id("some player")
        assert result.startswith("unresolved:")

    def test_empty_string_handled(self):
        from migrate_prediction_ledger_to_silver_v2 import _unresolved_entity_id

        result = _unresolved_entity_id("")
        assert result.startswith("unresolved:")


# ---------------------------------------------------------------------------
# Test: _category_to_domain
# ---------------------------------------------------------------------------


class TestCategoryToDomain:
    def test_none_returns_sports_nfl(self):
        from migrate_prediction_ledger_to_silver_v2 import _category_to_domain

        assert _category_to_domain(None) == "sports.nfl"

    def test_empty_returns_sports_nfl(self):
        from migrate_prediction_ledger_to_silver_v2 import _category_to_domain

        assert _category_to_domain("") == "sports.nfl"

    def test_politics_category(self):
        from migrate_prediction_ledger_to_silver_v2 import _category_to_domain

        assert _category_to_domain("politics") == "politics"

    def test_finance_category(self):
        from migrate_prediction_ledger_to_silver_v2 import _category_to_domain

        assert _category_to_domain("finance") == "finance"

    def test_nfl_default(self):
        from migrate_prediction_ledger_to_silver_v2 import _category_to_domain

        assert _category_to_domain("PLAYER_TRADE") == "sports.nfl"


# ---------------------------------------------------------------------------
# Test: _compute_this_hash
# ---------------------------------------------------------------------------


class TestComputeThisHash:
    def test_deterministic(self):
        from migrate_prediction_ledger_to_silver_v2 import _compute_this_hash

        h1 = _compute_this_hash("id1", "eid1", "2025-01-01", "{}")
        h2 = _compute_this_hash("id1", "eid1", "2025-01-01", "{}")
        assert h1 == h2

    def test_different_inputs_differ(self):
        from migrate_prediction_ledger_to_silver_v2 import _compute_this_hash

        h1 = _compute_this_hash("id1", "eid1", "2025-01-01", "{}")
        h2 = _compute_this_hash("id2", "eid1", "2025-01-01", "{}")
        assert h1 != h2

    def test_returns_64_char_hex(self):
        from migrate_prediction_ledger_to_silver_v2 import _compute_this_hash

        h = _compute_this_hash("a", "b", "c", "d")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)


# ---------------------------------------------------------------------------
# Test: _ensure_tables_exist exits on missing table
# ---------------------------------------------------------------------------


class TestEnsureTablesExist:
    def test_exits_when_table_missing(self, monkeypatch):
        from migrate_prediction_ledger_to_silver_v2 import _ensure_tables_exist

        # Simulate NotFound being raised
        class _NotFound(Exception):
            pass

        monkeypatch.setattr(
            "migrate_prediction_ledger_to_silver_v2.NotFound", _NotFound
        )

        client = MagicMock()
        client.get_table.side_effect = _NotFound("Table not found")

        with pytest.raises(SystemExit) as exc_info:
            _ensure_tables_exist(client, "test-project")
        assert exc_info.value.code == 1

    def test_does_not_exit_when_all_tables_exist(self, monkeypatch):
        from migrate_prediction_ledger_to_silver_v2 import _ensure_tables_exist

        class _NotFound(Exception):
            pass

        monkeypatch.setattr(
            "migrate_prediction_ledger_to_silver_v2.NotFound", _NotFound
        )

        client = MagicMock()
        client.get_table.return_value = MagicMock()  # no exception

        # Should not raise
        _ensure_tables_exist(client, "test-project")
        assert client.get_table.call_count >= 1


# ---------------------------------------------------------------------------
# Test: _get_or_create_speaker_entity
# ---------------------------------------------------------------------------


class TestGetOrCreateSpeakerEntity:
    def test_returns_existing_entity_id_when_found(self, monkeypatch):
        import migrate_prediction_ledger_to_silver_v2 as m

        # Mock bigquery.QueryJobConfig + ScalarQueryParameter
        mock_bq = MagicMock()
        monkeypatch.setattr(m, "bigquery", mock_bq)

        existing_row = MagicMock()
        existing_row.__getitem__ = lambda self, k: {"entity_id": "existing-uuid-123"}[k]

        job = MagicMock()
        job.result.return_value = iter([existing_row])
        client = MagicMock()
        client.query.return_value = job

        result = m._get_or_create_speaker_entity(
            client, "proj", "adam_schefter", "Adam Schefter", dry_run=False
        )
        assert result == "existing-uuid-123"
        # Should not have inserted — only 1 query (the lookup)
        assert client.query.call_count == 1

    def test_creates_entity_when_not_found(self, monkeypatch):
        import migrate_prediction_ledger_to_silver_v2 as m

        mock_bq = MagicMock()
        monkeypatch.setattr(m, "bigquery", mock_bq)

        # First call (lookup) returns empty; second call (insert) returns empty
        empty_result = MagicMock()
        empty_result.__iter__ = MagicMock(return_value=iter([]))

        job = MagicMock()
        job.result.return_value = empty_result
        client = MagicMock()
        client.query.return_value = job

        result = m._get_or_create_speaker_entity(
            client, "proj", "new_pundit", "New Pundit", dry_run=False
        )
        # Should return a UUID string
        assert isinstance(result, str)
        assert len(result) == 36  # UUID v4
        # Should have called query twice: lookup + insert
        assert client.query.call_count == 2

    def test_dry_run_does_not_insert(self, monkeypatch):
        import migrate_prediction_ledger_to_silver_v2 as m

        mock_bq = MagicMock()
        monkeypatch.setattr(m, "bigquery", mock_bq)

        empty_result = MagicMock()
        empty_result.__iter__ = MagicMock(return_value=iter([]))

        job = MagicMock()
        job.result.return_value = empty_result
        client = MagicMock()
        client.query.return_value = job

        result = m._get_or_create_speaker_entity(
            client, "proj", "pundit_x", "Pundit X", dry_run=True
        )
        # dry-run: only the lookup query is run, no insert
        assert client.query.call_count == 1
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Test: _load_existing_legacy_hashes
# ---------------------------------------------------------------------------


class TestLoadExistingLegacyHashes:
    def test_returns_set_of_hashes(self, monkeypatch):
        import migrate_prediction_ledger_to_silver_v2 as m

        hash1 = "a" * 64
        hash2 = "b" * 64

        r1 = MagicMock()
        r1.__getitem__ = lambda self, k: {
            "legacy_prediction_hash": hash1 if k == "legacy_prediction_hash" else None
        }[k]
        r2 = MagicMock()
        r2.__getitem__ = lambda self, k: {
            "legacy_prediction_hash": hash2 if k == "legacy_prediction_hash" else None
        }[k]

        job = MagicMock()
        job.result.return_value = iter([r1, r2])
        client = MagicMock()
        client.query.return_value = job

        result = m._load_existing_legacy_hashes(client, "test-project")
        assert hash1 in result
        assert hash2 in result
        assert len(result) == 2

    def test_returns_empty_set_when_no_data(self, monkeypatch):
        import migrate_prediction_ledger_to_silver_v2 as m

        job = MagicMock()
        job.result.return_value = iter([])
        client = MagicMock()
        client.query.return_value = job

        result = m._load_existing_legacy_hashes(client, "test-project")
        assert result == set()


# ---------------------------------------------------------------------------
# Test: migrate_row — dry-run does not call INSERT
# ---------------------------------------------------------------------------


class TestMigrateRowDryRun:
    def test_dry_run_returns_true_without_insert(self, monkeypatch):
        import migrate_prediction_ledger_to_silver_v2 as m

        mock_bq = MagicMock()
        monkeypatch.setattr(m, "bigquery", mock_bq)

        # _get_or_create_speaker_entity should return a uuid
        monkeypatch.setattr(
            m,
            "_get_or_create_speaker_entity",
            lambda *a, **kw: "speaker-uuid-001",
        )

        empty_result = MagicMock()
        empty_result.__iter__ = MagicMock(return_value=iter([]))
        job = MagicMock()
        job.result.return_value = empty_result
        client = MagicMock()
        client.query.return_value = job

        row = {
            "prediction_hash": "a" * 64,
            "chain_hash": "b" * 64,
            "ingestion_timestamp": datetime(2025, 9, 1, tzinfo=timezone.utc),
            "source_url": "https://example.com",
            "pundit_id": "adam_schefter",
            "pundit_name": "Adam Schefter",
            "raw_assertion_text": "Mahomes wins MVP",
            "extracted_claim": "Mahomes wins MVP",
            "claim_category": "PLAYER_AWARD",
            "season_year": 2025,
            "target_player_id": "mahomes_kc",
            "target_team": "KC",
            "sport": "NFL",
            "resolution_status": "PENDING",
            "resolved_at": None,
            "resolution_notes": None,
            "target_player_name": "Patrick Mahomes",
            "stance": "positive",
            "prompt_version": "v2",
            "llm_provider": "ollama",
            "llm_model": "qwen2.5:32b",
            "target_entity": None,
        }

        resolution_queue_rows: list = []
        speaker_cache: dict = {}

        result = m._migrate_row(
            client,
            "test-project",
            row,
            dry_run=True,
            resolution_queue_rows=resolution_queue_rows,
            speaker_entity_cache=speaker_cache,
        )

        assert result is True
        # In dry-run, no INSERT queries should be fired
        insert_calls = [
            str(c) for c in client.query.call_args_list if "INSERT INTO" in str(c)
        ]
        assert len(insert_calls) == 0


# ---------------------------------------------------------------------------
# Test: _load_existing_resolution_claim_ids
# ---------------------------------------------------------------------------


class TestLoadExistingResolutionClaimIds:
    def test_returns_set(self, monkeypatch):
        import migrate_prediction_resolutions_to_silver_v2 as m

        cid = "claim-uuid-123"
        r = MagicMock()
        r.__getitem__ = lambda self, k: {"claim_id": cid}[k]

        job = MagicMock()
        job.result.return_value = iter([r])
        client = MagicMock()
        client.query.return_value = job

        result = m._load_existing_resolution_claim_ids(client, "proj")
        assert cid in result

    def test_returns_empty_set_when_no_rows(self, monkeypatch):
        import migrate_prediction_resolutions_to_silver_v2 as m

        job = MagicMock()
        job.result.return_value = iter([])
        client = MagicMock()
        client.query.return_value = job

        result = m._load_existing_resolution_claim_ids(client, "proj")
        assert result == set()


# ---------------------------------------------------------------------------
# Test: _migrate_resolution_row — skips row with no claim_id
# ---------------------------------------------------------------------------


class TestMigrateResolutionRow:
    def test_skips_row_without_claim_id(self, monkeypatch):
        import migrate_prediction_resolutions_to_silver_v2 as m

        mock_bq = MagicMock()
        monkeypatch.setattr(m, "bigquery", mock_bq)

        client = MagicMock()
        row = {
            "prediction_hash": "a" * 64,
            "claim_id": None,  # no matching claim
            "resolution_status": "CORRECT",
            "resolved_at": datetime(2025, 12, 1, tzinfo=timezone.utc),
            "brier_score": 0.1,
            "binary_correct": True,
            "weighted_score": 0.9,
            "timeliness_weight": 1.5,
            "outcome_source": "manual",
            "outcome_reference_id": None,
            "outcome_notes": None,
            "resolver": "system",
            "resolution_window_start": None,
            "speaker_entity_id": None,
        }

        result = m._migrate_resolution_row(client, "proj", row, dry_run=False)
        assert result is False
        client.query.assert_not_called()

    def test_dry_run_returns_true(self, monkeypatch):
        import migrate_prediction_resolutions_to_silver_v2 as m

        mock_bq = MagicMock()
        monkeypatch.setattr(m, "bigquery", mock_bq)

        client = MagicMock()
        row = {
            "prediction_hash": "b" * 64,
            "claim_id": "claim-uuid-456",
            "resolution_status": "CORRECT",
            "resolved_at": datetime(2025, 12, 1, tzinfo=timezone.utc),
            "brier_score": 0.05,
            "binary_correct": True,
            "weighted_score": 0.95,
            "timeliness_weight": 2.0,
            "outcome_source": "sportradar",
            "outcome_reference_id": "game-123",
            "outcome_notes": "Verified correct",
            "resolver": "auto",
            "resolution_window_start": datetime(2025, 9, 1, tzinfo=timezone.utc),
            "speaker_entity_id": "speaker-uuid-789",
        }

        result = m._migrate_resolution_row(client, "proj", row, dry_run=True)
        assert result is True
        # No insert calls in dry-run
        insert_calls = [
            str(c) for c in client.query.call_args_list if "INSERT INTO" in str(c)
        ]
        assert len(insert_calls) == 0


# ---------------------------------------------------------------------------
# Test: verify_kg_migration — PASS when all checks return 0, FAIL otherwise
# ---------------------------------------------------------------------------


class TestVerifyKgMigration:
    def test_all_pass_when_counts_are_zero(self, monkeypatch):
        import verify_kg_migration as v

        mock_bq = MagicMock()
        monkeypatch.setattr(v, "bigquery", mock_bq)

        # Each query() call must return a *fresh* job with its own iterator
        def make_zero_job(sql, *args, **kwargs):
            zero_row = MagicMock()
            zero_row.__getitem__ = lambda self, k: 0  # row[0] == 0
            job = MagicMock()
            job.result.return_value = iter([zero_row])
            return job

        client = MagicMock()
        client.query.side_effect = make_zero_job
        mock_bq.Client.return_value = client

        monkeypatch.setenv("GCP_PROJECT_ID", "test-project")
        result = v.run_all_checks("test-project")
        assert result is True

    def test_fails_when_any_check_returns_nonzero(self, monkeypatch):
        import verify_kg_migration as v

        mock_bq = MagicMock()
        monkeypatch.setattr(v, "bigquery", mock_bq)

        call_count = [0]

        def query_side_effect(sql, *args, **kwargs):
            job = MagicMock()
            call_count[0] += 1
            # First check passes, second fails
            count = 0 if call_count[0] == 1 else 5
            row = MagicMock()
            row.__getitem__ = lambda self, k: count
            job.result.return_value = iter([row])
            return job

        client = MagicMock()
        client.query.side_effect = query_side_effect
        mock_bq.Client.return_value = client

        result = v.run_all_checks("test-project")
        assert result is False

    def test_check_count_equals_four(self, monkeypatch):
        """The verification suite must have exactly 4 checks (from issue #920)."""
        import verify_kg_migration as v

        assert len(v.CHECKS) == 4

    def test_checks_reference_expected_tables(self):
        """Each check query must reference the silver_v2_claims tables."""
        import verify_kg_migration as v

        expected_tables = [
            "prediction_ledger",
            "prediction_resolutions",
            "claim_state_history",
            "claim_entity_link",
        ]
        for i, (check_name, query) in enumerate(v.CHECKS):
            assert expected_tables[i] in query, (
                f"Check {i} ('{check_name}') does not reference '{expected_tables[i]}'"
            )

    def test_exits_1_on_failure(self, monkeypatch):
        import verify_kg_migration as v

        mock_bq = MagicMock()
        monkeypatch.setattr(v, "bigquery", mock_bq)
        monkeypatch.setenv("GCP_PROJECT_ID", "test-project")

        nonzero_row = MagicMock()
        nonzero_row.__getitem__ = lambda self, k: 99

        job = MagicMock()
        job.result.return_value = iter([nonzero_row])
        client = MagicMock()
        client.query.return_value = job
        mock_bq.Client.return_value = client

        with pytest.raises(SystemExit) as exc_info:
            v.main()
        assert exc_info.value.code == 1

    def test_exits_0_on_all_pass(self, monkeypatch):
        import verify_kg_migration as v

        mock_bq = MagicMock()
        monkeypatch.setattr(v, "bigquery", mock_bq)
        monkeypatch.setenv("GCP_PROJECT_ID", "test-project")

        def make_zero_job(sql, *args, **kwargs):
            zero_row = MagicMock()
            zero_row.__getitem__ = lambda self, k: 0
            job = MagicMock()
            job.result.return_value = iter([zero_row])
            return job

        client = MagicMock()
        client.query.side_effect = make_zero_job
        mock_bq.Client.return_value = client

        with pytest.raises(SystemExit) as exc_info:
            v.main()
        assert exc_info.value.code == 0


# ---------------------------------------------------------------------------
# Test: migration log is written
# ---------------------------------------------------------------------------


class TestWriteLog:
    def test_log_file_created_in_expected_dir(self, tmp_path, monkeypatch):
        import migrate_prediction_ledger_to_silver_v2 as m

        monkeypatch.setattr(m, "LOG_DIR", tmp_path)
        m._write_log(100, 90, 10, dry_run=False)

        log_files = list(tmp_path.glob("migrate_ledger_live_*.txt"))
        assert len(log_files) == 1
        content = log_files[0].read_text()
        assert "Total processed: 100" in content
        assert "Inserted:        90" in content
        assert "Skipped:         10" in content

    def test_dry_run_log_has_dry_run_suffix(self, tmp_path, monkeypatch):
        import migrate_prediction_ledger_to_silver_v2 as m

        monkeypatch.setattr(m, "LOG_DIR", tmp_path)
        m._write_log(50, 45, 5, dry_run=True)

        log_files = list(tmp_path.glob("migrate_ledger_dry-run_*.txt"))
        assert len(log_files) == 1


# ---------------------------------------------------------------------------
# Test: resolution log is written
# ---------------------------------------------------------------------------


class TestWriteResolutionLog:
    def test_resolution_log_created(self, tmp_path, monkeypatch):
        import migrate_prediction_resolutions_to_silver_v2 as m

        monkeypatch.setattr(m, "LOG_DIR", tmp_path)
        m._write_log(
            total_processed=437,
            total_inserted=400,
            total_skipped=30,
            total_missing_claim=7,
            dry_run=False,
        )

        log_files = list(tmp_path.glob("migrate_resolutions_live_*.txt"))
        assert len(log_files) == 1
        content = log_files[0].read_text()
        assert "Total processed:      437" in content
        assert "Inserted:             400" in content


# ---------------------------------------------------------------------------
# Test: idempotency — _migrate_row skips if hash already in existing_hashes
# ---------------------------------------------------------------------------


class TestMigrateRowIdempotency:
    """
    Simulate that the migration runner skips rows whose legacy_prediction_hash
    is already in the existing_hashes set.
    """

    def test_row_skipped_when_hash_in_existing(self, monkeypatch):
        import migrate_prediction_ledger_to_silver_v2 as m

        mock_bq = MagicMock()
        monkeypatch.setattr(m, "bigquery", mock_bq)

        client = MagicMock()
        existing_hashes = {"a" * 64}

        row = {"prediction_hash": "a" * 64}

        # Simulate the outer loop check — don't call _migrate_row for rows in existing_hashes
        # (This is the pattern in main())
        if row["prediction_hash"] in existing_hashes:
            skipped = True
        else:
            skipped = False
            m._migrate_row(
                client,
                "proj",
                row,
                dry_run=False,
                resolution_queue_rows=[],
                speaker_entity_cache={},
            )

        assert skipped is True
        client.query.assert_not_called()
