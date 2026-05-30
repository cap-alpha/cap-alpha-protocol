"""
Phase 4 unit tests for resolution_engine.py silver_v2 writes (Issue #920).

Tests cover:
  - CORRECT resolution writes claim_state_history (close+open) AND entity_attribute_event
  - INCORRECT resolution writes claim_state_history but NOT entity_attribute_event
  - VOID resolution writes claim_state_history but NOT entity_attribute_event
  - DUAL_WRITE_LEGACY=false suppresses gold_layer writes but not silver_v2 writes
  - _write_claim_state_history no-ops gracefully when no silver_v2 claim exists
  - _write_entity_attribute_event no-ops gracefully when no silver_v2 claim/entity-link exists
"""

import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, call, patch

import pandas as pd
import pytest

from src.resolution_engine import (
    ResolutionResult,
    _write_claim_state_history,
    _write_entity_attribute_event,
    record_resolution,
)

FAKE_HASH = "b" * 64
FAKE_CLAIM_ID = "claim-" + "c" * 32
FAKE_ENTITY_ID = "entity-" + "e" * 28


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db_with_claim():
    """DB mock that returns a silver_v2 claim row on the first fetch_df call."""
    db = MagicMock()
    db.fetch_df.return_value = pd.DataFrame(
        [
            {
                "claim_id": FAKE_CLAIM_ID,
                "subject_metric": "mvp_odds",
                "resolution_window_start": datetime(2026, 2, 1, tzinfo=timezone.utc),
            }
        ]
    )
    return db


@pytest.fixture
def mock_db_with_claim_and_entity():
    """DB mock that returns claim+entity rows for entity_attribute_event tests."""
    db = MagicMock()
    db.fetch_df.return_value = pd.DataFrame(
        [
            {
                "claim_id": FAKE_CLAIM_ID,
                "subject_entity_id": FAKE_ENTITY_ID,
                "subject_metric": "mvp_odds",
                "resolution_window_start": datetime(2026, 2, 1, tzinfo=timezone.utc),
                "predicate_args": None,
            }
        ]
    )
    return db


@pytest.fixture
def mock_db_empty():
    """DB mock that returns empty DataFrame (no silver_v2 claim found)."""
    db = MagicMock()
    db.fetch_df.return_value = pd.DataFrame()
    return db


# ---------------------------------------------------------------------------
# _write_claim_state_history
# ---------------------------------------------------------------------------


