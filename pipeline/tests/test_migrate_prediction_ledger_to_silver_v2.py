"""
Unit tests for scripts/migrate_prediction_ledger_to_silver_v2.py — the Phase 0
bridge migration (issue #1129 §5: "Bridge first: run
migrate_prediction_ledger_to_silver_v2.py ... migrate all 2,669 legacy rows
as-is").

This PR hardens three properties without needing a live BigQuery connection:

  1. Idempotency — a second run (or a run against a corpus with a
     partially-migrated row from an interrupted prior run) must not
     double-insert, and must correctly backfill any partial row instead of
     silently skipping it forever.
  2. Full-corpus migration — every source row with a usable prediction_hash
     is migrated (no dedup — dedup is an explicit, separate follow-up).
  3. --dry-run parity — dry-run exercises the *same* subject-entity
     resolution path as a live run, and performs zero writes.

Rather than mock google.cloud.bigquery.Client with a rubber-stamp stub, this
file hand-rolls a small in-memory reimplementation of the specific SQL
statements the script issues (INSERT ... WHERE NOT EXISTS, MERGE ... WHEN NOT
MATCHED) — see FakeBigQueryClient below. That gives *real* two-run
idempotency coverage (row counts genuinely don't move on rerun) while
staying fast, deterministic, and independent of any BigQuery/DuckDB
connection. See the PR description for why this script isn't run against the
DuckDB local backend directly: its MERGE and `JSON @param` literal-cast BQ
syntax don't currently translate through
pipeline/src/duckdb_manager.py's _translate_bq_sql (confirmed by direct
testing — bare `MERGE` needs `MERGE INTO` in DuckDB, and `JSON @param`
translates to invalid `VARCHAR $param`). Fixing that translation layer is a
separate, shared-file concern (duckdb_manager.py is not in this PR's scope).
"""

from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any

import pytest

from scripts import migrate_prediction_ledger_to_silver_v2 as bridge
from scripts.migrate_prediction_ledger_to_silver_v2 import (
    _classify_row,
    _generate_verification_report,
    _load_migration_state,
    run_migration,
)

PROJECT_ID = "test-project"


@pytest.fixture(autouse=True)
def _isolate_log_dir(tmp_path, monkeypatch):
    """run_migration() writes a summary file to LOG_DIR on every call. Redirect
    it to a pytest tmp_path so running this suite doesn't leave real files
    under pipeline/migrations/logs/."""
    monkeypatch.setattr(bridge, "LOG_DIR", tmp_path)


# ---------------------------------------------------------------------------
# FakeBigQueryClient — see module docstring for why this exists.
# ---------------------------------------------------------------------------


class FakeBQRow(dict):
    """dict subclass with attribute access, mirroring google.cloud.bigquery.Row."""

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name)


class FakeJob:
    def __init__(self, rows: list[dict]):
        self._rows = rows

    def result(self):
        return self._rows


def _params(job_config) -> dict[str, Any]:
    if job_config is None or not getattr(job_config, "query_parameters", None):
        return {}
    return {qp.name: qp.value for qp in job_config.query_parameters}


