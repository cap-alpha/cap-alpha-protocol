"""Unit tests for MicrobatchTrigger (SP18.5-2).

All tests use a mock DBManager so no BigQuery connection is needed.
"""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.microbatch_trigger import MicrobatchTrigger


def _make_db(known_rows=None):
    """Return a mock DBManager pre-loaded with known hash rows."""
    db = MagicMock()
    db.project_id = "test-project"
    db.dataset_id = "nfl_dead_money"

    if known_rows is None:
        known_rows = []
    db.fetch_df.return_value = (
        pd.DataFrame(known_rows, columns=["entity_key", "content_hash"])
        if known_rows
        else pd.DataFrame(columns=["entity_key", "content_hash"])
    )

    return db


class TestDetectChanges:
    def test_all_new_when_no_prior_hashes(self):
        db = _make_db(known_rows=[])
        trigger = MicrobatchTrigger(db, "test_ns")

        df = pd.DataFrame(
            [
                {"PlayerID": "1", "Name": "Alice", "Team": "KC"},
                {"PlayerID": "2", "Name": "Bob", "Team": "SF"},
            ]
        )
        changed = trigger.detect_changes(
            df, key_col="PlayerID", hash_cols=["Name", "Team"]
        )
        assert len(changed) == 2

    def test_unchanged_rows_excluded(self):
        df = pd.DataFrame(
            [
                {"PlayerID": "1", "Name": "Alice", "Team": "KC"},
            ]
        )
        # Pre-compute expected hash
        trigger_temp = MicrobatchTrigger.__new__(MicrobatchTrigger)
        trigger_temp.namespace = "test_ns"
        expected_hash = trigger_temp._hash_row(df.iloc[0], ["Name", "Team"])

        db = _make_db(known_rows=[{"entity_key": "1", "content_hash": expected_hash}])
        trigger = MicrobatchTrigger(db, "test_ns")

        changed = trigger.detect_changes(
            df, key_col="PlayerID", hash_cols=["Name", "Team"]
        )
        assert len(changed) == 0

    def test_changed_row_detected(self):
        db = _make_db(known_rows=[{"entity_key": "1", "content_hash": "old_hash_abc"}])
        trigger = MicrobatchTrigger(db, "test_ns")

        df = pd.DataFrame([{"PlayerID": "1", "Name": "Alice", "Team": "NE"}])
        changed = trigger.detect_changes(
            df, key_col="PlayerID", hash_cols=["Name", "Team"]
        )
        assert len(changed) == 1
        assert changed.iloc[0]["Team"] == "NE"

    def test_mixed_new_changed_unchanged(self):
        df_new = pd.DataFrame([{"PlayerID": "1", "Name": "Alice", "Team": "KC"}])
        trigger_temp = MicrobatchTrigger.__new__(MicrobatchTrigger)
        trigger_temp.namespace = "test_ns"
        hash_unchanged = trigger_temp._hash_row(df_new.iloc[0], ["Name", "Team"])

        known = [
            {"entity_key": "1", "content_hash": hash_unchanged},  # unchanged
            {"entity_key": "2", "content_hash": "stale_hash"},  # will change
        ]
        db = _make_db(known_rows=known)
        trigger = MicrobatchTrigger(db, "test_ns")

        current_df = pd.DataFrame(
            [
                {"PlayerID": "1", "Name": "Alice", "Team": "KC"},  # same — unchanged
                {"PlayerID": "2", "Name": "Bob", "Team": "DAL"},  # team changed
                {"PlayerID": "3", "Name": "Carol", "Team": "PHI"},  # new
            ]
        )
        changed = trigger.detect_changes(
            current_df, key_col="PlayerID", hash_cols=["Name", "Team"]
        )
        assert len(changed) == 2
        changed_keys = set(changed["PlayerID"].tolist())
        assert "2" in changed_keys
        assert "3" in changed_keys
        assert "1" not in changed_keys

    def test_empty_input_returns_empty(self):
        db = _make_db()
        trigger = MicrobatchTrigger(db, "test_ns")
        result = trigger.detect_changes(
            pd.DataFrame(), key_col="PlayerID", hash_cols=["Name"]
        )
        assert result.empty

    def test_content_hash_column_added(self):
        db = _make_db()
        trigger = MicrobatchTrigger(db, "test_ns")
        df = pd.DataFrame([{"PlayerID": "1", "Name": "X", "Team": "Y"}])
        changed = trigger.detect_changes(
            df, key_col="PlayerID", hash_cols=["Name", "Team"]
        )
        assert "_content_hash" in changed.columns
        assert len(changed.iloc[0]["_content_hash"]) == 64  # SHA-256 hex = 64 chars


class TestCommitHashes:
    def test_raises_without_content_hash_column(self):
        db = _make_db()
        trigger = MicrobatchTrigger(db, "test_ns")
        df = pd.DataFrame([{"PlayerID": "1", "Name": "Alice"}])
        with pytest.raises(ValueError, match="_content_hash"):
            trigger.commit_hashes(df, key_col="PlayerID")

    def test_empty_df_is_no_op(self):
        db = _make_db()
        trigger = MicrobatchTrigger(db, "test_ns")
        trigger.commit_hashes(pd.DataFrame(), key_col="PlayerID")
        db.append_dataframe_to_table.assert_not_called()
