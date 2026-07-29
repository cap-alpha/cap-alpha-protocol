"""
Tests for the Daily Media Ingestion Pipeline (Issue #78).
Unit tests — no BigQuery or network access required.
"""

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pandas as pd
import pytest

from src.media_ingestor import (
    FETCHERS,
    MediaItem,
    SourceResult,
    _extract_video_id,
    _is_youtube_short,
    _passes_keyword_filter,
    compute_content_hash,
    fetch_rss,
    get_existing_hashes,
    ingest_from_urls,
    ingest_source,
    load_media_config,
    match_pundit,
    match_pundit_by_author,
    match_pundit_by_byline,
    run_daily_ingestion,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_CONFIG = {
    "sources": [
        {
            "id": "test_feed",
            "name": "Test Feed",
            "type": "rss",
            "url": "https://example.com/feed",
            "enabled": True,
            "pundits": [
                {
                    "id": "adam_schefter",
                    "name": "Adam Schefter",
                    "match_authors": ["Adam Schefter", "Schefter"],
                },
                {
                    "id": "pat_mcafee",
                    "name": "Pat McAfee",
                    "match_authors": ["Pat McAfee"],
                },
            ],
        },
        {
            "id": "disabled_feed",
            "name": "Disabled Feed",
            "type": "rss",
            "url": "https://example.com/disabled",
            "enabled": False,
            "pundits": [],
        },
    ],
    "defaults": {
        "fetch_timeout_seconds": 10,
        "max_retries": 2,
        "retry_backoff_seconds": 0,  # fast tests
        "max_items_per_feed": 10,
        "dedup_window_days": 7,
    },
}


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.fetch_df.return_value = pd.DataFrame()
    return db


@pytest.fixture
def config_file(tmp_path):
    import yaml

    config_path = tmp_path / "media_sources.yaml"
    with open(config_path, "w") as f:
        yaml.dump(SAMPLE_CONFIG, f)
    return config_path


# ---------------------------------------------------------------------------
# Content hashing
# ---------------------------------------------------------------------------


class TestContentHash:
    def test_deterministic(self):
        h1 = compute_content_hash("https://example.com/a", "Title A")
        h2 = compute_content_hash("https://example.com/a", "Title A")
        assert h1 == h2

    def test_different_urls_produce_different_hashes(self):
        h1 = compute_content_hash("https://example.com/a", "Title")
        h2 = compute_content_hash("https://example.com/b", "Title")
        assert h1 != h2

    def test_returns_sha256_hex(self):
        h = compute_content_hash("https://example.com", "t")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)


# ---------------------------------------------------------------------------
# Pundit matching
# ---------------------------------------------------------------------------


class TestPunditMatchingByAuthor:
    """Tests for the author-field matcher (Tier 1)."""

    PUNDITS = [
        {
            "id": "adam_schefter",
            "name": "Adam Schefter",
            "match_authors": ["Adam Schefter", "Schefter"],
        },
        {"id": "pat_mcafee", "name": "Pat McAfee", "match_authors": ["Pat McAfee"]},
    ]

    def test_exact_match(self):
        pid, pname = match_pundit_by_author("Adam Schefter", self.PUNDITS)
        assert pid == "adam_schefter"
        assert pname == "Adam Schefter"

    def test_partial_match(self):
        pid, pname = match_pundit_by_author("By Schefter, ESPN", self.PUNDITS)
        assert pid == "adam_schefter"

    def test_case_insensitive(self):
        pid, pname = match_pundit_by_author("ADAM SCHEFTER", self.PUNDITS)
        assert pid == "adam_schefter"

    def test_no_match(self):
        pid, pname = match_pundit_by_author("Random Author", self.PUNDITS)
        assert pid is None
        assert pname is None

    def test_none_author(self):
        pid, pname = match_pundit_by_author(None, self.PUNDITS)
        assert pid is None
        assert pname is None