class FakeBigQueryClient:
    """In-memory stand-in that reimplements just the write-guard semantics
    (WHERE NOT EXISTS / MERGE WHEN NOT MATCHED) the real script relies on for
    idempotency, dispatched by matching stable substrings unique to each SQL
    statement the script constructs.
    """

    def __init__(self, ledger_rows: list[dict]):
        self.ledger = list(ledger_rows)
        self.entity: list[dict] = []
        self.claim: list[dict] = []
        self.claim_state_history: list[dict] = []
        self.claim_entity_link: list[dict] = []
        self.entity_resolution_queue: list[dict] = []
        self.executed_sql: list[str] = []

    # _ensure_tables_exist calls client.get_table() per required table.
    def get_table(self, _table_ref):
        return object()

    def query(self, sql: str, job_config=None):
        self.executed_sql.append(sql)
        p = _params(job_config)

        # --- reads ---
        if "AS has_history" in sql:
            return FakeJob(self._select_migration_state())
        if "AS total_rows" in sql:
            return FakeJob(self._select_source_stats())
        if "HAVING COUNT(*) > 1" in sql:
            return FakeJob(self._select_target_duplicates())
        if "ORDER BY ingestion_timestamp, prediction_hash" in sql:
            return FakeJob(self._select_ledger_batch(sql))
        if "$.pundit_id" in sql:
            return FakeJob(self._select_speaker_entity(p["pundit_id"]))
        if "entity_alias` a USING (entity_id)" in sql:
            return FakeJob([])  # no aliases seeded in these fixtures
        if "notes = @raw_string" in sql:
            return FakeJob(self._select_unresolved_fallback(p["raw_string"]))

        # --- writes ---
        if "'person', 'sports.nfl', JSON @external_ids" in sql:
            return FakeJob(self._insert_speaker_entity(p))
        if "'unresolved', @domain, @notes, CURRENT_TIMESTAMP())" in sql:
            return FakeJob(self._merge_placeholder_entity(p))
        if "entity_resolution_queue` AS target" in sql:
            return FakeJob(self._merge_queue_row(p))
        if "'legacy_migration'" in sql:
            return FakeJob(self._insert_claim(p))
        if "'backfill from gold_layer.prediction_ledger'" in sql:
            return FakeJob(self._insert_history(p))
        if "link_id, claim_id, entity_id, entity_role, ordinal, created_at" in sql:
            return FakeJob(self._insert_link(p))

        raise AssertionError(f"FakeBigQueryClient: unrecognized query:\n{sql}")

    # -- reads --

    def _select_migration_state(self) -> list[dict]:
        rows = []
        for c in self.claim:
            if not c.get("legacy_prediction_hash"):
                continue
            has_history = any(
                h["claim_id"] == c["claim_id"] for h in self.claim_state_history
            )
            has_links = any(
                l["claim_id"] == c["claim_id"] for l in self.claim_entity_link
            )
            rows.append(
                FakeBQRow(
                    legacy_prediction_hash=c["legacy_prediction_hash"],
                    claim_id=c["claim_id"],
                    has_history=has_history,
                    has_links=has_links,
                )
            )
        return rows

    def _select_source_stats(self) -> list[dict]:
        values = [r.get("prediction_hash") for r in self.ledger]
        total = len(values)
        null_or_blank = sum(1 for v in values if not v)
        non_null = [v for v in values if v is not None]
        dup = len(non_null) - len(set(non_null))
        return [
            FakeBQRow(
                total_rows=total, null_hash_rows=null_or_blank, duplicate_hash_rows=dup
            )
        ]

    def _select_target_duplicates(self) -> list[dict]:
        counts = Counter(
            c["legacy_prediction_hash"]
            for c in self.claim
            if c.get("legacy_prediction_hash")
        )
        n = sum(1 for cnt in counts.values() if cnt > 1)
        return [FakeBQRow(n=n)]

    def _select_ledger_batch(self, sql: str) -> list[dict]:
        limit = int(re.search(r"LIMIT (\d+)", sql).group(1))
        offset = int(re.search(r"OFFSET (\d+)", sql).group(1))
        ordered = sorted(
            self.ledger,
            key=lambda r: (
                r.get("ingestion_timestamp") or "",
                r.get("prediction_hash") or "",
            ),
        )
        return [FakeBQRow(**r) for r in ordered[offset : offset + limit]]

    def _select_speaker_entity(self, pundit_id: str) -> list[dict]:
        for e in self.entity:
            ext = e.get("external_ids")
            if ext and json.loads(ext).get("pundit_id") == pundit_id:
                return [FakeBQRow(entity_id=e["entity_id"])]
        return []

    def _select_unresolved_fallback(self, raw_string: str) -> list[dict]:
        for e in self.entity:
            if e.get("entity_kind") == "unresolved" and e.get("notes") == raw_string:
                return [FakeBQRow(entity_id=e["entity_id"])]
        return []

    # -- writes (each mirrors the real statement's own idempotency guard) --

    def _insert_speaker_entity(self, p: dict) -> list[dict]:
        self.entity.append(
            {
                "entity_id": p["entity_id"],
                "entity_kind": "person",
                "primary_domain": "sports.nfl",
                "external_ids": p["external_ids"],
                "notes": None,
            }
        )
        return []

    def _merge_placeholder_entity(self, p: dict) -> list[dict]:
        if not any(e["entity_id"] == p["entity_id"] for e in self.entity):
            self.entity.append(
                {
                    "entity_id": p["entity_id"],
                    "entity_kind": "unresolved",
                    "primary_domain": p["domain"],
                    "notes": p["notes"],
                    "external_ids": None,
                }
            )
        return []

    def _merge_queue_row(self, p: dict) -> list[dict]:
        key = (p["placeholder_entity_id"], p["raw_entity_string"])
        exists = any(
            (q["placeholder_entity_id"], q["raw_entity_string"]) == key
            for q in self.entity_resolution_queue
        )
        if not exists:
            self.entity_resolution_queue.append(dict(p))
        return []

    def _insert_claim(self, p: dict) -> list[dict]:
        exists = any(
            c["legacy_prediction_hash"] == p["legacy_prediction_hash"]
            for c in self.claim
        )
        if not exists:
            self.claim.append(
                {
                    "claim_id": p["claim_id"],
                    "speaker_entity_id": p["speaker_entity_id"],
                    "domain": p["domain"],
                    "legacy_prediction_hash": p["legacy_prediction_hash"],
                    "legacy_chain_hash": p["legacy_chain_hash"],
                    "this_hash": p["this_hash"],
                }
            )
        return []

    def _insert_history(self, p: dict) -> list[dict]:
        claim = next(
            (
                c
                for c in self.claim
                if c["legacy_prediction_hash"] == p["legacy_prediction_hash"]
            ),
            None,
        )
        if claim is None:
            return []
        if not any(
            h["claim_id"] == claim["claim_id"] for h in self.claim_state_history
        ):
            self.claim_state_history.append(
                {
                    "history_id": p["history_id"],
                    "claim_id": claim["claim_id"],
                    "state": p["state"],
                }
            )
        return []

    def _insert_link(self, p: dict) -> list[dict]:
        claim = next(
            (
                c
                for c in self.claim
                if c["legacy_prediction_hash"] == p["legacy_prediction_hash"]
            ),
            None,
        )
        if claim is None:
            return []
        exists = any(
            l["claim_id"] == claim["claim_id"]
            and l["entity_id"] == p["entity_id"]
            and l["entity_role"] == p["entity_role"]
            for l in self.claim_entity_link
        )
        if not exists:
            self.claim_entity_link.append(
                {
                    "link_id": p["link_id"],
                    "claim_id": claim["claim_id"],
                    "entity_id": p["entity_id"],
                    "entity_role": p["entity_role"],
                    "ordinal": p["ordinal"],
                }
            )
        return []


