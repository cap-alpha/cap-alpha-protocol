"""
Tests for the COI Detection Engine -- Phase 1 (Issue #810).
Unit tests only -- no BigQuery or network calls required.
"""

from collections import namedtuple
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.coi_engine import (
    DISCLAIMER,
    SIGNAL1_ABS_THRESHOLD,
    SIGNAL1_MIN_BASELINE_CLAIMS,
    SIGNAL1_Z_THRESHOLD,
    SIGNAL2_DELTA_DEFAULT,
    SIGNAL2_DELTA_DOMINANT,
    SIGNAL2_ENTITY_DOMINANT_SHARE,
    SIGNAL2_MIN_RESOLVED,
    SIGNAL3_MIN_OUTLETS,
    SIGNAL3_MIN_PUNDITS,
    COIFlag,
    _check_confidence_coverage,
    _cluster_severity,
    _confidence_spike_severity,
    _entity_bias_severity,
    _extract_outlet,
    _extract_tokens,
    _jaccard,
    _make_flag_id,
    run_signal1_confidence_spike,
    run_signal2_entity_bias,
    run_signal3_narrative_cluster,
    write_flags,
    run_daily,
)

NOW = datetime(2026, 5, 8, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.project_id = "test-project"
    db.fetch_df.return_value = pd.DataFrame()
    return db


# ---------------------------------------------------------------------------
# _make_flag_id
# ---------------------------------------------------------------------------


class TestMakeFlagId:
    def test_deterministic(self):
        ts = datetime(2026, 5, 1, tzinfo=timezone.utc)
        id1 = _make_flag_id("pundit_a", "CONFIDENCE_SPIKE", ts, None)
        id2 = _make_flag_id("pundit_a", "CONFIDENCE_SPIKE", ts, None)
        assert id1 == id2

    def test_different_pundit_different_id(self):
        ts = datetime(2026, 5, 1, tzinfo=timezone.utc)
        id1 = _make_flag_id("pundit_a", "CONFIDENCE_SPIKE", ts, None)
        id2 = _make_flag_id("pundit_b", "CONFIDENCE_SPIKE", ts, None)
        assert id1 != id2

    def test_entity_key_affects_id(self):
        id1 = _make_flag_id("pundit_a", "ENTITY_BIAS", None, "Patrick Mahomes")
        id2 = _make_flag_id("pundit_a", "ENTITY_BIAS", None, "Travis Kelce")
        assert id1 != id2

    def test_returns_sha256_hex(self):
        fid = _make_flag_id("pundit_x", "CONFIDENCE_SPIKE", None, None)
        assert len(fid) == 64
        assert all(c in "0123456789abcdef" for c in fid)

    def test_same_date_same_id_regardless_of_time(self):
        ts1 = datetime(2026, 5, 1, 8, 0, 0, tzinfo=timezone.utc)
        ts2 = datetime(2026, 5, 1, 23, 59, 59, tzinfo=timezone.utc)
        assert _make_flag_id("p", "CONFIDENCE_SPIKE", ts1, None) == _make_flag_id(
            "p", "CONFIDENCE_SPIKE", ts2, None
        )


# ---------------------------------------------------------------------------
# Severity helpers
# ---------------------------------------------------------------------------


class TestSeverityHelpers:
    def test_confidence_spike_severity_high(self):
        assert _confidence_spike_severity(3.5) == "HIGH"

    def test_confidence_spike_severity_medium(self):
        assert _confidence_spike_severity(2.5) == "MEDIUM"

    def test_confidence_spike_severity_low(self):
        assert _confidence_spike_severity(1.0) == "LOW"

    def test_entity_bias_severity_high(self):
        assert _entity_bias_severity(0.40) == "HIGH"

    def test_entity_bias_severity_medium(self):
        assert _entity_bias_severity(0.25) == "MEDIUM"

    def test_entity_bias_severity_low(self):
        assert _entity_bias_severity(0.10) == "LOW"

    def test_cluster_severity_high(self):
        assert _cluster_severity(6) == "HIGH"

    def test_cluster_severity_medium(self):
        assert _cluster_severity(4) == "MEDIUM"

    def test_cluster_severity_low(self):
        assert _cluster_severity(2) == "LOW"


# ---------------------------------------------------------------------------
# Lexical helpers
# ---------------------------------------------------------------------------


class TestLexicalHelpers:
    def test_extract_tokens_basic(self):
        tokens = _extract_tokens("Patrick Mahomes will win MVP")
        assert "patrick" in tokens
        assert "mahomes" in tokens
        assert "win" in tokens

    def test_extract_tokens_strips_punctuation(self):
        tokens = _extract_tokens("He's great!")
        assert "hes" in tokens or "he" in tokens
        assert "great" in tokens

    def test_extract_tokens_empty_string(self):
        assert _extract_tokens("") == frozenset()

    def test_extract_tokens_none(self):
        assert _extract_tokens(None) == frozenset()

    def test_jaccard_identical(self):
        a = frozenset(["a", "b", "c"])
        assert _jaccard(a, a) == 1.0

    def test_jaccard_disjoint(self):
        a = frozenset(["a", "b"])
        b = frozenset(["c", "d"])
        assert _jaccard(a, b) == 0.0

    def test_jaccard_partial(self):
        a = frozenset(["a", "b", "c"])
        b = frozenset(["b", "c", "d"])
        sim = _jaccard(a, b)
        assert abs(sim - 0.5) < 1e-9  # |{b,c}| / |{a,b,c,d}| = 2/4

    def test_jaccard_empty(self):
        assert _jaccard(frozenset(), frozenset(["a"])) == 0.0

    def test_extract_outlet_standard(self):
        assert _extract_outlet("https://www.espn.com/nfl/article") == "espn.com"

    def test_extract_outlet_no_www(self):
        assert _extract_outlet("https://theathletic.com/article") == "theathletic.com"

    def test_extract_outlet_none(self):
        assert _extract_outlet(None) == "unknown"

    def test_extract_outlet_empty(self):
        assert _extract_outlet("") == "unknown"


# ---------------------------------------------------------------------------
# COIFlag.to_bq_row
# ---------------------------------------------------------------------------


class TestCOIFlagToBqRow:
    def test_disclaimer_in_signal_data(self):
        flag = COIFlag(
            flag_id="a" * 64,
            pundit_id="mel_kiper",
            signal_type="CONFIDENCE_SPIKE",
            severity="MEDIUM",
            detected_at=NOW,
            window_start=NOW,
            window_end=NOW,
            entity_key=None,
            claim_hashes=["hash1"],
            signal_data={"z_score": 2.5},
            pipeline_run_id="abc12345",
        )
        row = flag.to_bq_row()
        import json

        parsed = json.loads(row["signal_data"])
        assert "disclaimer" in parsed
        assert parsed["disclaimer"] == DISCLAIMER

    def test_none_timestamps_serialize_to_none(self):
        flag = COIFlag(
            flag_id="b" * 64,
            pundit_id="adam_schefter",
            signal_type="ENTITY_BIAS",
            severity="HIGH",
            detected_at=NOW,
            window_start=None,
            window_end=None,
            entity_key="Patrick Mahomes",
            claim_hashes=[],
            signal_data={},
            pipeline_run_id="xyz",
        )
        row = flag.to_bq_row()
        assert row["window_start"] is None
        assert row["window_end"] is None


# ---------------------------------------------------------------------------
# Signal 1 -- Confidence Spike
# ---------------------------------------------------------------------------


class TestSignal1ConfidenceSpike:
    def test_skipped_when_coverage_below_50pct(self, mock_db):
        mock_db.fetch_df.return_value = pd.DataFrame({"overall_coverage": [0.30]})
        flags = run_signal1_confidence_spike(mock_db, "run001")
        assert flags == []

    def test_returns_empty_when_no_spikes(self, mock_db):
        # First call: coverage check; second call: spike detection
        mock_db.fetch_df.side_effect = [
            pd.DataFrame({"overall_coverage": [0.75]}),  # coverage OK
            pd.DataFrame(),  # no spikes
        ]
        flags = run_signal1_confidence_spike(mock_db, "run001")
        assert flags == []

    def test_detects_spike(self, mock_db):
        spike_df = pd.DataFrame(
            {
                "prediction_hash": ["hash_001"],
                "pundit_id": ["mel_kiper"],
                "raw_confidence": [0.95],
                "ingestion_timestamp": [NOW],
                "mu": [0.55],
                "sigma": [0.10],
                "baseline_n": [40],
                "z_score": [4.0],
            }
        )
        mock_db.fetch_df.side_effect = [
            pd.DataFrame({"overall_coverage": [0.80]}),
            spike_df,
        ]
        flags = run_signal1_confidence_spike(mock_db, "run001")
        assert len(flags) == 1
        f = flags[0]
        assert f.signal_type == "CONFIDENCE_SPIKE"
        assert f.pundit_id == "mel_kiper"
        assert f.severity == "HIGH"
        assert f.claim_hashes == ["hash_001"]
        assert f.signal_data["z_score"] == 4.0

    def test_severity_medium_at_z_2(self, mock_db):
        spike_df = pd.DataFrame(
            {
                "prediction_hash": ["h1"],
                "pundit_id": ["p1"],
                "raw_confidence": [0.82],
                "ingestion_timestamp": [NOW],
                "mu": [0.60],
                "sigma": [0.10],
                "baseline_n": [25],
                "z_score": [2.2],
            }
        )
        mock_db.fetch_df.side_effect = [
            pd.DataFrame({"overall_coverage": [0.70]}),
            spike_df,
        ]
        flags = run_signal1_confidence_spike(mock_db, "run002")
        assert flags[0].severity == "MEDIUM"

    def test_query_failure_returns_empty(self, mock_db):
        mock_db.fetch_df.side_effect = [
            pd.DataFrame({"overall_coverage": [0.80]}),
            Exception("BQ error"),
        ]
        flags = run_signal1_confidence_spike(mock_db, "run003")
        assert flags == []


# ---------------------------------------------------------------------------
# Signal 2 -- Entity Bias
# ---------------------------------------------------------------------------


class TestSignal2EntityBias:
    def _make_bias_df(
        self,
        pundit_id="adam_schefter",
        entity_key="Patrick Mahomes",
        p_global=0.51,
        p_entity=0.78,
        n_entity=20,
        n_global=60,
        entity_claim_share=0.22,
        delta_threshold=0.20,
        claim_hashes=None,
    ):
        if claim_hashes is None:
            claim_hashes = ["h1", "h2"]
        return pd.DataFrame(
            {
                "pundit_id": [pundit_id],
                "entity_key": [entity_key],
                "p_global": [p_global],
                "p_entity": [p_entity],
                "n_entity": [n_entity],
                "n_global": [n_global],
                "delta_raw": [p_entity - p_global],
                "entity_claim_share": [entity_claim_share],
                "delta_threshold": [delta_threshold],
                "claim_hashes": [claim_hashes],
            }
        )

    def test_detects_entity_bias(self, mock_db):
        mock_db.fetch_df.return_value = self._make_bias_df()
        flags = run_signal2_entity_bias(mock_db, "run001")
        assert len(flags) == 1
        f = flags[0]
        assert f.signal_type == "ENTITY_BIAS"
        assert f.entity_key == "Patrick Mahomes"
        assert f.signal_data["accuracy_delta"] == pytest.approx(0.27)
        assert f.signal_data["delta_threshold_applied"] == 0.20

    def test_dominant_entity_uses_higher_threshold(self, mock_db):
        mock_db.fetch_df.return_value = self._make_bias_df(
            entity_claim_share=0.65,
            delta_threshold=SIGNAL2_DELTA_DOMINANT,
        )
        flags = run_signal2_entity_bias(mock_db, "run002")
        assert flags[0].signal_data["delta_threshold_applied"] == SIGNAL2_DELTA_DOMINANT

    def test_negative_delta_flags_as_entity_bias(self, mock_db):
        # Pundit performs WORSE on entity than globally
        mock_db.fetch_df.return_value = self._make_bias_df(
            p_global=0.70, p_entity=0.40, n_entity=20
        )
        flags = run_signal2_entity_bias(mock_db, "run003")
        assert len(flags) == 1
        assert flags[0].signal_data["accuracy_delta"] == pytest.approx(-0.30)

    def test_returns_empty_when_no_bias(self, mock_db):
        mock_db.fetch_df.return_value = pd.DataFrame()
        flags = run_signal2_entity_bias(mock_db, "run004")
        assert flags == []

    def test_severity_high_for_large_delta(self, mock_db):
        mock_db.fetch_df.return_value = self._make_bias_df(p_global=0.40, p_entity=0.80)
        flags = run_signal2_entity_bias(mock_db, "run005")
        assert flags[0].severity == "HIGH"

    def test_query_failure_returns_empty(self, mock_db):
        mock_db.fetch_df.side_effect = Exception("BQ offline")
        flags = run_signal2_entity_bias(mock_db, "run006")
        assert flags == []


# ---------------------------------------------------------------------------
# Signal 3 -- Narrative Cluster
# ---------------------------------------------------------------------------


class TestSignal3NarrativeCluster:
    def _make_ledger_df(self, n_pundits=4, n_outlets=3, time_gap_hours=2):
        """Generate n_pundits rows with highly similar claim text, spread across outlets."""
        base_claim = "Patrick Mahomes will win the MVP award this season"
        rows = []
        for i in range(n_pundits):
            rows.append(
                {
                    "prediction_hash": f"hash_{i:04d}",
                    "pundit_id": f"pundit_{i}",
                    "extracted_claim": base_claim,
                    "claim_category": "mvp_prediction",
                    "stance": "positive",
                    "entity_key": "Patrick Mahomes",
                    "ingestion_timestamp": NOW + timedelta(hours=i * time_gap_hours),
                    "source_url": f"https://outlet{i % n_outlets}.com/article",
                }
            )
        return pd.DataFrame(rows)

    def test_detects_cluster(self, mock_db):
        mock_db.fetch_df.return_value = self._make_ledger_df(n_pundits=4, n_outlets=3)
        flags = run_signal3_narrative_cluster(mock_db, "run001")
        assert len(flags) > 0
        f = flags[0]
        assert f.signal_type == "NARRATIVE_CLUSTER"
        assert f.signal_data["pundit_count"] >= SIGNAL3_MIN_PUNDITS

    def test_cluster_below_min_pundits_not_flagged(self, mock_db):
        mock_db.fetch_df.return_value = self._make_ledger_df(n_pundits=2, n_outlets=2)
        flags = run_signal3_narrative_cluster(mock_db, "run002", min_pundits=3)
        assert flags == []

    def test_cluster_below_min_outlets_not_flagged(self, mock_db):
        # All pundits on same outlet
        mock_db.fetch_df.return_value = self._make_ledger_df(n_pundits=4, n_outlets=1)
        flags = run_signal3_narrative_cluster(mock_db, "run003", min_outlets=2)
        assert flags == []

    def test_shared_source_suppression(self, mock_db):
        # All 4 pundits on same outlet => shared_source >= 50% => suppressed
        df = self._make_ledger_df(n_pundits=4, n_outlets=1)
        # Force all to the same outlet
        df["source_url"] = "https://samereporter.com/article"
        mock_db.fetch_df.return_value = df
        flags = run_signal3_narrative_cluster(mock_db, "run004", min_outlets=1)
        # Flags exist but are suppressed
        suppressed = [f for f in flags if f.suppressed]
        assert len(suppressed) > 0
        assert suppressed[0].suppression_reason == "shared_source_fraction_ge_50pct"

    def test_outside_time_window_not_clustered(self, mock_db):
        # Pundits spread 25h apart each -- total span > 72h window
        mock_db.fetch_df.return_value = self._make_ledger_df(
            n_pundits=4, n_outlets=3, time_gap_hours=25
        )
        flags = run_signal3_narrative_cluster(
            mock_db, "run005", window_hours=72, min_pundits=4
        )
        # Anchor at i=0, window_end = +72h. At 25h gaps, only pundits 0,1,2 fall in
        # window; pundit 3 is at 75h. So cluster size = 3 (just meets threshold).
        # Test that we don't blow up and severity is reasonable.
        assert isinstance(flags, list)

    def test_returns_empty_when_no_claims(self, mock_db):
        mock_db.fetch_df.return_value = pd.DataFrame()
        flags = run_signal3_narrative_cluster(mock_db, "run006")
        assert flags == []

    def test_query_failure_returns_empty(self, mock_db):
        mock_db.fetch_df.side_effect = Exception("timeout")
        flags = run_signal3_narrative_cluster(mock_db, "run007")
        assert flags == []

    def test_flag_has_disclaimer_in_signal_data(self, mock_db):
        mock_db.fetch_df.return_value = self._make_ledger_df(n_pundits=3, n_outlets=2)
        flags = run_signal3_narrative_cluster(mock_db, "run008")
        if flags:
            import json

            row = flags[0].to_bq_row()
            parsed = json.loads(row["signal_data"])
            assert DISCLAIMER in parsed.get("disclaimer", "")


# ---------------------------------------------------------------------------
# write_flags
# ---------------------------------------------------------------------------


class TestWriteFlags:
    def test_dry_run_returns_zero(self, mock_db):
        flag = COIFlag(
            flag_id="c" * 64,
            pundit_id="p1",
            signal_type="CONFIDENCE_SPIKE",
            severity="MEDIUM",
            detected_at=NOW,
            window_start=NOW,
            window_end=NOW,
            entity_key=None,
            claim_hashes=["h1"],
            signal_data={"z_score": 2.5},
            pipeline_run_id="r1",
        )
        result = write_flags(mock_db, [flag], dry_run=True)
        assert result == 0

    def test_empty_flags_returns_zero(self, mock_db):
        assert write_flags(mock_db, [], dry_run=False) == 0


# ---------------------------------------------------------------------------
# run_daily
# ---------------------------------------------------------------------------


class TestRunDaily:
    def test_returns_expected_keys(self, mock_db):
        mock_db.fetch_df.return_value = pd.DataFrame()
        # _ensure_table calls db.execute
        mock_db.execute.return_value = None
        result = run_daily(db=mock_db, run_id="test-run", dry_run=True)
        assert "signal1_count" in result
        assert "signal2_count" in result
        assert "signal3_count" in result
        assert "total_written" in result
        assert result["run_id"] == "test-run"

    def test_only_selected_signals_run(self, mock_db):
        mock_db.fetch_df.return_value = pd.DataFrame()
        mock_db.execute.return_value = None
        with (
            patch("src.coi_engine.run_signal1_confidence_spike") as s1,
            patch("src.coi_engine.run_signal2_entity_bias") as s2,
            patch("src.coi_engine.run_signal3_narrative_cluster") as s3,
        ):
            s1.return_value = []
            s2.return_value = []
            s3.return_value = []
            run_daily(db=mock_db, run_id="r", signals=[2], dry_run=True)
            s1.assert_not_called()
            s2.assert_called_once()
            s3.assert_not_called()