class TestPunditMatchingByByline:
    """Tests for the byline-scan matcher (Tier 2)."""

    PUNDITS = [
        {
            "id": "dianna_russini",
            "name": "Dianna Russini",
            "match_authors": ["Dianna Russini"],
        },
        {"id": "jeff_howe", "name": "Jeff Howe", "match_authors": ["Jeff Howe"]},
    ]

    def test_name_in_first_500_chars(self):
        text = (
            "By Dianna Russini — The Dolphins are expected to trade for a top receiver."
        )
        pid, pname = match_pundit_by_byline(text, self.PUNDITS)
        assert pid == "dianna_russini"
        assert pname == "Dianna Russini"

    def test_name_after_500_chars_not_matched(self):
        text = "x" * 501 + " Jeff Howe says the Patriots will draft a QB."
        pid, pname = match_pundit_by_byline(text, self.PUNDITS)
        assert pid is None

    def test_no_match(self):
        text = "Breaking news from an anonymous source close to the team."
        pid, pname = match_pundit_by_byline(text, self.PUNDITS)
        assert pid is None

    def test_none_text(self):
        pid, pname = match_pundit_by_byline(None, self.PUNDITS)
        assert pid is None


class TestPunditMatchingCascade:
    """Tests for the full three-tier cascade."""

    PUNDITS = [
        {
            "id": "mike_florio",
            "name": "Mike Florio",
            "match_authors": ["Mike Florio", "mflorio"],
        },
    ]
    SOURCE_WITH_DEFAULT = {
        "id": "pft_nbc",
        "default_pundit": {"id": "pft_staff", "name": "PFT Staff"},
        "pundits": PUNDITS,
    }
    SOURCE_NO_DEFAULT = {"id": "test_feed", "pundits": PUNDITS}

    def test_tier1_author_field_wins(self):
        pid, pname, method = match_pundit(
            "Mike Florio", self.PUNDITS, raw_text="Some article text"
        )
        assert pid == "mike_florio"
        assert method == "author_field"

    def test_tier2_byline_scan_when_author_empty(self):
        pid, pname, method = match_pundit(
            None,
            self.PUNDITS,
            raw_text="By Mike Florio — The Raiders are exploring options.",
        )
        assert pid == "mike_florio"
        assert method == "byline_scan"

    def test_tier3_source_default_when_no_author_or_byline(self):
        pid, pname, method = match_pundit(
            None,
            self.PUNDITS,
            raw_text="Breaking: anonymous source reports trade.",
            source=self.SOURCE_WITH_DEFAULT,
        )
        assert pid == "pft_staff"
        assert pname == "PFT Staff"
        assert method == "source_default"

    def test_unmatched_when_no_default(self):
        pid, pname, method = match_pundit(
            None,
            self.PUNDITS,
            raw_text="Breaking: anonymous source reports trade.",
            source=self.SOURCE_NO_DEFAULT,
        )
        assert pid is None
        assert method == "unmatched"

    def test_co_authored_article(self):
        """Author field 'Tim McManus and Jeremy Fowler' should match Jeremy Fowler."""
        pundits = [
            {
                "id": "jeremy_fowler",
                "name": "Jeremy Fowler",
                "match_authors": ["Jeremy Fowler"],
            },
        ]
        pid, pname, method = match_pundit("Tim McManus and Jeremy Fowler", pundits)
        assert pid == "jeremy_fowler"
        assert method == "author_field"


# ---------------------------------------------------------------------------
# Keyword filter
# ---------------------------------------------------------------------------


