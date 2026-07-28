"""
Tests for the Cryptographic Hashing Pipeline (Issue #111, #552).

Unit tests run without BigQuery. Integration tests require GCP_PROJECT_ID.
"""

import hashlib
import os
import threading
from datetime import datetime, timezone
from unittest.mock import MagicMock, call, patch

import pandas as pd
import pytest

from src.cryptographic_ledger import (
    HASH_SEED,
    PunditPrediction,
    _canonical_payload,
    _read_chain_head,
    _try_advance_chain_head,
    compute_chain_hash,
    compute_prediction_hash,
    get_latest_chain_hash,
    ingest_batch,
    ingest_prediction,
    verify_chain_integrity,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_prediction():
    return PunditPrediction(
        pundit_id="adam_schefter",
        pundit_name="Adam Schefter",
        source_url="https://twitter.com/AdamSchefter/status/123456",
        raw_assertion_text="Patrick Mahomes will win MVP this season.",
        extracted_claim="Mahomes wins MVP",
        claim_category="player_performance",
        season_year=2025,
        target_player_id="P_MAHOMES",
        target_team="KC",
        ingestion_timestamp=datetime(2025, 9, 1, 12, 0, 0, tzinfo=timezone.utc),
    )


def _make_mock_db(chain_head: str = HASH_SEED):
    """
    Return a MagicMock DBManager configured for the new atomic-guard path.

    - ``db.fetch_df`` returns the chain_head sentinel row (or empty DataFrame).
    - ``db.client.query().result()`` is a no-op (DDL / MERGE calls).
    - MERGE job reports 1 row affected (i.e. we win the race) by default.
    - ``db.client.load_table_from_dataframe`` returns a no-op job.
    - ``db.append_dataframe_to_table`` delegates to
      ``db.client.load_table_from_dataframe`` (#1132 routes _append_to_ledger
      through append_dataframe_to_table instead of calling the client
      method directly) so existing assertions against
      ``db.client.load_table_from_dataframe.call_args`` keep working.
    """
    db = MagicMock()

    # _ensure_chain_head_table and _try_advance_chain_head both call
    # db.client.query(...).result()  — make the job return num_dml_affected_rows=1
    merge_job = MagicMock()
    merge_job.result.return_value = None
    merge_job.num_dml_affected_rows = 1
    db.client.query.return_value = merge_job

    # _read_chain_head calls db.fetch_df for the sentinel, then any subsequent
    # call from verify_chain_integrity etc reads the main ledger.
    if chain_head == HASH_SEED:
        # sentinel table is empty (fresh ledger)
        db.fetch_df.return_value = pd.DataFrame()
    else:
        # sentinel row exists
        db.fetch_df.return_value = pd.DataFrame({"chain_hash": [chain_head]})

    # _append_to_ledger calls db.append_dataframe_to_table (#1132), which
    # delegates to db.client.load_table_from_dataframe.
    append_job = MagicMock()
    append_job.result.return_value = None
    db.client.load_table_from_dataframe.return_value = append_job
    db.append_dataframe_to_table.side_effect = lambda df, table_name: (
        db.client.load_table_from_dataframe(df, table_name, job_config=None)
    )

    return db


@pytest.fixture
def mock_db():
    return _make_mock_db()


# ---------------------------------------------------------------------------
# Unit tests — no BigQuery required
# ---------------------------------------------------------------------------


class TestCanonicalPayload:
    def test_deterministic(self, sample_prediction):
        p1 = _canonical_payload(sample_prediction)
        p2 = _canonical_payload(sample_prediction)
        assert p1 == p2

    def test_contains_all_fields(self, sample_prediction):
        payload = _canonical_payload(sample_prediction)
        assert sample_prediction.pundit_id in payload
        assert sample_prediction.source_url in payload
        assert sample_prediction.raw_assertion_text in payload

    def test_pipe_delimited(self, sample_prediction):
        payload = _canonical_payload(sample_prediction)
        parts = payload.split("|")
        assert len(parts) == 4

    def test_changes_when_text_changes(self, sample_prediction):
        p1 = _canonical_payload(sample_prediction)
        sample_prediction.raw_assertion_text = "Different text."
        p2 = _canonical_payload(sample_prediction)
        assert p1 != p2


class TestPredictionHash:
    def test_returns_sha256_hex(self, sample_prediction):
        h = compute_prediction_hash(sample_prediction)
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_deterministic(self, sample_prediction):
        assert compute_prediction_hash(sample_prediction) == compute_prediction_hash(
            sample_prediction
        )

    def test_unique_per_prediction(self, sample_prediction):
        h1 = compute_prediction_hash(sample_prediction)
        sample_prediction.raw_assertion_text = "A totally different claim."
        h2 = compute_prediction_hash(sample_prediction)
        assert h1 != h2

    def test_matches_manual_sha256(self, sample_prediction):
        payload = _canonical_payload(sample_prediction)
        expected = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        assert compute_prediction_hash(sample_prediction) == expected


class TestChainHash:
    def test_deterministic(self):
        h = compute_chain_hash("abc123", "prev456")
        assert h == compute_chain_hash("abc123", "prev456")

    def test_changes_with_previous(self):
        h1 = compute_chain_hash("abc123", "seed_A")
        h2 = compute_chain_hash("abc123", "seed_B")
        assert h1 != h2

    def test_returns_sha256_hex(self):
        h = compute_chain_hash("abc", HASH_SEED)
        assert len(h) == 64


class TestGetLatestChainHash:
    def test_returns_seed_when_empty(self, mock_db):
        mock_db.fetch_df.return_value = pd.DataFrame()
        result = get_latest_chain_hash(mock_db)
        assert result == HASH_SEED

    def test_returns_stored_hash_when_rows_exist(self, mock_db):
        mock_db.fetch_df.return_value = pd.DataFrame(
            {"chain_hash": ["abc123def456" + "0" * 52]}
        )
        result = get_latest_chain_hash(mock_db)
        assert result == "abc123def456" + "0" * 52

    def test_returns_seed_on_query_error(self, mock_db):
        mock_db.fetch_df.side_effect = Exception("BQ unavailable")
        result = get_latest_chain_hash(mock_db)
        assert result == HASH_SEED


class TestIngestPrediction:
    def test_ingest_calls_append(self, sample_prediction, mock_db):
        prediction_hash = ingest_prediction(sample_prediction, db=mock_db)
        assert len(prediction_hash) == 64
        mock_db.client.load_table_from_dataframe.assert_called_once()

    def test_ingest_uses_seed_for_first_record(self, sample_prediction, mock_db):
        # empty sentinel → seed used
        mock_db.fetch_df.return_value = pd.DataFrame()
        ingest_prediction(sample_prediction, db=mock_db)

        call_args = mock_db.client.load_table_from_dataframe.call_args
        df = call_args[0][0]
        prediction_hash = compute_prediction_hash(sample_prediction)
        expected_chain = compute_chain_hash(prediction_hash, HASH_SEED)
        assert df.iloc[0]["chain_hash"] == expected_chain

    def test_ingest_row_has_pending_status(self, sample_prediction, mock_db):
        ingest_prediction(sample_prediction, db=mock_db)
        call_args = mock_db.client.load_table_from_dataframe.call_args
        df = call_args[0][0]
        assert df.iloc[0]["resolution_status"] == "PENDING"

    def test_ingest_row_has_correct_pundit_id(self, sample_prediction, mock_db):
        ingest_prediction(sample_prediction, db=mock_db)
        call_args = mock_db.client.load_table_from_dataframe.call_args
        df = call_args[0][0]
        assert df.iloc[0]["pundit_id"] == "adam_schefter"


class TestIngestBatch:
    def test_batch_chains_correctly(self, sample_prediction, mock_db):
        mock_db.fetch_df.return_value = pd.DataFrame()

        pred2 = PunditPrediction(
            pundit_id="pat_mcafee",
            pundit_name="Pat McAfee",
            source_url="https://youtube.com/watch?v=456",
            raw_assertion_text="Josh Allen wins Super Bowl.",
            ingestion_timestamp=datetime(2025, 9, 2, 12, 0, 0, tzinfo=timezone.utc),
        )

        hashes = ingest_batch([sample_prediction, pred2], db=mock_db)
        assert len(hashes) == 2

        call_args = mock_db.client.load_table_from_dataframe.call_args
        df = call_args[0][0]
        assert len(df) == 2

        h0 = compute_prediction_hash(sample_prediction)
        chain0 = compute_chain_hash(h0, HASH_SEED)
        h1 = compute_prediction_hash(pred2)
        expected_chain1 = compute_chain_hash(h1, chain0)

        assert df.iloc[0]["chain_hash"] == chain0
        assert df.iloc[1]["chain_hash"] == expected_chain1

    def test_batch_returns_hashes_in_order(self, sample_prediction, mock_db):
        mock_db.fetch_df.return_value = pd.DataFrame()
        pred2 = PunditPrediction(
            pundit_id="mike_florio",
            pundit_name="Mike Florio",
            source_url="https://profootballtalk.nbcsports.com/123",
            raw_assertion_text="Aaron Rodgers retires.",
            ingestion_timestamp=datetime(2025, 9, 3, 12, 0, 0, tzinfo=timezone.utc),
        )
        hashes = ingest_batch([sample_prediction, pred2], db=mock_db)
        assert hashes[0] == compute_prediction_hash(sample_prediction)
        assert hashes[1] == compute_prediction_hash(pred2)

    def test_empty_batch_returns_empty(self, mock_db):
        hashes = ingest_batch([], db=mock_db)
        assert hashes == []
        mock_db.client.load_table_from_dataframe.assert_not_called()


class _LedgerClientStubDirectLoadRejectsJSON:
    """Reproduces the production #1132 bug: load_table_from_dataframe is the
    Parquet-backed path, and BigQuery rejects any destination table with a
    JSON-typed column (gold_layer.prediction_ledger.target_entity, migration
    022) with "400 Unsupported field type: JSON"."""

    def query(self, sql, **kwargs):
        job = MagicMock()
        job.result.return_value = None
        job.num_dml_affected_rows = 1
        return job

    def load_table_from_dataframe(self, *args, **kwargs):
        raise Exception(
            "400 Unsupported field type: JSON; reason: invalid, message: "
            "Unsupported field type: JSON"
        )


class _LedgerDBStubOldPath:
    """Simulates the pre-#1132-fix code: _append_to_ledger called
    db.client.load_table_from_dataframe directly, so append_dataframe_to_table
    was never reached. Calling it here raises to prove the point."""

    def __init__(self):
        self.client = _LedgerClientStubDirectLoadRejectsJSON()

    def fetch_df(self, query, **kwargs):
        return pd.DataFrame()  # empty sentinel -> HASH_SEED

    def append_dataframe_to_table(self, df, table_name):
        raise AssertionError(
            "old (pre-#1132) code path never called append_dataframe_to_table"
        )


class _LedgerDBStubRoutedFixed:
    """Simulates the post-#1132-fix code: db.append_dataframe_to_table is the
    only write path _append_to_ledger uses. A real DBManager routes JSON-
    bearing tables through load_table_from_json internally (covered by
    test_db_manager_table_ref.py); here we just capture that the ledger write
    goes through this method rather than the client directly."""

    def __init__(self):
        self.appended = []
        self.client = MagicMock()
        merge_job = MagicMock()
        merge_job.result.return_value = None
        merge_job.num_dml_affected_rows = 1
        self.client.query.return_value = merge_job

    def fetch_df(self, query, **kwargs):
        return pd.DataFrame()

    def append_dataframe_to_table(self, df, table_name):
        self.appended.append((table_name, df.copy()))

    def close(self):
        pass


class TestAppendToLedgerRoutesThroughDBManager:
    """Regression coverage for #1132.

    Same bug family as #1119/#1124/#1126: _append_to_ledger called
    db.client.load_table_from_dataframe directly, bypassing
    DBManager.append_dataframe_to_table's JSON-column handling. target_entity
    is a JSON-typed destination column on gold_layer.prediction_ledger
    (migration 022), so every real ingest 400'd with "Unsupported field type:
    JSON". Fix mirrors #1119/#1124/#1126 exactly: route through
    db.append_dataframe_to_table(df, table_ref) instead.
    """

    def test_direct_client_load_reproduces_production_400(self):
        """Sanity check: the old-path stub's client rejects the write with
        the exact error string seen in production logs."""
        db = _LedgerDBStubOldPath()
        df = pd.DataFrame([{"target_entity": '{"type": "player"}'}])
        with pytest.raises(Exception, match="Unsupported field type: JSON"):
            db.client.load_table_from_dataframe(df, "x")

    def test_ingest_batch_routes_through_append_dataframe_to_table(
        self, sample_prediction
    ):
        """ingest_batch -> _append_to_ledger must call
        db.append_dataframe_to_table, not db.client.load_table_from_dataframe
        directly — proven by using a stub where only the former succeeds."""
        db = _LedgerDBStubRoutedFixed()
        hashes = ingest_batch([sample_prediction], db=db)

        assert len(hashes) == 1
        assert len(db.appended) == 1
        table_ref, df = db.appended[0]
        assert table_ref.endswith("gold_layer.prediction_ledger")
        assert df.iloc[0]["pundit_id"] == sample_prediction.pundit_id

    def test_regression_guard_direct_client_call_raises(self, sample_prediction):
        """If _append_to_ledger regresses to calling
        db.client.load_table_from_dataframe directly again, ingest_batch
        raises AssertionError instead of silently succeeding — proving the
        fix is still wired up (mirrors the #1124 regression-test pattern for
        write_raw_utterances)."""
        db = _LedgerDBStubOldPath()
        with pytest.raises(AssertionError, match="append_dataframe_to_table"):
            ingest_batch([sample_prediction], db=db)


class TestVerifyChainIntegrity:
    def test_empty_ledger_is_verified(self, mock_db):
        mock_db.fetch_df.return_value = pd.DataFrame()
        result = verify_chain_integrity(db=mock_db)
        assert result["verified"] is True
        assert result["total_records"] == 0
        assert result["first_break_at"] is None

    def test_valid_chain_passes(self, mock_db):
        h0 = "a" * 64
        chain0 = compute_chain_hash(h0, HASH_SEED)
        h1 = "b" * 64
        chain1 = compute_chain_hash(h1, chain0)

        mock_db.fetch_df.return_value = pd.DataFrame(
            [
                {
                    "prediction_hash": h0,
                    "chain_hash": chain0,
                    "ingestion_timestamp": datetime(2025, 9, 1, tzinfo=timezone.utc),
                    "source_url": "https://example.com",
                    "pundit_id": "test",
                    "raw_assertion_text": "test",
                },
                {
                    "prediction_hash": h1,
                    "chain_hash": chain1,
                    "ingestion_timestamp": datetime(2025, 9, 2, tzinfo=timezone.utc),
                    "source_url": "https://example.com",
                    "pundit_id": "test",
                    "raw_assertion_text": "test2",
                },
            ]
        )
        result = verify_chain_integrity(db=mock_db)
        assert result["verified"] is True
        assert result["total_records"] == 2

    def test_tampered_record_fails(self, mock_db):
        h0 = "a" * 64

        mock_db.fetch_df.return_value = pd.DataFrame(
            [
                {
                    "prediction_hash": h0,
                    "chain_hash": "tampered" + "0" * 56,  # wrong
                    "ingestion_timestamp": datetime(2025, 9, 1, tzinfo=timezone.utc),
                    "source_url": "https://example.com",
                    "pundit_id": "test",
                    "raw_assertion_text": "test",
                },
            ]
        )
        result = verify_chain_integrity(db=mock_db)
        assert result["verified"] is False
        assert result["first_break_at"] == h0


# ---------------------------------------------------------------------------
# Concurrency regression tests (Issue #552)
# ---------------------------------------------------------------------------


class TestAtomicChainHead:
    """Unit tests for the optimistic-concurrency sentinel helpers."""

    def test_try_advance_returns_true_when_merge_affects_row(self):
        db = MagicMock()
        job = MagicMock()
        job.result.return_value = None
        job.num_dml_affected_rows = 1
        db.client.query.return_value = job

        won = _try_advance_chain_head(db, HASH_SEED, "a" * 64)
        assert won is True

    def test_try_advance_returns_false_when_merge_zero_rows(self):
        """Simulates a concurrent writer that already advanced the head."""
        db = MagicMock()
        job = MagicMock()
        job.result.return_value = None
        job.num_dml_affected_rows = 0
        db.client.query.return_value = job

        won = _try_advance_chain_head(db, HASH_SEED, "b" * 64)
        assert won is False

    def test_try_advance_returns_false_when_affected_rows_none(self):
        """Guard against BigQuery returning None for num_dml_affected_rows."""
        db = MagicMock()
        job = MagicMock()
        job.result.return_value = None
        job.num_dml_affected_rows = None
        db.client.query.return_value = job

        won = _try_advance_chain_head(db, HASH_SEED, "c" * 64)
        assert won is False

    def test_read_chain_head_returns_seed_when_empty(self):
        db = MagicMock()
        # _ensure_chain_head_table — DDL query
        ddl_job = MagicMock()
        ddl_job.result.return_value = None
        db.client.query.return_value = ddl_job
        # sentinel table is empty
        db.fetch_df.return_value = pd.DataFrame()

        result = _read_chain_head(db)
        assert result == HASH_SEED

    def test_read_chain_head_returns_stored_value(self):
        stored = "d" * 64
        db = MagicMock()
        ddl_job = MagicMock()
        ddl_job.result.return_value = None
        db.client.query.return_value = ddl_job
        db.fetch_df.return_value = pd.DataFrame({"chain_hash": [stored]})

        result = _read_chain_head(db)
        assert result == stored


class TestConcurrentIngestRaceCondition:
    """
    Regression test for Issue #552.

    Two threads call ingest_batch simultaneously with mocked BigQuery.
    The mock serialises MERGE attempts: only the first caller wins (returns
    num_dml_affected_rows=1); the second gets 0, retries, then gets 1.

    Assertions:
    - Both calls complete without exception.
    - The combined set of ingested rows forms a strictly linear chain
      (no branching, no duplicate chain_hash values).
    """

    def _build_pred(self, idx: int) -> PunditPrediction:
        return PunditPrediction(
            pundit_id=f"pundit_{idx}",
            pundit_name=f"Pundit {idx}",
            source_url=f"https://example.com/{idx}",
            raw_assertion_text=f"Claim number {idx}.",
            ingestion_timestamp=datetime(
                2025, 9, idx + 1, 12, 0, 0, tzinfo=timezone.utc
            ),
        )

    def test_concurrent_ingest_produces_linear_chain(self):
        """
        Simulate two concurrent ingest_batch calls racing on chain-head.

        Mock strategy:
          - Shared in-memory chain_head starts at HASH_SEED.
          - A threading.Lock serialises MERGE attempts.
          - First MERGE call within a lock succeeds (returns 1).
          - Second call within the same slot returns 0 (conflict).
          - After conflict the loser re-reads the updated head and retries.
        """
        chain_head_state = {"value": HASH_SEED}
        state_lock = threading.Lock()
        appended_rows: list[dict] = []
        append_lock = threading.Lock()

        def make_db_for_thread():
            db = MagicMock()

            def mock_query(sql, **kwargs):
                job = MagicMock()
                job.result.return_value = None

                # MERGE attempt — parse expected_hash and new_hash from SQL
                if "MERGE" in sql:
                    # Extract the two hashes embedded in the MERGE SQL.
                    # Format: AND T.chain_hash = '<expected>' ... SET chain_hash = '<new>'
                    import re

                    expected_match = re.search(r"T\.chain_hash = '([0-9a-f]*)'", sql)
                    new_match = re.search(r"SET chain_hash = '([0-9a-f]+)'", sql)
                    # Also handle the INSERT branch (first-ever row)
                    insert_match = re.search(r"VALUES \('HEAD', '([0-9a-f]+)'", sql)

                    expected = expected_match.group(1) if expected_match else HASH_SEED
                    new_val = (
                        new_match.group(1)
                        if new_match
                        else (insert_match.group(1) if insert_match else None)
                    )

                    with state_lock:
                        if chain_head_state["value"] == expected and new_val:
                            chain_head_state["value"] = new_val
                            job.num_dml_affected_rows = 1
                        else:
                            job.num_dml_affected_rows = 0
                else:
                    # DDL (CREATE TABLE IF NOT EXISTS) — always succeeds
                    job.num_dml_affected_rows = 0

                return job

            def mock_fetch_df(query, **kwargs):
                if "ledger_chain_head" in query:
                    with state_lock:
                        current = chain_head_state["value"]
                    if current == HASH_SEED:
                        return pd.DataFrame()
                    return pd.DataFrame({"chain_hash": [current]})
                # verify_chain_integrity path — not exercised here
                return pd.DataFrame()

            def mock_load(df, table_ref, job_config=None):
                with append_lock:
                    appended_rows.extend(df.to_dict("records"))
                load_job = MagicMock()
                load_job.result.return_value = None
                return load_job

            db.client.query = mock_query
            db.fetch_df = mock_fetch_df
            db.client.load_table_from_dataframe = mock_load
            # _append_to_ledger calls db.append_dataframe_to_table (#1132);
            # delegate to the same mock_load so appended_rows still captures
            # every write.
            db.append_dataframe_to_table = lambda df, table_ref: mock_load(
                df, table_ref
            )
            return db

        # Thread A ingests pred_0, Thread B ingests pred_1 concurrently.
        pred_a = self._build_pred(0)
        pred_b = self._build_pred(1)
        errors: list[Exception] = []

        def run_a():
            try:
                ingest_batch([pred_a], db=make_db_for_thread())
            except Exception as e:
                errors.append(e)

        def run_b():
            try:
                ingest_batch([pred_b], db=make_db_for_thread())
            except Exception as e:
                errors.append(e)

        t_a = threading.Thread(target=run_a)
        t_b = threading.Thread(target=run_b)
        t_a.start()
        t_b.start()
        t_a.join(timeout=30)
        t_b.join(timeout=30)

        assert not errors, f"Thread raised exception: {errors}"
        assert len(appended_rows) == 2, (
            f"Expected exactly 2 rows appended, got {len(appended_rows)}"
        )

        # Chain must be linear — no duplicate chain_hash values
        chain_hashes = [r["chain_hash"] for r in appended_rows]
        assert len(set(chain_hashes)) == 2, (
            "Duplicate chain_hash detected — chain branched under concurrent load"
        )

        # Verify each row's chain_hash is derivable from the previous
        # (we don't know the order so we check both orderings)
        h_a = appended_rows[0]["chain_hash"]
        h_b = appended_rows[1]["chain_hash"]
        pred_hash_a = appended_rows[0]["prediction_hash"]
        pred_hash_b = appended_rows[1]["prediction_hash"]

        # One of the two orderings must produce a valid chain from HASH_SEED
        chain_from_a = compute_chain_hash(pred_hash_a, HASH_SEED)
        chain_from_b = compute_chain_hash(pred_hash_b, HASH_SEED)

        if h_a == chain_from_a:
            # A was first; B must chain from A
            assert h_b == compute_chain_hash(pred_hash_b, h_a), (
                "Chain broken: row B does not chain from row A"
            )
        elif h_b == chain_from_b:
            # B was first; A must chain from B
            assert h_a == compute_chain_hash(pred_hash_a, h_b), (
                "Chain broken: row A does not chain from row B"
            )
        else:
            pytest.fail(
                "Neither row is a valid first link — chain is corrupt. "
                f"h_a={h_a[:16]}…  h_b={h_b[:16]}…"
            )


# ---------------------------------------------------------------------------
# Integration tests — require GCP_PROJECT_ID (skipped locally)
# ---------------------------------------------------------------------------

pytestmark_integration = pytest.mark.skipif(
    not os.environ.get("GCP_PROJECT_ID"),
    reason="GCP_PROJECT_ID not set — skipping BigQuery integration tests",
)


@pytest.mark.skipif(
    not os.environ.get("RUN_BQ_INTEGRATION"),
    reason="RUN_BQ_INTEGRATION not set — skipping live BigQuery integration tests (requires gold_layer dataset)",
)
class TestLedgerIntegration:
    """
    Writes a test prediction to the real BigQuery ledger and verifies it.
    Requires gold_layer dataset to exist (run scripts/run_bq_migrations.py first).
    Enable with: RUN_BQ_INTEGRATION=1 pytest tests/test_cryptographic_ledger.py
    """

    TEST_PUNDIT_ID = "_test_integration_agent"

    def test_ingest_and_verify(self):
        from src.db_manager import DBManager

        db = DBManager()
        prediction = PunditPrediction(
            pundit_id=self.TEST_PUNDIT_ID,
            pundit_name="Integration Test Agent",
            source_url="https://test.internal/integration-test",
            raw_assertion_text="This is an automated integration test record.",
            claim_category="player_performance",
            season_year=2025,
        )

        prediction_hash = ingest_prediction(prediction, db=db)
        assert len(prediction_hash) == 64

        result = verify_chain_integrity(db=db)
        assert result["verified"] is True
        db.close()
