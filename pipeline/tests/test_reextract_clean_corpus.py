"""
Unit tests for pipeline/scripts/reextract_clean_corpus.py (Issue #999).

These tests exercise:
  - Constants are correct (source IDs + pundit IDs match #998/#995 definitions)
  - _in_literal() produces safe SQL literals
  - Dry-run path calls count queries but no DELETE queries
  - The step functions handle count-query failures gracefully (warning, not crash)
"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pandas as pd
import pytest

# Make pipeline scripts importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Import the module under test
import importlib.util

_SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent / "scripts" / "reextract_clean_corpus.py"
)
_spec = importlib.util.spec_from_file_location("reextract_clean_corpus", _SCRIPT_PATH)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

# Pull names from the loaded module
CONTAMINATED_SOURCE_IDS = _mod.CONTAMINATED_SOURCE_IDS
CONTAMINATED_PUNDIT_IDS = _mod.CONTAMINATED_PUNDIT_IDS
_in_literal = _mod._in_literal
step1_delete_contaminated_predictions = _mod.step1_delete_contaminated_predictions
step2_reset_processed_hashes = _mod.step2_reset_processed_hashes


# ---------------------------------------------------------------------------
# Constant correctness
# ---------------------------------------------------------------------------


class TestConstants:
    def test_contaminated_source_ids_match_pr998_sources(self):
        """Source IDs must match the media_sources.yaml IDs for the affected sources."""
        assert "pft_nbc" in CONTAMINATED_SOURCE_IDS, (
            "pft_nbc is the media_sources.yaml id for ProFootballTalk — must be present"
        )
        assert "theathletic_nfl" in CONTAMINATED_SOURCE_IDS, (
            "theathletic_nfl is the media_sources.yaml id for The Athletic — must be present"
        )

    def test_contaminated_pundit_ids_match_pr995_removed_buckets(self):
        """Pundit IDs must match the staff buckets removed in PR #995."""
        assert "pft_staff" in CONTAMINATED_PUNDIT_IDS
        assert "athletic_nfl_staff" in CONTAMINATED_PUNDIT_IDS

    def test_named_pundits_are_not_in_contaminated_list(self):
        """Named individual pundits (mike_florio, dianna_russini) must NOT be deleted."""
        for individual in [
            "mike_florio",
            "josh_alper",
            "dianna_russini",
            "jeff_howe",
            "charean_williams",
            "myles_simmons",
            "michael_david_smith",
        ]:
            assert individual not in CONTAMINATED_PUNDIT_IDS, (
                f"{individual!r} is an individual pundit — should not be deleted"
            )


# ---------------------------------------------------------------------------
# _in_literal helper
# ---------------------------------------------------------------------------


class TestInLiteral:
    def test_single_value(self):
        assert _in_literal(("foo",)) == "('foo')"

    def test_two_values(self):
        result = _in_literal(("pft_staff", "athletic_nfl_staff"))
        assert result == "('pft_staff', 'athletic_nfl_staff')"

    def test_values_are_single_quoted(self):
        result = _in_literal(("pft_nbc", "theathletic_nfl"))
        assert "'pft_nbc'" in result
        assert "'theathletic_nfl'" in result

    def test_no_double_quotes(self):
        result = _in_literal(("a", "b"))
        assert '"' not in result


# ---------------------------------------------------------------------------
# Step 1 — dry-run
# ---------------------------------------------------------------------------


class TestStep1DryRun:
    def _make_db(self, count: int = 0):
        """Return a mock DBManager that returns ``count`` for COUNT(*) queries."""
        db = MagicMock()
        db.fetch_df.return_value = pd.DataFrame([[count]])
        return db

    def test_dry_run_does_not_call_execute(self):
        """execute() (DELETE) must never be called during a dry-run."""
        db = self._make_db(count=5)
        step1_delete_contaminated_predictions(db, project_id=None, dry_run=True)
        db.execute.assert_not_called()

    def test_dry_run_returns_ledger_count(self):
        db = self._make_db(count=42)
        result = step1_delete_contaminated_predictions(
            db, project_id=None, dry_run=True
        )
        from scripts.reextract_clean_corpus import _LEDGER_TABLE

        assert result[_LEDGER_TABLE] == 42

    def test_dry_run_tolerates_count_failure(self):
        """A count-query failure should warn (not raise) and return -1."""
        db = MagicMock()
        db.fetch_df.side_effect = Exception("table not found")
        result = step1_delete_contaminated_predictions(
            db, project_id=None, dry_run=True
        )
        # All counts should be -1 (or missing) — no crash
        for v in result.values():
            assert v == -1