class TestKeywordFilter:
    def test_matches_title(self):
        assert _passes_keyword_filter("NFL Draft Preview", "", ["NFL", "football"])

    def test_matches_text(self):
        assert _passes_keyword_filter(
            "", "The quarterback threw a touchdown", ["touchdown"]
        )

    def test_case_insensitive(self):
        assert _passes_keyword_filter("nfl news", "", ["NFL"])

    def test_no_match(self):
        assert not _passes_keyword_filter(
            "Premier League Recap", "Soccer highlights", ["NFL", "football", "draft"]
        )

    def test_empty_keywords_returns_false(self):
        # Empty keyword list means any() over empty iterable → False.
        # Callers guard with `if keyword_filter and ...` so this is safe.
        assert not _passes_keyword_filter("Anything", "at all", [])

    def test_partial_word_match(self):
        """'football' in keyword list matches 'football' in text."""
        assert _passes_keyword_filter("", "Great football game today", ["football"])

    @patch("src.media_ingestor.feedparser")
    def test_fetch_rss_skips_filtered_entries(self, mock_fp):
        """Entries not matching keyword_filter should be skipped."""
        entry_nfl = MagicMock()
        entry_nfl.get = lambda k, d=None: {
            "title": "NFL Draft Big Board",
            "link": "https://example.com/nfl",
            "author": "Test Author",
        }.get(k, d)
        entry_nfl.published_parsed = (2025, 9, 1, 12, 0, 0, 0, 0, 0)
        type(entry_nfl).summary = property(lambda self: "<p>NFL draft content</p>")
        entry_nfl.content = []
        entry_nfl.tags = []

        entry_soccer = MagicMock()
        entry_soccer.get = lambda k, d=None: {
            "title": "Premier League Weekend Recap",
            "link": "https://example.com/soccer",
            "author": "Test Author",
        }.get(k, d)
        entry_soccer.published_parsed = (2025, 9, 1, 12, 0, 0, 0, 0, 0)
        type(entry_soccer).summary = property(
            lambda self: "<p>Soccer match highlights</p>"
        )
        entry_soccer.content = []
        entry_soccer.tags = []

        feed = MagicMock()
        feed.bozo = False
        feed.entries = [entry_nfl, entry_soccer]
        mock_fp.parse.return_value = feed

        source = {
            "id": "theathletic_nfl",
            "name": "The Athletic NFL",
            "type": "rss",
            "url": "https://example.com/feed",
            "sport": "NFL",
            "keyword_filter": ["NFL", "football", "draft"],
            "pundits": [],
        }
        defaults = {"max_items_per_feed": 50, "fetch_timeout_seconds": 30}

        items = fetch_rss(source, defaults)
        assert len(items) == 1
        assert items[0].title == "NFL Draft Big Board"


# ---------------------------------------------------------------------------
# Dedup (get_existing_hashes)
# ---------------------------------------------------------------------------


class TestGetExistingHashes:
    def test_returns_set_of_hashes(self, mock_db):
        mock_db.fetch_df.return_value = pd.DataFrame(
            {"content_hash": ["abc123", "def456"]}
        )
        result = get_existing_hashes(mock_db, "test_feed")
        assert result == {"abc123", "def456"}

    def test_returns_empty_set_on_error(self, mock_db):
        mock_db.fetch_df.side_effect = Exception("BQ down")
        result = get_existing_hashes(mock_db, "test_feed")
        assert result == set()

    def test_returns_empty_set_when_no_data(self, mock_db):
        mock_db.fetch_df.return_value = pd.DataFrame()
        result = get_existing_hashes(mock_db, "test_feed")
        assert result == set()


# ---------------------------------------------------------------------------
# fetch_rss (mocked feedparser)
# ---------------------------------------------------------------------------


class TestFetchRSS:
    def _make_feed(self, entries):
        """Simulate feedparser output."""
        feed = MagicMock()
        feed.bozo = False
        feed.entries = entries
        return feed

    def _make_entry(
        self, title="Test Article", link="https://example.com/1", author="Adam Schefter"
    ):
        entry = MagicMock()
        entry.get = lambda k, d=None: {
            "title": title,
            "link": link,
            "author": author,
        }.get(k, d)
        entry.title = title
        entry.link = link
        entry.author = author
        entry.published_parsed = (2025, 9, 1, 12, 0, 0, 0, 0, 0)
        entry.summary = "<p>Prediction text here</p>"
        entry.content = []
        entry.tags = []
        # Make hasattr work
        type(entry).summary = property(lambda self: "<p>Prediction text here</p>")
        return entry

    @patch("src.media_ingestor.feedparser")
    def test_returns_media_items(self, mock_fp):
        entry = self._make_entry()
        mock_fp.parse.return_value = self._make_feed([entry])

        source = SAMPLE_CONFIG["sources"][0]
        defaults = SAMPLE_CONFIG["defaults"]
        items = fetch_rss(source, defaults)

        assert len(items) == 1
        assert items[0].source_id == "test_feed"
        assert items[0].matched_pundit_id == "adam_schefter"
        assert items[0].content_type == "article"

    @patch("src.media_ingestor.feedparser")
    def test_skips_entries_without_link(self, mock_fp):
        entry = self._make_entry(link="")
        mock_fp.parse.return_value = self._make_feed([entry])

        source = SAMPLE_CONFIG["sources"][0]
        items = fetch_rss(source, SAMPLE_CONFIG["defaults"])
        assert len(items) == 0

    @patch("src.media_ingestor.feedparser")
    def test_raises_on_bozo_with_no_entries(self, mock_fp):
        feed = self._make_feed([])
        feed.bozo = True
        feed.bozo_exception = "XML parse error"
        mock_fp.parse.return_value = feed

        source = SAMPLE_CONFIG["sources"][0]
        with pytest.raises(ValueError, match="Feed parse error"):
            fetch_rss(source, SAMPLE_CONFIG["defaults"])