# ---------------------------------------------------------------------------
# Fixture data
# ---------------------------------------------------------------------------


def _ledger_row(n: int, **overrides) -> dict:
    row = {
        "prediction_hash": f"hash-{n}",
        "chain_hash": f"chain-{n}",
        "ingestion_timestamp": f"2026-0{n}-01T00:00:00+00:00",
        "source_url": f"https://example.com/{n}",
        "pundit_id": f"pundit-{n % 2}",  # two rows can share a pundit
        "pundit_name": f"Pundit {n % 2}",
        "raw_assertion_text": f"Player {n} will do a thing",
        "extracted_claim": f"Player {n} will do a thing",
        "claim_category": "nfl_performance",
        "season_year": 2026,
        "target_player_id": None,
        "target_player_name": f"Player {n}",
        "target_team": "SEA",
        "sport": "NFL",
        "resolution_status": "PENDING",
        "resolved_at": None,
        "resolution_notes": None,
        "stance": "for",
        "prompt_version": "v1",
        "llm_provider": "gemini",
        "llm_model": "gemini-3-flash",
        "target_entity": None,
    }
    row.update(overrides)
    return row


# ---------------------------------------------------------------------------
# _classify_row — pure function, no I/O
# ---------------------------------------------------------------------------


class TestClassifyRow:
    def test_malformed_when_blank_or_none(self):
        assert _classify_row("", {}) == "malformed"
        assert _classify_row(None, {}) == "malformed"

    def test_new_when_absent_from_state(self):
        assert _classify_row("h1", {}) == "new"

    def test_skip_when_fully_bridged(self):
        state = {"h1": {"claim_id": "c1", "has_history": True, "has_links": True}}
        assert _classify_row("h1", state) == "skip"

    def test_repair_when_missing_history(self):
        state = {"h1": {"claim_id": "c1", "has_history": False, "has_links": True}}
        assert _classify_row("h1", state) == "repair"

    def test_repair_when_missing_links(self):
        state = {"h1": {"claim_id": "c1", "has_history": True, "has_links": False}}
        assert _classify_row("h1", state) == "repair"

    def test_repair_when_missing_both(self):
        state = {"h1": {"claim_id": "c1", "has_history": False, "has_links": False}}
        assert _classify_row("h1", state) == "repair"


# ---------------------------------------------------------------------------
# run_migration — end-to-end idempotency against FakeBigQueryClient
# ---------------------------------------------------------------------------