# ---------------------------------------------------------------------------
# Step 2 — dry-run
# ---------------------------------------------------------------------------


class TestStep2DryRun:
    def _make_db(self, count: int = 0):
        db = MagicMock()
        db.fetch_df.return_value = pd.DataFrame([[count]])
        return db

    def test_dry_run_does_not_call_execute(self):
        db = self._make_db(count=10)
        step2_reset_processed_hashes(db, project_id=None, dry_run=True)
        db.execute.assert_not_called()

    def test_dry_run_returns_count(self):
        db = self._make_db(count=7)
        result = step2_reset_processed_hashes(db, project_id=None, dry_run=True)
        from scripts.reextract_clean_corpus import _PROCESSED_HASHES_TABLE

        assert result[_PROCESSED_HASHES_TABLE] == 7

    def test_dry_run_tolerates_count_failure(self):
        db = MagicMock()
        db.fetch_df.side_effect = Exception("no such table")
        result = step2_reset_processed_hashes(db, project_id=None, dry_run=True)
        for v in result.values():
            assert v == -1


# ---------------------------------------------------------------------------
# Step 1 — live delete path
# ---------------------------------------------------------------------------


class TestStep1LiveDelete:
    def _make_db(self, count: int = 5):
        db = MagicMock()
        db.fetch_df.return_value = pd.DataFrame([[count]])
        mock_result = MagicMock()
        mock_result.job.num_dml_affected_rows = count
        db.execute.return_value = mock_result
        return db

    def test_live_run_calls_delete_for_ledger(self):
        db = self._make_db(count=3)
        step1_delete_contaminated_predictions(db, project_id=None, dry_run=False)
        # execute() should have been called (for deletes)
        assert db.execute.call_count >= 1

    def test_live_delete_queries_use_pundit_ids(self):
        """The DELETE SQL must reference the contaminated pundit IDs."""
        db = self._make_db(count=1)
        step1_delete_contaminated_predictions(db, project_id=None, dry_run=False)
        all_queries = [str(c) for c in db.execute.call_args_list]
        combined = " ".join(all_queries)
        assert "pft_staff" in combined
        assert "athletic_nfl_staff" in combined

    def test_live_delete_uses_source_doc_id_join_for_utterances(self):
        """raw_utterance deletions must JOIN through source_doc_id, not pundit_id directly."""
        db = self._make_db(count=1)
        step1_delete_contaminated_predictions(db, project_id=None, dry_run=False)
        all_queries = [
            str(c.args[0]) if c.args else "" for c in db.execute.call_args_list
        ]
        utterance_query = next(
            (q for q in all_queries if "raw_utterance" in q or "source_doc_id" in q), ""
        )
        assert "source_doc_id" in utterance_query, (
            "raw_utterance DELETE must filter via source_doc_id (not a direct pundit_id column)"
        )


# ---------------------------------------------------------------------------
# Step 2 — live delete path
# ---------------------------------------------------------------------------


class TestStep2LiveDelete:
    def _make_db(self, count: int = 5):
        db = MagicMock()
        db.fetch_df.return_value = pd.DataFrame([[count]])
        mock_result = MagicMock()
        mock_result.job.num_dml_affected_rows = count
        db.execute.return_value = mock_result
        return db

    def test_live_run_calls_delete(self):
        db = self._make_db(count=4)
        step2_reset_processed_hashes(db, project_id=None, dry_run=False)
        assert db.execute.call_count >= 1

    def test_live_delete_uses_source_id_subquery(self):
        """Hash deletion must filter by source_id via a subquery, not directly."""
        db = self._make_db(count=2)
        step2_reset_processed_hashes(db, project_id=None, dry_run=False)
        all_queries = [
            str(c.args[0]) if c.args else "" for c in db.execute.call_args_list
        ]
        combined = " ".join(all_queries)
        assert "pft_nbc" in combined
        assert "theathletic_nfl" in combined
        assert "source_id" in combined

    def test_live_delete_does_not_touch_other_sources(self):
        """The DELETE must be scoped to the two contaminated source IDs only."""
        db = self._make_db(count=2)
        step2_reset_processed_hashes(db, project_id=None, dry_run=False)
        all_queries = [
            str(c.args[0]) if c.args else "" for c in db.execute.call_args_list
        ]
        combined = " ".join(all_queries)
        # Should NOT reference other sources
        for other_source in ["espn_nfl", "pat_mcafee_show", "dan_patrick_show"]:
            assert other_source not in combined, (
                f"DELETE query must not reference unrelated source {other_source!r}"
            )