# ---------------------------------------------------------------------------
# ingest_source
# ---------------------------------------------------------------------------


class TestPodcastFetcherRegistration:
    """Regression tests for the missing `podcast` fetcher (#pipeline-ingestion-recovery).

    the_ringer_nfl and bill_simmons_podcast are `type: podcast` sources backed
    by plain Megaphone RSS feeds. Before this fix, FETCHERS had no "podcast"
    key, so ingest_source() hard-failed both sources every run with
    "No fetcher for source type: podcast".
    """

    def test_podcast_type_is_registered(self):
        assert "podcast" in FETCHERS

    def test_podcast_type_routes_to_fetch_rss(self):
        assert FETCHERS["podcast"] is fetch_rss

    @patch("src.media_ingestor.feedparser")
    def test_podcast_source_fetches_via_rss(self, mock_fp):
        """A `type: podcast` source (e.g. Megaphone feed) is fetched exactly
        like a plain RSS feed and tagged content_type=podcast_episode."""
        entry = MagicMock()
        entry.get = lambda k, d=None: {
            "title": "The Ringer NFL Show: Week 1 Preview",
            "link": "https://feeds.megaphone.fm/ep1",
            "author": "Robert Mays",
        }.get(k, d)
        entry.published_parsed = None
        type(entry).summary = property(
            lambda self: "Predictions for every Week 1 game."
        )
        entry.content = []
        entry.tags = []

        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.entries = [entry]
        mock_fp.parse.return_value = mock_feed

        source = {
            "id": "the_ringer_nfl",
            "name": "The Ringer NFL",
            "type": "podcast",
            "url": "https://feeds.megaphone.fm/the-ringer-nfl-show",
            "pundits": [],
        }
        items = FETCHERS["podcast"](source, {"max_items_per_feed": 10})

        assert len(items) == 1
        assert items[0].content_type == "podcast_episode"
        assert items[0].fetch_source_type == "podcast"
        assert items[0].source_url == "https://feeds.megaphone.fm/ep1"

    def test_ingest_source_no_longer_errors_for_podcast_type(self, mock_db):
        """End-to-end: ingest_source() must not report 'No fetcher' for podcast
        sources — this was the exact failure mode before FETCHERS["podcast"]
        was registered."""
        mock_db.fetch_df.return_value = pd.DataFrame()
        source = {
            "id": "bill_simmons_podcast",
            "name": "The Bill Simmons Podcast",
            "type": "podcast",
            "url": "https://feeds.megaphone.fm/the-bill-simmons-podcast",
            "pundits": [],
        }
        mock_fetcher = MagicMock(return_value=[])
        with patch.dict("src.media_ingestor.FETCHERS", {"podcast": mock_fetcher}):
            result = ingest_source(source, {"max_items_per_feed": 10}, mock_db)

        assert result.error is None
        mock_fetcher.assert_called_once()


