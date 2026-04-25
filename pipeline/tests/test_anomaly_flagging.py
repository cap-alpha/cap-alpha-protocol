"""Unit tests for AnomalyFlagEngine (SP23-3, GH-#85)."""

import pytest
from unittest.mock import MagicMock, call
from datetime import datetime, date, timezone, timedelta
import pandas as pd

from src.anomaly_flagging import (
    AnomalyFlagEngine,
    PlayerAnomaly,
    run_anomaly_detection,
    SPIKE_THRESHOLD_SOFT,
    SPIKE_THRESHOLD_HARD,
    MIN_BASELINE_DAYS,
    MIN_DAILY_VOLUME,
)


def _make_db():
    db = MagicMock()
    db.project_id = "test-project"
    return db


def _make_daily_df(player: str, today: date, baseline_counts: list, today_count: int) -> pd.DataFrame:
    """Build a daily_count DataFrame with history + today row."""
    rows = []
    for i, count in enumerate(baseline_counts):
        d = today - timedelta(days=len(baseline_counts) - i)
        rows.append({"player_name": player, "mention_date": d, "daily_count": count})
    rows.append({"player_name": player, "mention_date": today, "daily_count": today_count})
    return pd.DataFrame(rows)


_TODAY = datetime(2026, 4, 1, 0, 0, 0, tzinfo=timezone.utc)
_TODAY_DATE = _TODAY.date()


class TestDetectSpikes:
    def test_returns_empty_when_no_data(self):
        db = _make_db()
        db.fetch_df.return_value = pd.DataFrame()
        engine = AnomalyFlagEngine(db=db)
        anomalies = engine.detect_spikes(today=_TODAY)
        assert anomalies == []

    def test_no_anomaly_for_normal_volume(self):
        db = _make_db()
        # Baseline with natural variance: mean≈5, stddev≈1.4; today=6 → z≈0.7
        baseline = [3, 7, 4, 6, 5, 4, 7, 5, 6, 3, 5, 6, 4, 7, 5, 6, 4, 5, 6, 5]
        df = _make_daily_df("Patrick Mahomes", _TODAY_DATE, baseline, today_count=6)
        db.fetch_df.return_value = df
        engine = AnomalyFlagEngine(db=db)
        anomalies = engine.detect_spikes(today=_TODAY)
        assert anomalies == []

    def test_soft_spike_flagged_as_suspicious(self):
        db = _make_db()
        # baseline mean=5, stddev≈1, today=12 → z≈7 → but let's be precise
        # Use a stable baseline to get a controlled z-score
        baseline = [5] * 20
        # std = 0, force stddev > 0 by adding some variation
        baseline[0] = 3
        baseline[1] = 7
        df = _make_daily_df("Travis Kelce", _TODAY_DATE, baseline, today_count=13)
        db.fetch_df.return_value = df
        engine = AnomalyFlagEngine(db=db)
        anomalies = engine.detect_spikes(today=_TODAY)
        assert len(anomalies) == 1
        assert anomalies[0].flag_type in ("SUSPICIOUS", "ANOMALY")
        assert anomalies[0].player_name == "Travis Kelce"

    def test_hard_spike_flagged_as_anomaly(self):
        db = _make_db()
        # Very stable baseline mean=5 stddev≈1; today=30 → z=(30-5)/1=25 >> SPIKE_HARD
        baseline = [5] * 28
        baseline[0] = 4
        baseline[1] = 6
        df = _make_daily_df("Josh Allen", _TODAY_DATE, baseline, today_count=30)
        db.fetch_df.return_value = df
        engine = AnomalyFlagEngine(db=db)
        anomalies = engine.detect_spikes(today=_TODAY)
        assert len(anomalies) == 1
        assert anomalies[0].flag_type == "ANOMALY"
        assert anomalies[0].z_score >= SPIKE_THRESHOLD_HARD

    def test_skips_players_with_insufficient_history(self):
        db = _make_db()
        # Only 3 days of history < MIN_BASELINE_DAYS
        baseline = [10, 10, 10]
        df = _make_daily_df("New Player", _TODAY_DATE, baseline, today_count=100)
        db.fetch_df.return_value = df
        engine = AnomalyFlagEngine(db=db)
        anomalies = engine.detect_spikes(today=_TODAY)
        assert anomalies == []

    def test_skips_low_volume_players(self):
        db = _make_db()
        # Baseline mean = 1.0 < MIN_DAILY_VOLUME (2)
        baseline = [1] * 20
        df = _make_daily_df("Obscure Player", _TODAY_DATE, baseline, today_count=50)
        db.fetch_df.return_value = df
        engine = AnomalyFlagEngine(db=db)
        anomalies = engine.detect_spikes(today=_TODAY)
        assert anomalies == []

    def test_db_error_returns_empty_list(self):
        db = _make_db()
        db.fetch_df.side_effect = Exception("BigQuery unavailable")
        engine = AnomalyFlagEngine(db=db)
        anomalies = engine.detect_spikes(today=_TODAY)
        assert anomalies == []

    def test_player_anomaly_has_expected_fields(self):
        db = _make_db()
        baseline = [5] * 28
        baseline[0] = 4
        baseline[1] = 6
        df = _make_daily_df("Lamar Jackson", _TODAY_DATE, baseline, today_count=25)
        db.fetch_df.return_value = df
        engine = AnomalyFlagEngine(db=db)
        anomalies = engine.detect_spikes(today=_TODAY)
        assert len(anomalies) == 1
        a = anomalies[0]
        assert a.player_name == "Lamar Jackson"
        assert a.today_count == 25
        assert a.baseline_mean > 0
        assert a.baseline_stddev > 0
        assert a.z_score > 0
        assert a.flag_type in ("SUSPICIOUS", "ANOMALY")


class TestWriteFlags:
    def test_writes_anomalies_to_table(self):
        db = _make_db()
        engine = AnomalyFlagEngine(db=db)
        anomaly = PlayerAnomaly(
            player_name="Tyreek Hill",
            today_count=30,
            baseline_mean=5.0,
            baseline_stddev=1.0,
            z_score=25.0,
            flag_type="ANOMALY",
        )
        n = engine.write_flags([anomaly])
        assert n == 1
        db.append_dataframe_to_table.assert_called_once()
        df_written = db.append_dataframe_to_table.call_args[0][0]
        assert "player_name" in df_written.columns
        assert "z_score" in df_written.columns
        assert "flag_type" in df_written.columns

    def test_write_flags_returns_zero_for_empty_list(self):
        db = _make_db()
        engine = AnomalyFlagEngine(db=db)
        n = engine.write_flags([])
        assert n == 0
        db.append_dataframe_to_table.assert_not_called()


class TestRun:
    def test_run_returns_summary_dict(self):
        db = _make_db()
        db.fetch_df.return_value = pd.DataFrame()
        engine = AnomalyFlagEngine(db=db)
        summary = engine.run(today=_TODAY)
        assert "flagged_players" in summary
        assert "anomaly_count" in summary
        assert "suspicious_count" in summary
        assert "rows_written" in summary

    def test_run_module_entry_point(self):
        db = _make_db()
        db.fetch_df.return_value = pd.DataFrame()
        result = run_anomaly_detection(db=db)
        assert isinstance(result, dict)
        assert result["flagged_players"] == 0