class TestIdempotency:
    def test_second_run_is_full_noop(self):
        """AC: re-running the bridge must not double-insert or corrupt
        legacy_prediction_hash. Two full runs over the same source data must
        leave the target tables byte-for-byte identical after run 1."""
        ledger = [
            _ledger_row(1),
            _ledger_row(2),
            _ledger_row(3, target_player_name=None, target_team=None),
        ]
        client = FakeBigQueryClient(ledger)

        stats1 = run_migration(client, PROJECT_ID, dry_run=False, batch_size=100)
        assert stats1 == {
            "total_processed": 3,
            "total_inserted": 3,
            "total_repaired": 0,
            "total_skipped": 0,
            "total_malformed": 0,
        }
        assert len(client.claim) == 3
        assert len(client.claim_state_history) == 3
        assert len(client.claim_entity_link) >= 3  # >=1 link per claim

        claim_snapshot = [dict(c) for c in client.claim]
        history_snapshot = [dict(h) for h in client.claim_state_history]
        link_snapshot = [dict(l) for l in client.claim_entity_link]

        stats2 = run_migration(client, PROJECT_ID, dry_run=False, batch_size=100)
        assert stats2 == {
            "total_processed": 3,
            "total_inserted": 0,
            "total_repaired": 0,
            "total_skipped": 3,
            "total_malformed": 0,
        }
        # Nothing moved — true no-op.
        assert client.claim == claim_snapshot
        assert client.claim_state_history == history_snapshot
        assert client.claim_entity_link == link_snapshot

    def test_interrupted_migration_is_repaired_not_reskipped_forever(self):
        """Adversarial case: a prior run crashed after writing the claim row
        but before writing claim_state_history / claim_entity_link. The old
        "skip if legacy_prediction_hash already exists" logic would silently
        skip this row on every future run, leaving it permanently incomplete.
        The hardened classify/repair path must detect and backfill it."""
        ledger = [_ledger_row(1), _ledger_row(2)]
        client = FakeBigQueryClient(ledger)

        # Simulate a partial prior run: claim for hash-1 exists, nothing else.
        client.claim.append(
            {
                "claim_id": "pre-existing-claim-id",
                "speaker_entity_id": "some-speaker",
                "domain": "sports.nfl",
                "legacy_prediction_hash": "hash-1",
                "legacy_chain_hash": "chain-1",
                "this_hash": "stale-hash",
            }
        )

        stats = run_migration(client, PROJECT_ID, dry_run=False, batch_size=100)

        assert stats["total_repaired"] == 1
        assert stats["total_inserted"] == 1  # hash-2, never touched before
        assert stats["total_skipped"] == 0
        assert stats["total_processed"] == 2

        # Repair must NOT create a second claim row for hash-1.
        hash1_claims = [
            c for c in client.claim if c["legacy_prediction_hash"] == "hash-1"
        ]
        assert len(hash1_claims) == 1
        assert hash1_claims[0]["claim_id"] == "pre-existing-claim-id"

        # The pre-existing claim now has its history + link backfilled.
        assert any(
            h["claim_id"] == "pre-existing-claim-id" for h in client.claim_state_history
        )
        assert any(
            l["claim_id"] == "pre-existing-claim-id" for l in client.claim_entity_link
        )

        # A third run (post-repair) must now be a full no-op.
        stats2 = run_migration(client, PROJECT_ID, dry_run=False, batch_size=100)
        assert stats2["total_inserted"] == 0
        assert stats2["total_repaired"] == 0
        assert stats2["total_skipped"] == 2

    def test_duplicate_legacy_hash_across_two_claim_rows_is_flagged(self):
        """Safety net: if the idempotency invariant is ever violated (two
        claim rows sharing one legacy_prediction_hash — should never happen
        given the WHERE NOT EXISTS guard, but verify the detector works)."""
        client = FakeBigQueryClient([])
        client.claim.append(
            {
                "claim_id": "c1",
                "legacy_prediction_hash": "dup-hash",
                "speaker_entity_id": "s",
                "domain": "sports.nfl",
                "legacy_chain_hash": "",
                "this_hash": "h1",
            }
        )
        client.claim.append(
            {
                "claim_id": "c2",
                "legacy_prediction_hash": "dup-hash",
                "speaker_entity_id": "s",
                "domain": "sports.nfl",
                "legacy_chain_hash": "",
                "this_hash": "h2",
            }
        )
        state = _load_migration_state(client, PROJECT_ID)
        # Detector doesn't crash; last-write-wins in the returned map, but the
        # duplicate is logged (see _generate_verification_report test below
        # for the counted version via target_duplicate_legacy_hash_count).
        assert "dup-hash" in state