class TestIngestSource:
    def _make_item(self, content_hash="hash1", **overrides):
        now = datetime.now(timezone.utc)
        defaults = dict(
            content_hash=content_hash,
            source_id="test_feed",
            title="Test",
            raw_text="Text",
            source_url="https://example.com/1",
            author="Adam Schefter",
            matched_pundit_id="adam_schefter",
            matched_pundit_name="Adam Schefter",
            published_at=now,
            ingested_at=now,
            content_type="article",
            fetch_source_type="rss",
        )
        defaults.update(overrides)
        return MediaItem(**defaults)

    def test_writes_new_items(self, mock_db):
        mock_fetcher = MagicMock(return_value=[self._make_item()])
        mock_db.fetch_df.return_value = pd.DataFrame()

        source = SAMPLE_CONFIG["sources"][0]
        with patch.dict("src.media_ingestor.FETCHERS", {"rss": mock_fetcher}):
            result = ingest_source(source, SAMPLE_CONFIG["defaults"], mock_db)

        assert result.items_fetched == 1
        assert result.items_new == 1
        assert result.items_deduped == 0
        assert result.error is None
        mock_db.append_dataframe_to_table.assert_called_once()

    def test_deduplicates_existing_items(self, mock_db):
        mock_fetcher = MagicMock(
            return_value=[self._make_item(content_hash="already_seen")]
        )
        mock_db.fetch_df.return_value = pd.DataFrame({"content_hash": ["already_seen"]})

        source = SAMPLE_CONFIG["sources"][0]
        with patch.dict("src.media_ingestor.FETCHERS", {"rss": mock_fetcher}):
            result = ingest_source(source, SAMPLE_CONFIG["defaults"], mock_db)

        assert result.items_fetched == 1
        assert result.items_new == 0
        assert result.items_deduped == 1
        mock_db.append_dataframe_to_table.assert_not_called()

    def test_dry_run_does_not_write(self, mock_db):
        mock_fetcher = MagicMock(
            return_value=[self._make_item(content_hash="hash_new")]
        )
        mock_db.fetch_df.return_value = pd.DataFrame()

        source = SAMPLE_CONFIG["sources"][0]
        with patch.dict("src.media_ingestor.FETCHERS", {"rss": mock_fetcher}):
            result = ingest_source(
                source, SAMPLE_CONFIG["defaults"], mock_db, dry_run=True
            )

        assert result.items_new == 1
        mock_db.append_dataframe_to_table.assert_not_called()

    def test_retries_on_failure(self, mock_db):
        mock_fetcher = MagicMock(side_effect=[Exception("Network error"), []])
        mock_db.fetch_df.return_value = pd.DataFrame()

        source = SAMPLE_CONFIG["sources"][0]
        defaults = {**SAMPLE_CONFIG["defaults"], "max_retries": 2}
        with patch.dict("src.media_ingestor.FETCHERS", {"rss": mock_fetcher}):
            result = ingest_source(source, defaults, mock_db)

        assert result.error is None
        assert mock_fetcher.call_count == 2

    def test_records_error_after_max_retries(self, mock_db):
        mock_fetcher = MagicMock(side_effect=Exception("Persistent failure"))

        source = SAMPLE_CONFIG["sources"][0]
        defaults = {**SAMPLE_CONFIG["defaults"], "max_retries": 2}
        with patch.dict("src.media_ingestor.FETCHERS", {"rss": mock_fetcher}):
            result = ingest_source(source, defaults, mock_db)

        assert result.error is not None
        assert "Persistent failure" in result.error


# ---------------------------------------------------------------------------
# run_daily_ingestion
# ---------------------------------------------------------------------------


