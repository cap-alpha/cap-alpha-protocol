"""
Tests for RegistryManager (Issue #119 — Adaptive Pundit Registry).
All tests use mocked DBManager — no BigQuery or network required.
"""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, call, patch

import pandas as pd
import pytest

from src.registry_manager import (
    DISCOVERY_MIN_APPEARANCES,
    DISCOVERY_WINDOW_DAYS,
    RegistryManager,
    compute_cadence_tier,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_YAML_CONFIG = {
    "sources": [
        {
            "id": "espn_nfl",
            "name": "ESPN NFL",
            "type": "rss",
            "url": "https://www.espn.com/espn/rss/nfl/news",
            "sport": "NFL",
            "enabled": True,
            "scrape_full_text": True,
            "default_pundit": {"id": "espn_nfl_staff", "name": "ESPN NFL Staff"},
            "pundits": [
                {
                    "id": "adam_schefter",
                    "name": "Adam Schefter",
                    "match_authors": ["Adam Schefter", "Schefter"],
                },
                {
                    "id": "jeremy_fowler",
                    "name": "Jeremy Fowler",
                    "match_authors": ["Jeremy Fowler"],
                },
            ],
        },
        {
            "id": "pat_mcafee_show",
            "name": "The Pat McAfee Show",
            "type": "youtube_transcript",
            "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCxcTeAKWJca6XyJ37_ZoKIQ",
            "sport": "NFL",
            "enabled": True,
            "pundits": [
                {
                    "id": "pat_mcafee",
                    "name": "Pat McAfee",
                    "match_authors": ["Pat McAfee"],
                }
            ],
        },
        {
            "id": "disabled_feed",
            "name": "Disabled Feed",
            "type": "rss",
            "url": "https://example.com/feed",
            "sport": "NFL",
            "enabled": False,
            "pundits": [],
        },
    ],
    "defaults": {"fetch_timeout_seconds": 30},
}


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.project_id = "test-project"
    db.fetch_df.return_value = pd.DataFrame()
    db.execute.return_value = None
    db.append_dataframe_to_table.return_value = None
    return db


@pytest.fixture
def rm(mock_db):
    return RegistryManager(mock_db)


# ---------------------------------------------------------------------------
# compute_cadence_tier
# ---------------------------------------------------------------------------


class TestComputeCadenceTier:
    def test_daily_at_high_frequency(self):
        assert compute_cadence_tier(20.0) == "daily"

    def test_daily_at_threshold(self):
        assert compute_cadence_tier(15.0) == "daily"

    def test_twice_weekly_above_7(self):
        assert compute_cadence_tier(10.0) == "twice_weekly"

    def test_twice_weekly_at_threshold(self):
        assert compute_cadence_tier(7.0) == "twice_weekly"

    def test_weekly_above_3(self):
        assert compute_cadence_tier(5.0) == "weekly"

    def test_weekly_at_threshold(self):
        assert compute_cadence_tier(3.0) == "weekly"

    def test_biweekly_above_1(self):
        assert compute_cadence_tier(2.0) == "biweekly"

    def test_biweekly_at_threshold(self):
        assert compute_cadence_tier(1.0) == "biweekly"

    def test_monthly_below_1(self):
        assert compute_cadence_tier(0.5) == "monthly"

    def test_monthly_at_zero(self):
        assert compute_cadence_tier(0.0) == "monthly"


# ---------------------------------------------------------------------------
# seed_from_yaml
# ---------------------------------------------------------------------------


class TestSeedFromYaml:
    def test_inserts_sources_and_pundits(self, rm, mock_db):
        summary = rm.seed_from_yaml(SAMPLE_YAML_CONFIG)

        # 3 sources: espn_nfl, pat_mcafee_show, disabled_feed
        assert summary["sources_inserted"] == 3
        # pundits: espn_nfl_staff (default), adam_schefter, jeremy_fowler, pat_mcafee
        assert summary["pundits_inserted"] == 4
        assert summary["sources_skipped"] == 0
        assert summary["pundits_skipped"] == 0

        # BQ writes should have happened
        assert mock_db.append_dataframe_to_table.call_count >= 2

    def test_skips_existing_sources(self, rm, mock_db):
        existing_sources = pd.DataFrame({"source_id": ["espn_nfl"]})
        existing_pundits = pd.DataFrame(
            {"pundit_id": ["espn_nfl_staff", "adam_schefter", "jeremy_fowler"]}
        )
        mock_db.fetch_df.side_effect = [existing_sources, existing_pundits]

        summary = rm.seed_from_yaml(SAMPLE_YAML_CONFIG)

        assert summary["sources_skipped"] == 1
        assert summary["sources_inserted"] == 2  # pat_mcafee_show, disabled_feed
        assert summary["pundits_skipped"] == 3

    def test_default_pundit_marked_correctly(self, rm, mock_db):
        rm.seed_from_yaml(SAMPLE_YAML_CONFIG)

        pundit_write_call = None
        for c in mock_db.append_dataframe_to_table.call_args_list:
            df, table = c.args
            if table == "pundit_registry":
                pundit_write_call = df
                break

        assert pundit_write_call is not None
        defaults = pundit_write_call[pundit_write_call["is_source_default"] == True]
        assert "espn_nfl_staff" in defaults["pundit_id"].values

    def test_source_rows_have_required_fields(self, rm, mock_db):
        rm.seed_from_yaml(SAMPLE_YAML_CONFIG)

        source_write_call = None
        for c in mock_db.append_dataframe_to_table.call_args_list:
            df, table = c.args
            if table == "source_registry":
                source_write_call = df
                break

        assert source_write_call is not None
        required = {
            "source_id",
            "source_name",
            "source_type",
            "url",
            "sport",
            "enabled",
        }
        assert required.issubset(set(source_write_call.columns))

    def test_overwrite_deletes_existing(self, rm, mock_db):
        rm.seed_from_yaml(SAMPLE_YAML_CONFIG, overwrite=True)

        delete_calls = [str(c) for c in mock_db.execute.call_args_list]
        assert any("DELETE" in c and "source_registry" in c for c in delete_calls)
        assert any("DELETE" in c and "pundit_registry" in c for c in delete_calls)

    def test_empty_config_returns_zeros(self, rm, mock_db):
        summary = rm.seed_from_yaml({"sources": []})
        assert summary == {
            "sources_inserted": 0,
            "sources_skipped": 0,
            "pundits_inserted": 0,
            "pundits_skipped": 0,
        }


# ---------------------------------------------------------------------------
# get_source_config
# ---------------------------------------------------------------------------


class TestGetSourceConfig:
    def _make_source_df(self):
        return pd.DataFrame(
            [
                {
                    "source_id": "espn_nfl",
                    "source_name": "ESPN NFL",
                    "source_type": "rss",
                    "url": "https://www.espn.com/espn/rss/nfl/news",
                    "sport": "NFL",
                    "enabled": True,
                    "scrape_full_text": True,
                    "keyword_filter": None,
                    "default_pundit_id": "espn_nfl_staff",
                    "polling_cadence": "daily",
                },
                {
                    "source_id": "pat_mcafee_show",
                    "source_name": "The Pat McAfee Show",
                    "source_type": "youtube_transcript",
                    "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCxcTeAKWJca6XyJ37_ZoKIQ",
                    "sport": "NFL",
                    "enabled": True,
                    "scrape_full_text": None,
                    "keyword_filter": None,
                    "default_pundit_id": None,
                    "polling_cadence": "daily",
                },
            ]
        )

    def _make_pundit_df(self):
        return pd.DataFrame(
            [
                {
                    "pundit_id": "espn_nfl_staff",
                    "pundit_name": "ESPN NFL Staff",
                    "source_ids": ["espn_nfl"],
                    "match_authors": [],
                    "is_source_default": True,
                },
                {
                    "pundit_id": "adam_schefter",
                    "pundit_name": "Adam Schefter",
                    "source_ids": ["espn_nfl"],
                    "match_authors": ["Adam Schefter", "Schefter"],
                    "is_source_default": False,
                },
                {
                    "pundit_id": "pat_mcafee",
                    "pundit_name": "Pat McAfee",
                    "source_ids": ["pat_mcafee_show"],
                    "match_authors": ["Pat McAfee"],
                    "is_source_default": False,
                },
            ]
        )

    def test_returns_sources_list(self, rm, mock_db):
        mock_db.fetch_df.side_effect = [self._make_source_df(), self._make_pundit_df()]
        config = rm.get_source_config()
        assert len(config["sources"]) == 2

    def test_source_has_expected_fields(self, rm, mock_db):
        mock_db.fetch_df.side_effect = [self._make_source_df(), self._make_pundit_df()]
        config = rm.get_source_config()
        espn = next(s for s in config["sources"] if s["id"] == "espn_nfl")
        assert espn["type"] == "rss"
        assert espn["sport"] == "NFL"
        assert espn["enabled"] is True
        assert espn["scrape_full_text"] is True

    def test_pundits_attached_to_correct_source(self, rm, mock_db):
        mock_db.fetch_df.side_effect = [self._make_source_df(), self._make_pundit_df()]
        config = rm.get_source_config()

        espn = next(s for s in config["sources"] if s["id"] == "espn_nfl")
        mcafee = next(s for s in config["sources"] if s["id"] == "pat_mcafee_show")

        espn_ids = {p["id"] for p in espn["pundits"]}
        assert "adam_schefter" in espn_ids
        assert "espn_nfl_staff" not in espn_ids  # default pundit not in pundits list

        assert espn.get("default_pundit", {}).get("id") == "espn_nfl_staff"

        mcafee_ids = {p["id"] for p in mcafee["pundits"]}
        assert "pat_mcafee" in mcafee_ids

    def test_returns_empty_when_registry_empty(self, rm, mock_db):
        mock_db.fetch_df.return_value = pd.DataFrame()
        config = rm.get_source_config()
        assert config == {"sources": [], "defaults": {}}

    def test_graceful_when_bq_fails(self, rm, mock_db):
        mock_db.fetch_df.side_effect = Exception("BQ unavailable")
        # get_source_config itself doesn't catch — caller (load_config_from_bq) does
        with pytest.raises(Exception, match="BQ unavailable"):
            rm.get_source_config()


# ---------------------------------------------------------------------------
# find_discovery_candidates
# ---------------------------------------------------------------------------


class TestFindDiscoveryCandidates:
    def test_returns_candidates_from_bq(self, rm, mock_db):
        candidates_df = pd.DataFrame(
            [
                {
                    "author": "Dianna Russini",
                    "source_id": "theathletic_nfl",
                    "appearances": 5,
                    "first_seen": datetime(2026, 4, 1, tzinfo=timezone.utc),
                    "last_seen": datetime(2026, 4, 20, tzinfo=timezone.utc),
                }
            ]
        )
        mock_db.fetch_df.return_value = candidates_df

        results = rm.find_discovery_candidates()

        assert len(results) == 1
        assert results[0]["author"] == "Dianna Russini"
        assert results[0]["appearances"] == 5

    def test_returns_empty_on_no_candidates(self, rm, mock_db):
        mock_db.fetch_df.return_value = pd.DataFrame()
        results = rm.find_discovery_candidates()
        assert results == []

    def test_returns_empty_on_bq_error(self, rm, mock_db):
        mock_db.fetch_df.side_effect = Exception("BQ timeout")
        results = rm.find_discovery_candidates()
        assert results == []

    def test_logs_audit_entry_for_each_candidate(self, rm, mock_db):
        candidates_df = pd.DataFrame(
            [
                {
                    "author": "Alice",
                    "source_id": "src_a",
                    "appearances": 4,
                    "first_seen": None,
                    "last_seen": None,
                },
                {
                    "author": "Bob",
                    "source_id": "src_b",
                    "appearances": 7,
                    "first_seen": None,
                    "last_seen": None,
                },
            ]
        )
        mock_db.fetch_df.return_value = candidates_df

        rm.find_discovery_candidates()

        audit_calls = [
            c
            for c in mock_db.append_dataframe_to_table.call_args_list
            if c.args[1] == "registry_audit_log"
        ]
        assert len(audit_calls) == 2

    def test_query_uses_configured_thresholds(self, rm, mock_db):
        mock_db.fetch_df.return_value = pd.DataFrame()
        rm.find_discovery_candidates(min_appearances=5, window_days=14)

        query = mock_db.fetch_df.call_args.args[0]
        assert "5" in query
        assert "14" in query


# ---------------------------------------------------------------------------
# refresh_cadences
# ---------------------------------------------------------------------------


class TestRefreshCadences:
    def test_updates_cadence_when_changed(self, rm, mock_db):
        freq_df = pd.DataFrame(
            [{"pundit_id": "adam_schefter", "posts_per_month": 20.0}]
        )
        reg_df = pd.DataFrame(
            [
                {
                    "pundit_id": "adam_schefter",
                    "polling_cadence": "weekly",
                    "posts_per_month": 3.0,
                }
            ]
        )
        mock_db.fetch_df.side_effect = [freq_df, reg_df]

        updated = rm.refresh_cadences()

        assert updated == 1  # cadence changed from weekly → daily

    def test_no_update_when_cadence_unchanged(self, rm, mock_db):
        freq_df = pd.DataFrame([{"pundit_id": "adam_schefter", "posts_per_month": 5.0}])
        reg_df = pd.DataFrame(
            [
                {
                    "pundit_id": "adam_schefter",
                    "polling_cadence": "weekly",
                    "posts_per_month": 5.0,
                }
            ]
        )
        mock_db.fetch_df.side_effect = [freq_df, reg_df]

        updated = rm.refresh_cadences()

        assert updated == 0  # weekly is correct for 5/month, no change

    def test_returns_zero_on_empty_data(self, rm, mock_db):
        mock_db.fetch_df.return_value = pd.DataFrame()
        updated = rm.refresh_cadences()
        assert updated == 0

    def test_returns_zero_on_bq_error(self, rm, mock_db):
        mock_db.fetch_df.side_effect = Exception("connection reset")
        updated = rm.refresh_cadences()
        assert updated == 0


# ---------------------------------------------------------------------------
# CRUD helpers
# ---------------------------------------------------------------------------


class TestCrudHelpers:
    def test_enable_pundit_calls_update(self, rm, mock_db):
        rm.enable_pundit("adam_schefter", reason="Back from suspension")
        execute_calls = [str(c) for c in mock_db.execute.call_args_list]
        assert any("UPDATE" in c and "adam_schefter" in c for c in execute_calls)

    def test_disable_pundit_calls_update(self, rm, mock_db):
        rm.disable_pundit("adam_schefter", reason="Left ESPN")
        execute_calls = [str(c) for c in mock_db.execute.call_args_list]
        assert any("UPDATE" in c and "adam_schefter" in c for c in execute_calls)

    def test_update_last_seen_calls_update(self, rm, mock_db):
        ts = datetime(2026, 4, 25, 12, 0, 0, tzinfo=timezone.utc)
        rm.update_last_seen("pat_mcafee", ts)
        execute_calls = [str(c) for c in mock_db.execute.call_args_list]
        assert any("UPDATE" in c and "pat_mcafee" in c for c in execute_calls)

    def test_update_source_fetch_stats(self, rm, mock_db):
        rm.update_source_fetch_stats("espn_nfl", item_count=42)
        execute_calls = [str(c) for c in mock_db.execute.call_args_list]
        assert any("UPDATE" in c and "espn_nfl" in c for c in execute_calls)


# ---------------------------------------------------------------------------
# load_config_from_bq (integration with media_ingestor)
# ---------------------------------------------------------------------------


class TestLoadConfigFromBq:
    def test_returns_bq_config_when_available(self, tmp_path):
        import yaml
        from src.media_ingestor import load_config_from_bq

        yaml_config = {"sources": [{"id": "yaml_source"}], "defaults": {"timeout": 10}}
        yaml_path = tmp_path / "media_sources.yaml"
        yaml_path.write_text(yaml.dump(yaml_config))

        mock_db = MagicMock()
        mock_db.project_id = "test-project"

        bq_config = {
            "sources": [{"id": "bq_source", "type": "rss", "url": "http://x.com"}]
        }

        with patch("src.registry_manager.RegistryManager") as MockRM:
            MockRM.return_value.get_source_config.return_value = bq_config
            result = load_config_from_bq(mock_db, fallback_yaml_path=yaml_path)

        assert result["sources"][0]["id"] == "bq_source"
        assert result["defaults"]["timeout"] == 10  # merged from YAML

    def test_falls_back_to_yaml_when_bq_empty(self, tmp_path):
        import yaml
        from src.media_ingestor import load_config_from_bq

        yaml_config = {"sources": [{"id": "yaml_source"}], "defaults": {}}
        yaml_path = tmp_path / "media_sources.yaml"
        yaml_path.write_text(yaml.dump(yaml_config))

        mock_db = MagicMock()
        mock_db.project_id = "test-project"

        with patch("src.registry_manager.RegistryManager") as MockRM:
            MockRM.return_value.get_source_config.return_value = {"sources": []}
            result = load_config_from_bq(mock_db, fallback_yaml_path=yaml_path)

        assert result["sources"][0]["id"] == "yaml_source"

    def test_falls_back_to_yaml_when_bq_error(self, tmp_path):
        import yaml
        from src.media_ingestor import load_config_from_bq

        yaml_config = {"sources": [{"id": "yaml_source"}], "defaults": {}}
        yaml_path = tmp_path / "media_sources.yaml"
        yaml_path.write_text(yaml.dump(yaml_config))

        mock_db = MagicMock()
        mock_db.project_id = "test-project"

        with patch("src.registry_manager.RegistryManager") as MockRM:
            MockRM.return_value.get_source_config.side_effect = Exception("BQ down")
            result = load_config_from_bq(mock_db, fallback_yaml_path=yaml_path)

        assert result["sources"][0]["id"] == "yaml_source"