class TestWriteClaimStateHistory:
    def test_noop_when_no_silver_v2_claim(self, mock_db_empty):
        """When no silver_v2 claim exists, no DB writes should occur."""
        with patch.dict(os.environ, {"GCP_PROJECT_ID": "test-project"}):
            _write_claim_state_history(
                project_id="test-project",
                prediction_hash=FAKE_HASH,
                resolution_status="CORRECT",
                resolved_at=datetime(2026, 2, 2, tzinfo=timezone.utc),
                brier_score=None,
                binary_correct=True,
                db=mock_db_empty,
            )
        # fetch_df was called once for the lookup; execute was never called
        assert mock_db_empty.fetch_df.call_count == 1
        mock_db_empty.execute.assert_not_called()

    def test_closes_open_row(self, mock_db_with_claim):
        """First execute call must be an UPDATE to close the open row."""
        resolved_at = datetime(2026, 2, 2, tzinfo=timezone.utc)
        with patch.dict(os.environ, {"GCP_PROJECT_ID": "test-project"}):
            _write_claim_state_history(
                project_id="test-project",
                prediction_hash=FAKE_HASH,
                resolution_status="CORRECT",
                resolved_at=resolved_at,
                brier_score=0.04,
                binary_correct=True,
                db=mock_db_with_claim,
            )
        first_call = mock_db_with_claim.execute.call_args_list[0]
        close_sql = first_call[0][0]
        assert "UPDATE" in close_sql
        assert "effective_to" in close_sql
        assert "effective_to IS NULL" in close_sql

    def test_inserts_new_open_row(self, mock_db_with_claim):
        """Second execute call must INSERT a new open history row."""
        resolved_at = datetime(2026, 2, 2, tzinfo=timezone.utc)
        with patch.dict(os.environ, {"GCP_PROJECT_ID": "test-project"}):
            _write_claim_state_history(
                project_id="test-project",
                prediction_hash=FAKE_HASH,
                resolution_status="INCORRECT",
                resolved_at=resolved_at,
                brier_score=0.81,
                binary_correct=False,
                db=mock_db_with_claim,
            )
        second_call = mock_db_with_claim.execute.call_args_list[1]
        insert_sql = second_call[0][0]
        assert "INSERT" in insert_sql
        assert "claim_state_history" in insert_sql
        # Verify the state param is INCORRECT
        params = {p.name: p.value for p in second_call[1]["query_parameters"]}
        assert params["state"] == "INCORRECT"
        assert params["claim_id"] == FAKE_CLAIM_ID

    def test_two_execute_calls_total(self, mock_db_with_claim):
        """Exactly 2 execute calls: UPDATE close + INSERT open."""
        with patch.dict(os.environ, {"GCP_PROJECT_ID": "test-project"}):
            _write_claim_state_history(
                project_id="test-project",
                prediction_hash=FAKE_HASH,
                resolution_status="VOID",
                resolved_at=datetime(2026, 2, 2, tzinfo=timezone.utc),
                brier_score=None,
                binary_correct=None,
                db=mock_db_with_claim,
            )
        assert mock_db_with_claim.execute.call_count == 2

    def test_error_does_not_propagate(self, mock_db_with_claim):
        """Errors in the silver_v2 write must be swallowed (best-effort)."""
        mock_db_with_claim.execute.side_effect = Exception("BQ timeout")
        resolved_at = datetime(2026, 2, 2, tzinfo=timezone.utc)
        # Should NOT raise
        _write_claim_state_history(
            project_id="test-project",
            prediction_hash=FAKE_HASH,
            resolution_status="CORRECT",
            resolved_at=resolved_at,
            brier_score=None,
            binary_correct=True,
            db=mock_db_with_claim,
        )


# ---------------------------------------------------------------------------
# _write_entity_attribute_event
# ---------------------------------------------------------------------------


class TestWriteEntityAttributeEvent:
    def test_noop_when_no_claim_or_entity_link(self, mock_db_empty):
        """When no silver_v2 claim+entity-link exists, no writes occur."""
        with patch.dict(os.environ, {"GCP_PROJECT_ID": "test-project"}):
            _write_entity_attribute_event(
                project_id="test-project",
                prediction_hash=FAKE_HASH,
                weighted_score=1.5,
                db=mock_db_empty,
            )
        assert mock_db_empty.fetch_df.call_count == 1
        mock_db_empty.execute.assert_not_called()

    def test_inserts_entity_attribute_event(self, mock_db_with_claim_and_entity):
        """One INSERT per subject entity with source_claim_id and evidence_type."""
        with patch.dict(os.environ, {"GCP_PROJECT_ID": "test-project"}):
            _write_entity_attribute_event(
                project_id="test-project",
                prediction_hash=FAKE_HASH,
                weighted_score=1.5,
                db=mock_db_with_claim_and_entity,
            )
        assert mock_db_with_claim_and_entity.execute.call_count == 1
        insert_sql = mock_db_with_claim_and_entity.execute.call_args[0][0]
        assert "INSERT" in insert_sql
        assert "entity_attribute_event" in insert_sql
        assert "resolved_prediction" in insert_sql
        assert "source_claim_id" in insert_sql

    def test_source_claim_id_set_correctly(self, mock_db_with_claim_and_entity):
        """source_claim_id in the INSERT params must equal the claim_id from the lookup."""
        with patch.dict(os.environ, {"GCP_PROJECT_ID": "test-project"}):
            _write_entity_attribute_event(
                project_id="test-project",
                prediction_hash=FAKE_HASH,
                weighted_score=0.9,
                db=mock_db_with_claim_and_entity,
            )
        params = {
            p.name: p.value
            for p in mock_db_with_claim_and_entity.execute.call_args[1][
                "query_parameters"
            ]
        }
        assert params["source_claim_id"] == FAKE_CLAIM_ID
        assert params["entity_id"] == FAKE_ENTITY_ID

    def test_multiple_subject_entities_each_get_an_event(self):
        """Two subject entities linked to one claim produce two INSERT calls."""
        db = MagicMock()
        db.fetch_df.return_value = pd.DataFrame(
            [
                {
                    "claim_id": FAKE_CLAIM_ID,
                    "subject_entity_id": "entity-aaa",
                    "subject_metric": "mvp",
                    "resolution_window_start": None,
                    "predicate_args": None,
                },
                {
                    "claim_id": FAKE_CLAIM_ID,
                    "subject_entity_id": "entity-bbb",
                    "subject_metric": "mvp",
                    "resolution_window_start": None,
                    "predicate_args": None,
                },
            ]
        )
        with patch.dict(os.environ, {"GCP_PROJECT_ID": "test-project"}):
            _write_entity_attribute_event(
                project_id="test-project",
                prediction_hash=FAKE_HASH,
                weighted_score=1.0,
                db=db,
            )
        assert db.execute.call_count == 2

    def test_error_does_not_propagate(self, mock_db_with_claim_and_entity):
        """Errors in entity_attribute_event write must be swallowed."""
        mock_db_with_claim_and_entity.execute.side_effect = Exception("BQ error")
        _write_entity_attribute_event(
            project_id="test-project",
            prediction_hash=FAKE_HASH,
            weighted_score=1.0,
            db=mock_db_with_claim_and_entity,
        )