class TestRunDailyIngestion:
    @patch("src.media_ingestor.ingest_source")
    def test_skips_disabled_sources(self, mock_ingest, mock_db, config_file):
        mock_ingest.return_value = SourceResult(
            source_id="test_feed", source_name="Test Feed", items_new=5
        )
        results = run_daily_ingestion(config_path=config_file, db=mock_db)
        # Only 1 source should be ingested (disabled_feed is skipped)
        assert len(results) == 1
        assert results[0].source_id == "test_feed"

    @patch("src.media_ingestor.ingest_source")
    def test_source_filter(self, mock_ingest, mock_db, config_file):
        mock_ingest.return_value = SourceResult(
            source_id="test_feed", source_name="Test Feed"
        )
        results = run_daily_ingestion(
            config_path=config_file,
            source_filter="test_feed",
            db=mock_db,
        )
        assert len(results) == 1

    @patch("src.media_ingestor.ingest_source")
    def test_source_filter_no_match(self, mock_ingest, mock_db, config_file):
        results = run_daily_ingestion(
            config_path=config_file,
            source_filter="nonexistent",
            db=mock_db,
        )
        assert len(results) == 0

    @patch("src.media_ingestor.ingest_source")
    def test_catches_unexpected_errors(self, mock_ingest, mock_db, config_file):
        mock_ingest.side_effect = RuntimeError("Unexpected crash")
        results = run_daily_ingestion(config_path=config_file, db=mock_db)
        assert len(results) == 1
        assert results[0].error is not None

    @patch("src.media_ingestor.ingest_source")
    def test_returns_manifest(self, mock_ingest, mock_db, config_file):
        mock_ingest.return_value = SourceResult(
            source_id="test_feed",
            source_name="Test Feed",
            items_fetched=10,
            items_new=3,
            items_deduped=7,
        )
        results = run_daily_ingestion(config_path=config_file, db=mock_db)
        assert results[0].items_fetched == 10
        assert results[0].items_new == 3
        assert results[0].items_deduped == 7


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------


class TestConfigLoading:
    def test_loads_real_config(self):
        config = load_media_config()
        assert "sources" in config
        assert "defaults" in config
        assert len(config["sources"]) > 0

    def test_all_sources_have_required_fields(self):
        config = load_media_config()
        for source in config["sources"]:
            assert "id" in source
            assert "name" in source
            assert "type" in source
            assert "url" in source

    def test_no_enabled_source_has_unknown_channel_id(self):
        """Sanity check: no enabled YouTube source should have 'UNKNOWN' as channel_id."""
        config = load_media_config()
        for source in config["sources"]:
            if source.get("enabled") and "youtube" in source.get("type", ""):
                assert "UNKNOWN" not in source["url"], (
                    f"Source {source['id']} has UNKNOWN channel_id and is enabled"
                )


# ---------------------------------------------------------------------------
# YouTube URL helpers
# ---------------------------------------------------------------------------


class TestExtractVideoId:
    def test_standard_watch_url(self):
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert _extract_video_id(url) == "dQw4w9WgXcQ"

    def test_watch_url_with_extra_params(self):
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42s&ab_channel=RickAstley"
        assert _extract_video_id(url) == "dQw4w9WgXcQ"

    def test_shorts_url(self):
        url = "https://www.youtube.com/shorts/zWHQIinOgZI"
        assert _extract_video_id(url) == "zWHQIinOgZI"

    def test_shorts_url_with_query(self):
        url = "https://www.youtube.com/shorts/zWHQIinOgZI?feature=share"
        assert _extract_video_id(url) == "zWHQIinOgZI"

    def test_unrecognized_url_returns_none(self):
        assert _extract_video_id("https://www.youtube.com/channel/UCxxx") is None

    def test_empty_string_returns_none(self):
        assert _extract_video_id("") is None


class TestIsYoutubeShort:
    def test_shorts_url_is_short(self):
        assert _is_youtube_short("https://www.youtube.com/shorts/zWHQIinOgZI") is True

    def test_watch_url_is_not_short(self):
        assert _is_youtube_short("https://www.youtube.com/watch?v=dQw4w9WgXcQ") is False

    def test_empty_string_is_not_short(self):
        assert _is_youtube_short("") is False


# ---------------------------------------------------------------------------
# ingest_from_urls  (Issue #213 — historical backfill)
# ---------------------------------------------------------------------------


