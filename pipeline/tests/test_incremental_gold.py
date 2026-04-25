"""Unit tests for IncrementalGoldRefresh (SP18.5-3)."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, call, patch

import pandas as pd
import pytest


def _make_db(watermark_ts=None, changed_keys=None, mart_count=100):
    db = MagicMock()
    db.project_id = "test-project"
    db.dataset_id = "nfl_dead_money"

    # Watermark query returns a row or None
    wm_row = (watermark_ts,) if watermark_ts else None

    # changed keys query returns a DataFrame
    if changed_keys is None:
        changed_df = pd.DataFrame(columns=["player_name", "year", "team"])
    else:
        changed_df = pd.DataFrame(changed_keys, columns=["player_name", "year", "team"])

    # Count query
    count_row = (mart_count,)

    # We need execute to return different things for different queries.
    # Simplest: sequence of returns.
    proxy_wm = MagicMock()
    proxy_wm.fetchone.return_value = wm_row

    proxy_count = MagicMock()
    proxy_count.fetchone.return_value = count_row

    # execute() side effect: return wm proxy first, then count proxy for subsequent calls
    execute_returns = [proxy_wm, proxy_count, MagicMock(), MagicMock(), MagicMock()]
    db.execute.side_effect = execute_returns

    db.fetch_df.return_value = changed_df

    return db


class TestIncrementalGoldRefresh:
    def _make_trigger(self, db):
        from src.incremental_gold import IncrementalGoldRefresh

        # Patch _ensure_watermark_table to avoid DDL calls
        with patch.object(IncrementalGoldRefresh, "_ensure_watermark_table"):
            trigger = IncrementalGoldRefresh(db)
        return trigger

    def test_no_changes_skips_rebuild(self):
        db = _make_db(
            watermark_ts=datetime(2026, 4, 1, tzinfo=timezone.utc),
            changed_keys=[],
        )
        trigger = self._make_trigger(db)
        result = trigger.refresh()
        assert result["build_type"] == "incremental"
        assert result["rows_affected"] == 0
        assert result["changed_keys"] == []

    def test_changed_keys_triggers_rebuild(self):
        changed = [("Patrick Mahomes", 2025, "KC"), ("Josh Allen", 2025, "BUF")]
        db = _make_db(
            watermark_ts=datetime(2026, 4, 1, tzinfo=timezone.utc),
            changed_keys=changed,
            mart_count=50,
        )
        trigger = self._make_trigger(db)

        with patch.object(
            trigger, "_rebuild_keys", return_value=42
        ) as mock_rebuild, patch.object(trigger, "_upsert_watermark") as mock_wm:
            result = trigger.refresh()

        mock_rebuild.assert_called_once_with(changed)
        mock_wm.assert_called_once_with("incremental", 42)
        assert result["build_type"] == "incremental"
        assert result["rows_affected"] == 42
        assert result["changed_keys"] == changed

    def test_full_refresh_ignores_watermark(self):
        db = _make_db()
        trigger = self._make_trigger(db)

        with patch.object(trigger, "_full_rebuild") as mock_full, patch.object(
            trigger, "_count_mart", return_value=999
        ) as mock_count, patch.object(trigger, "_upsert_watermark") as mock_wm:
            result = trigger.refresh(full_refresh=True)

        mock_full.assert_called_once()
        mock_wm.assert_called_once_with("full", 999)
        assert result["build_type"] == "full"
        assert result["rows_affected"] == 999

    def test_missing_watermark_returns_epoch(self):
        db = _make_db(watermark_ts=None, changed_keys=[])
        trigger = self._make_trigger(db)

        loaded = trigger._load_watermark()
        assert loaded.year == 1970

    def test_find_changed_keys_returns_list_of_tuples(self):
        changed = [("Alice Smith", 2025, "KC")]
        db = _make_db(changed_keys=changed)
        trigger = self._make_trigger(db)

        since = datetime(2026, 4, 1, tzinfo=timezone.utc)
        keys = trigger._find_changed_keys(since=since)
        assert len(keys) == 1
        assert keys[0] == ("Alice Smith", 2025, "KC")

    def test_find_changed_keys_returns_empty_on_error(self):
        db = _make_db(changed_keys=[])
        db.fetch_df.side_effect = Exception("BQ unavailable")
        trigger = self._make_trigger(db)

        keys = trigger._find_changed_keys(since=None)
        assert keys == []