class TestDryRun:
    def test_dry_run_performs_zero_writes_but_exercises_resolution(self):
        ledger = [_ledger_row(1), _ledger_row(2)]
        client = FakeBigQueryClient(ledger)

        stats = run_migration(client, PROJECT_ID, dry_run=True, batch_size=100)

        assert stats["total_inserted"] == 2
        assert stats["total_processed"] == 2

        # No writes anywhere.
        assert client.entity == []
        assert client.claim == []
        assert client.claim_state_history == []
        assert client.claim_entity_link == []
        assert client.entity_resolution_queue == []

        # But the real subject-entity alias-resolution SELECT was issued for
        # each row (proves dry-run runs the same resolution path as a live
        # run, not the old divergent stub that never queried the DB).
        alias_lookups = [
            s for s in client.executed_sql if "entity_alias` a USING (entity_id)" in s
        ]
        assert len(alias_lookups) >= 2

    def test_dry_run_twice_is_stable(self):
        """Running --dry-run twice must report the same counts both times
        (nothing persisted between runs to change the second preview)."""
        ledger = [_ledger_row(1), _ledger_row(2), _ledger_row(3)]
        client = FakeBigQueryClient(ledger)

        stats1 = run_migration(client, PROJECT_ID, dry_run=True, batch_size=100)
        stats2 = run_migration(client, PROJECT_ID, dry_run=True, batch_size=100)
        assert (
            stats1
            == stats2
            == {
                "total_processed": 3,
                "total_inserted": 3,
                "total_repaired": 0,
                "total_skipped": 0,
                "total_malformed": 0,
            }
        )


class TestMalformedRows:
    def test_null_prediction_hash_is_counted_not_silently_dropped(self):
        """Regression test for the pre-hardening counting bug: a row with no
        usable prediction_hash used to vanish from the accounting entirely
        (neither inserted nor skipped), so processed != inserted+skipped."""
        ledger = [_ledger_row(1), _ledger_row(2, prediction_hash=None)]
        client = FakeBigQueryClient(ledger)

        stats = run_migration(client, PROJECT_ID, dry_run=False, batch_size=100)

        assert stats["total_malformed"] == 1
        assert stats["total_inserted"] == 1
        assert (
            stats["total_inserted"]
            + stats["total_repaired"]
            + stats["total_skipped"]
            + stats["total_malformed"]
            == stats["total_processed"]
        )


# ---------------------------------------------------------------------------
# _generate_verification_report
# ---------------------------------------------------------------------------


class TestVerificationReport:
    def test_report_counts_on_fresh_corpus(self):
        ledger = [_ledger_row(1), _ledger_row(2), _ledger_row(3, prediction_hash=None)]
        client = FakeBigQueryClient(ledger)

        report = _generate_verification_report(client, PROJECT_ID)

        assert report["source_row_count"] == 3
        assert report["source_null_or_blank_hash_count"] == 1
        assert report["source_duplicate_hash_count"] == 0
        assert report["bridged_complete_count"] == 0
        assert report["bridged_partial_count"] == 0
        assert report["pending_migration_count"] == 2
        assert report["target_duplicate_legacy_hash_count"] == 0

    def test_report_reflects_partial_and_complete_after_a_run(self):
        ledger = [_ledger_row(1), _ledger_row(2)]
        client = FakeBigQueryClient(ledger)
        run_migration(client, PROJECT_ID, dry_run=False, batch_size=100)

        # Simulate a THIRD row that's mid-migration (claim only, no history/link).
        client.ledger.append(_ledger_row(3))
        client.claim.append(
            {
                "claim_id": "partial-claim",
                "speaker_entity_id": "s",
                "domain": "sports.nfl",
                "legacy_prediction_hash": "hash-3",
                "legacy_chain_hash": "",
                "this_hash": "h3",
            }
        )

        report = _generate_verification_report(client, PROJECT_ID)
        assert report["source_row_count"] == 3
        assert report["bridged_complete_count"] == 2
        assert report["bridged_partial_count"] == 1
        assert report["pending_migration_count"] == 0

    def test_report_flags_duplicate_legacy_hash_in_target(self):
        client = FakeBigQueryClient([_ledger_row(1)])
        client.claim.append(
            {
                "claim_id": "c1",
                "legacy_prediction_hash": "hash-1",
                "speaker_entity_id": "s",
                "domain": "sports.nfl",
                "legacy_chain_hash": "",
                "this_hash": "h1",
            }
        )
        client.claim.append(
            {
                "claim_id": "c2",
                "legacy_prediction_hash": "hash-1",
                "speaker_entity_id": "s",
                "domain": "sports.nfl",
                "legacy_chain_hash": "",
                "this_hash": "h1-dup",
            }
        )
        report = _generate_verification_report(client, PROJECT_ID)
        assert report["target_duplicate_legacy_hash_count"] == 1