class TestIngestFromUrls:
    WEB_URL = "https://example.com/2026-draft-predictions"
    YT_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    @patch(
        "src.media_ingestor._scrape_article_text", return_value="Draft analysis text"
    )
    def test_web_article_creates_media_item(self, mock_scrape, mock_db):
        items = ingest_from_urls([self.WEB_URL], source_id="backfill_test", db=mock_db)
        assert len(items) == 1
        assert items[0].content_type == "article"
        assert items[0].fetch_source_type == "web_scrape"
        assert items[0].source_url == self.WEB_URL

    @patch(
        "src.media_ingestor._scrape_article_text", return_value="Draft analysis text"
    )
    def test_web_article_attaches_pundit(self, mock_scrape, mock_db):
        items = ingest_from_urls(
            [self.WEB_URL],
            source_id="backfill_test",
            pundit_id="adam_schefter",
            pundit_name="Adam Schefter",
            db=mock_db,
        )
        assert items[0].matched_pundit_id == "adam_schefter"
        assert items[0].matched_pundit_name == "Adam Schefter"
        assert items[0].match_method == "source_default"

    @patch("src.media_ingestor._scrape_article_text", return_value=None)
    def test_failed_scrape_is_skipped(self, mock_scrape, mock_db):
        items = ingest_from_urls([self.WEB_URL], source_id="backfill_test", db=mock_db)
        assert len(items) == 0
        mock_db.append_dataframe_to_table.assert_not_called()

    @patch("src.media_ingestor._fetch_transcript", return_value="Transcript text here")
    def test_youtube_url_creates_transcript_item(self, mock_transcript, mock_db):
        items = ingest_from_urls([self.YT_URL], source_id="backfill_yt", db=mock_db)
        assert len(items) == 1
        assert items[0].content_type == "transcript"
        assert items[0].fetch_source_type == "youtube_transcript"

    @patch("src.media_ingestor._fetch_transcript", side_effect=Exception("No captions"))
    def test_youtube_transcript_failure_is_skipped(self, mock_transcript, mock_db):
        items = ingest_from_urls([self.YT_URL], source_id="backfill_yt", db=mock_db)
        assert len(items) == 0
        mock_db.append_dataframe_to_table.assert_not_called()

    @patch("src.media_ingestor._scrape_article_text", return_value="Article text")
    def test_deduplicates_already_seen_url(self, mock_scrape, mock_db):
        content_hash = compute_content_hash(self.WEB_URL)
        mock_db.fetch_df.return_value = pd.DataFrame({"content_hash": [content_hash]})
        items = ingest_from_urls([self.WEB_URL], source_id="backfill_test", db=mock_db)
        assert len(items) == 0
        mock_db.append_dataframe_to_table.assert_not_called()

    @patch("src.media_ingestor._scrape_article_text", return_value="Article text")
    def test_dry_run_does_not_write(self, mock_scrape, mock_db):
        items = ingest_from_urls(
            [self.WEB_URL], source_id="backfill_test", db=mock_db, dry_run=True
        )
        assert len(items) == 1
        mock_db.append_dataframe_to_table.assert_not_called()

    @patch("src.media_ingestor._scrape_article_text", return_value="Article text")
    def test_writes_to_bq_when_new(self, mock_scrape, mock_db):
        mock_db.fetch_df.return_value = pd.DataFrame()
        ingest_from_urls([self.WEB_URL], source_id="backfill_test", db=mock_db)
        mock_db.append_dataframe_to_table.assert_called_once()

    @patch("src.media_ingestor._scrape_article_text", return_value="Article text")
    def test_unmatched_method_when_no_pundit(self, mock_scrape, mock_db):
        items = ingest_from_urls([self.WEB_URL], source_id="backfill_test", db=mock_db)
        assert items[0].match_method == "unmatched"
        assert items[0].matched_pundit_id is None


# ---------------------------------------------------------------------------
# Proxy strategy (Issue #676)
# ---------------------------------------------------------------------------


