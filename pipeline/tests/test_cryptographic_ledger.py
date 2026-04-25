"""
Tests for the Cryptographic Hashing Pipeline (Issue #111).

Unit tests run without BigQuery. Integration tests require GCP_PROJECT_ID.
"""

import hashlib
import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, call, patch

import pandas as pd
import pytest
from src.cryptographic_ledger import (HASH_SEED, PunditPrediction,
                                      _canonical_payload, compute_chain_hash,
                                      compute_prediction_hash,
                                      get_latest_chain_hash, ingest_batch,
                                      ingest_prediction,
                                      verify_chain_integrity)

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


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.fetch_df.return_value = pd.DataFrame()  # empty ledger by default
    # Simulate BQ load job (used by _append_to_ledger via db.client)
    mock_job = MagicMock()
    mock_job.result.return_value = None
    db.client.load_table_from_dataframe.return_value = mock_job
    return db


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
        mock_db.fetch_df.return_value = pd.DataFrame()  # empty ledger
        ingest_prediction(sample_prediction, db=mock_db)

        call_args = mock_db.client.load_table_from_dataframe.call_args
        df = call_args[0][0]
        # chain_hash for first record = sha256(prediction_hash + "")
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

        # Verify chain: row[1].chain_hash = sha256(row[1].prediction_hash + row[0].chain_hash)
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


class TestVerifyChainIntegrity:
    def test_empty_ledger_is_verified(self, mock_db):
        mock_db.fetch_df.return_value = pd.DataFrame()
        result = verify_chain_integrity(db=mock_db)
        assert result["verified"] is True
        assert result["total_records"] == 0
        assert result["first_break_at"] is None

    def test_valid_chain_passes(self, mock_db):
        # Build a valid 2-record chain
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
        chain0 = compute_chain_hash(h0, HASH_SEED)

        # Tamper: wrong chain_hash on record 0
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

        # Verify the chain is still intact after our write
        result = verify_chain_integrity(db=db)
        assert result["verified"] is True
        db.close()