# ---------------------------------------------------------------------------
# record_resolution — integration of silver_v2 writes
# ---------------------------------------------------------------------------


class TestRecordResolutionSilverV2:
    """
    Tests for the silver_v2 write path inside record_resolution.

    DUAL_WRITE_LEGACY=false is used here to keep execute call-count assertions
    clean: we only count calls from the silver_v2 path, not the legacy MERGE.
    """

    @pytest.fixture
    def mock_db_v2(self):
        """DB mock that simulates: legacy writes off, silver_v2 claim found."""
        db = MagicMock()
        # First fetch_df: claim lookup in _write_claim_state_history
        # Subsequent fetch_df calls (e.g. _write_entity_attribute_event): claim+entity
        claim_row = pd.DataFrame(
            [
                {
                    "claim_id": FAKE_CLAIM_ID,
                    "subject_metric": "mvp_odds",
                    "resolution_window_start": datetime(
                        2026, 2, 1, tzinfo=timezone.utc
                    ),
                }
            ]
        )
        claim_entity_row = pd.DataFrame(
            [
                {
                    "claim_id": FAKE_CLAIM_ID,
                    "subject_entity_id": FAKE_ENTITY_ID,
                    "subject_metric": "mvp_odds",
                    "resolution_window_start": datetime(
                        2026, 2, 1, tzinfo=timezone.utc
                    ),
                    "predicate_args": None,
                }
            ]
        )
        db.fetch_df.side_effect = [claim_row, claim_entity_row]
        return db

    def test_correct_writes_claim_state_history_and_entity_event(self, mock_db_v2):
        """CORRECT: state history updated (2 executes) + entity event (1 execute) = 3 total."""
        result = ResolutionResult(
            prediction_hash=FAKE_HASH,
            resolution_status="CORRECT",
            resolver="auto",
            binary_correct=True,
            timeliness_weight=1.25,
            weighted_score=1.25,
        )
        with patch.dict(
            os.environ,
            {"GCP_PROJECT_ID": "test-project", "DUAL_WRITE_LEGACY": "false"},
        ):
            record_resolution(result, db=mock_db_v2)
        # 2 executes for claim_state_history (UPDATE close + INSERT open)
        # + 1 execute for entity_attribute_event
        assert mock_db_v2.execute.call_count == 3

    def test_incorrect_writes_state_history_but_not_entity_event(self):
        """INCORRECT: state history updated but entity_attribute_event NOT written."""
        db = MagicMock()
        db.fetch_df.return_value = pd.DataFrame(
            [
                {
                    "claim_id": FAKE_CLAIM_ID,
                    "subject_metric": "draft_pick",
                    "resolution_window_start": None,
                }
            ]
        )
        result = ResolutionResult(
            prediction_hash=FAKE_HASH,
            resolution_status="INCORRECT",
            resolver="auto",
            binary_correct=False,
        )
        with patch.dict(
            os.environ,
            {"GCP_PROJECT_ID": "test-project", "DUAL_WRITE_LEGACY": "false"},
        ):
            record_resolution(result, db=db)
        # Only 2 executes: UPDATE close + INSERT open in claim_state_history
        # entity_attribute_event must NOT be called for INCORRECT
        assert db.execute.call_count == 2
        all_sql = " ".join(c[0][0] for c in db.execute.call_args_list)
        assert "entity_attribute_event" not in all_sql

    def test_void_writes_state_history_but_not_entity_event(self):
        """VOID: state history updated but entity_attribute_event NOT written."""
        db = MagicMock()
        db.fetch_df.return_value = pd.DataFrame(
            [
                {
                    "claim_id": FAKE_CLAIM_ID,
                    "subject_metric": "playoff_bid",
                    "resolution_window_start": None,
                }
            ]
        )
        result = ResolutionResult(
            prediction_hash=FAKE_HASH,
            resolution_status="VOID",
            resolver="manual",
            outcome_notes="player_retired_mid_season",
        )
        with patch.dict(
            os.environ,
            {"GCP_PROJECT_ID": "test-project", "DUAL_WRITE_LEGACY": "false"},
        ):
            record_resolution(result, db=db)
        assert db.execute.call_count == 2
        all_sql = " ".join(c[0][0] for c in db.execute.call_args_list)
        assert "entity_attribute_event" not in all_sql

    def test_dual_write_legacy_true_adds_gold_layer_writes(self):
        """DUAL_WRITE_LEGACY=true: gold_layer MERGE + ledger UPDATE are also executed."""
        db = MagicMock()
        db.fetch_df.return_value = (
            pd.DataFrame()
        )  # no silver_v2 claim → state history no-op
        result = ResolutionResult(
            prediction_hash=FAKE_HASH,
            resolution_status="CORRECT",
            resolver="auto",
            binary_correct=True,
        )
        with patch.dict(
            os.environ,
            {"GCP_PROJECT_ID": "test-project", "DUAL_WRITE_LEGACY": "true"},
        ):
            record_resolution(result, db=db)
        # 2 legacy writes (MERGE + ledger UPDATE) + 0 silver_v2 (no claim found)
        assert db.execute.call_count == 2
        merge_sql = db.execute.call_args_list[0][0][0]
        ledger_sql = db.execute.call_args_list[1][0][0]
        assert "MERGE" in merge_sql
        assert "prediction_resolutions" in merge_sql
        assert "UPDATE" in ledger_sql
        assert "prediction_ledger" in ledger_sql

    def test_dual_write_legacy_false_suppresses_gold_layer(self):
        """DUAL_WRITE_LEGACY=false: no MERGE into prediction_resolutions."""
        db = MagicMock()
        db.fetch_df.return_value = pd.DataFrame()  # no silver_v2 claim
        result = ResolutionResult(
            prediction_hash=FAKE_HASH,
            resolution_status="INCORRECT",
            resolver="auto",
            binary_correct=False,
        )
        with patch.dict(
            os.environ,
            {"GCP_PROJECT_ID": "test-project", "DUAL_WRITE_LEGACY": "false"},
        ):
            record_resolution(result, db=db)
        # No silver_v2 claim found → no execute calls at all
        db.execute.assert_not_called()
        all_sql = " ".join(c[0][0] for c in db.execute.call_args_list)
        assert "prediction_resolutions" not in all_sql