class TestProxyStrategy:
    """Tests for proxy_required source config and HTTP_PROXY env var routing."""

    PROXY_SOURCE = {
        "id": "proxy_feed",
        "name": "Proxy-Required Feed",
        "type": "rss",
        "url": "https://example.com/proxy-feed",
        "enabled": True,
        "proxy_required": True,
        "pundits": [],
    }
    NON_PROXY_SOURCE = {
        "id": "direct_feed",
        "name": "Direct Feed",
        "type": "rss",
        "url": "https://example.com/direct-feed",
        "enabled": True,
        "proxy_required": False,
        "pundits": [],
    }

    def test_get_proxy_dict_returns_dict_when_env_set(self, monkeypatch):
        """_get_proxy_dict() returns both http and https when HTTP_PROXY is set."""
        import src.media_ingestor as mi

        monkeypatch.setattr(mi, "_HTTP_PROXY", "http://proxy.example.com:8080")
        result = mi._get_proxy_dict()
        assert result == {
            "http": "http://proxy.example.com:8080",
            "https": "http://proxy.example.com:8080",
        }

    def test_get_proxy_dict_returns_none_when_env_unset(self, monkeypatch):
        """_get_proxy_dict() returns None when HTTP_PROXY is not set."""
        import src.media_ingestor as mi

        monkeypatch.setattr(mi, "_HTTP_PROXY", None)
        result = mi._get_proxy_dict()
        assert result is None

    def test_ingest_source_skips_gracefully_when_proxy_required_but_not_configured(
        self, mock_db, monkeypatch
    ):
        """
        When proxy_required=true and HTTP_PROXY is absent, ingest_source records
        a warning error and returns without crashing or fetching.
        """
        import src.media_ingestor as mi

        monkeypatch.setattr(mi, "_HTTP_PROXY", None)
        mock_fetcher = MagicMock()

        with patch.dict("src.media_ingestor.FETCHERS", {"rss": mock_fetcher}):
            result = ingest_source(
                self.PROXY_SOURCE, SAMPLE_CONFIG["defaults"], mock_db
            )

        assert result.error is not None
        assert "HTTP_PROXY" in result.error
        # Fetcher must NOT have been called — no network attempt
        mock_fetcher.assert_not_called()
        mock_db.append_dataframe_to_table.assert_not_called()

    def test_ingest_source_proceeds_when_proxy_required_and_configured(
        self, mock_db, monkeypatch
    ):
        """
        When proxy_required=true and HTTP_PROXY is set, ingest_source calls the fetcher.
        """
        import src.media_ingestor as mi

        monkeypatch.setattr(mi, "_HTTP_PROXY", "http://proxy.example.com:8080")
        mock_fetcher = MagicMock(return_value=[])

        with patch.dict("src.media_ingestor.FETCHERS", {"rss": mock_fetcher}):
            result = ingest_source(
                self.PROXY_SOURCE, SAMPLE_CONFIG["defaults"], mock_db
            )

        assert result.error is None
        mock_fetcher.assert_called_once()

    def test_ingest_source_proceeds_normally_when_proxy_not_required(
        self, mock_db, monkeypatch
    ):
        """
        Sources without proxy_required proceed regardless of HTTP_PROXY.
        """
        import src.media_ingestor as mi

        monkeypatch.setattr(mi, "_HTTP_PROXY", None)
        mock_fetcher = MagicMock(return_value=[])

        with patch.dict("src.media_ingestor.FETCHERS", {"rss": mock_fetcher}):
            result = ingest_source(
                self.NON_PROXY_SOURCE, SAMPLE_CONFIG["defaults"], mock_db
            )

        assert result.error is None
        mock_fetcher.assert_called_once()

    def test_scrape_article_text_passes_proxies_to_requests(self):
        """_scrape_article_text forwards the proxies dict to requests.get."""
        from src.media_ingestor import _scrape_article_text

        proxies = {
            "http": "http://proxy.example.com:8080",
            "https": "http://proxy.example.com:8080",
        }
        captured = {}

        def fake_get(url, timeout=None, headers=None, proxies=None):
            captured["proxies"] = proxies
            raise Exception("stop early — we only care about the call args")

        with patch("src.media_ingestor.requests.get", side_effect=fake_get):
            try:
                _scrape_article_text("https://example.com/article", proxies=proxies)
            except Exception:
                pass

        assert captured.get("proxies") == proxies

    def test_scrape_article_text_no_proxies_by_default(self):
        """_scrape_article_text passes proxies=None when called with default args."""
        from src.media_ingestor import _scrape_article_text

        captured = {}

        def fake_get(url, timeout=None, headers=None, proxies=None):
            captured["proxies"] = proxies
            raise Exception("stop early")

        with patch("src.media_ingestor.requests.get", side_effect=fake_get):
            try:
                _scrape_article_text("https://example.com/article")
            except Exception:
                pass

        assert captured.get("proxies") is None
