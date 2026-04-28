"""
Unit tests for youtube_transcript_ingestor.py (Issue #262).
No BigQuery or real network access required.
"""

import json
from concurrent.futures import Future
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, call

import pytest

from src.youtube_transcript_ingestor import (
    CHANNEL_REGISTRY,
    IngestSummary,
    TranscriptResult,
    VideoMeta,
    _chunk_text,
    _content_hash,
    _extract_video_id,
    _is_short,
    _parse_duration_iso,
    _passes_date_filter,
    _passes_title_filter,
    check_yield,
    fetch_single_transcript,
    fetch_transcripts_parallel,
    ingest_channel,
    ingest_urls,
    list_channel_videos,
)


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


class TestExtractVideoId:
    def test_standard_watch_url(self):
        assert (
            _extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
            == "dQw4w9WgXcQ"
        )

    def test_shortened_url(self):
        assert _extract_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_shorts_url(self):
        assert (
            _extract_video_id("https://www.youtube.com/shorts/dQw4w9WgXcQ")
            == "dQw4w9WgXcQ"
        )

    def test_invalid_url(self):
        assert _extract_video_id("https://example.com/video") is None

    def test_url_with_extra_params(self):
        assert (
            _extract_video_id("https://www.youtube.com/watch?v=abcde12345f&t=120")
            == "abcde12345f"
        )


class TestIsShort:
    def test_shorts_url(self):
        assert _is_short("https://www.youtube.com/shorts/abc123")

    def test_regular_url(self):
        assert not _is_short("https://www.youtube.com/watch?v=abc123")


class TestParseDurationIso:
    def test_full_duration(self):
        assert _parse_duration_iso("PT1H30M45S") == 5445

    def test_minutes_only(self):
        assert _parse_duration_iso("PT45M") == 2700

    def test_hours_and_minutes(self):
        assert _parse_duration_iso("PT2H0M") == 7200

    def test_invalid(self):
        assert _parse_duration_iso("") is None
        assert _parse_duration_iso("bad") is None


class TestTitleFilter:
    def test_prediction_keywords(self):
        assert _passes_title_filter("NFL Week 5 Predictions and Picks")
        assert _passes_title_filter("Bold Calls for the 2025 NFL Season")
        assert _passes_title_filter("Who Wins the Super Bowl?")
        assert _passes_title_filter("MVP Race Breakdown — Week 10")
        assert _passes_title_filter("Fantasy Football Sleeper Picks")
        assert _passes_title_filter("Playoff Preview: AFC Championship")

    def test_non_prediction_titles(self):
        # These are highlights or interviews that don't indicate predictions
        assert not _passes_title_filter("Patrick Mahomes throws 5 TD passes")
        assert not _passes_title_filter("Aaron Rodgers talks about his offseason")

    def test_case_insensitive(self):
        assert _passes_title_filter("PREDICTIONS for Week 1")
        assert _passes_title_filter("nfl draft grades 2024")


class TestDateFilter:
    def test_recent_video(self):
        dt = datetime(2023, 9, 1, tzinfo=timezone.utc)
        assert _passes_date_filter(dt)

    def test_exactly_2020(self):
        dt = datetime(2020, 1, 1, tzinfo=timezone.utc)
        assert _passes_date_filter(dt)

    def test_pre_2020(self):
        dt = datetime(2019, 12, 31, tzinfo=timezone.utc)
        assert not _passes_date_filter(dt)

    def test_none_date(self):
        # Optimistic: don't reject unknowns
        assert _passes_date_filter(None)


class TestChunkText:
    def test_short_text_no_chunking(self):
        text = "This is a short text."
        chunks = _chunk_text(text)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_long_text_splits(self):
        # Create text longer than CHUNK_SIZE (3500)
        text = "This is a sentence. " * 200  # ~4000 chars
        chunks = _chunk_text(text)
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk) <= 3500 + 100  # slight tolerance for boundary

    def test_chunks_preserve_content(self):
        text = "Word " * 1000
        chunks = _chunk_text(text)
        reconstructed = " ".join(chunks)
        # All words present (allow whitespace normalization)
        assert reconstructed.replace("  ", " ").count("Word") == 1000


class TestContentHash:
    def test_reproducible(self):
        h1 = _content_hash("https://youtube.com/watch?v=abc", 0)
        h2 = _content_hash("https://youtube.com/watch?v=abc", 0)
        assert h1 == h2

    def test_different_urls(self):
        h1 = _content_hash("https://youtube.com/watch?v=abc")
        h2 = _content_hash("https://youtube.com/watch?v=xyz")
        assert h1 != h2

    def test_different_chunks(self):
        url = "https://youtube.com/watch?v=abc"
        h0 = _content_hash(url, 0)
        h1 = _content_hash(url, 1)
        assert h0 != h1


# ---------------------------------------------------------------------------
# Channel registry
# ---------------------------------------------------------------------------


class TestChannelRegistry:
    def test_all_entries_have_required_fields(self):
        for ch in CHANNEL_REGISTRY:
            assert "id" in ch, f"Missing id: {ch}"
            assert "name" in ch, f"Missing name: {ch}"
            assert "channel_id" in ch, f"Missing channel_id: {ch}"
            assert "pundits" in ch or "default_pundit" in ch, (
                f"Missing pundit config: {ch}"
            )

    def test_no_duplicate_ids(self):
        ids = [ch["id"] for ch in CHANNEL_REGISTRY]
        assert len(ids) == len(set(ids)), "Duplicate channel IDs found"

    def test_target_channels_present(self):
        ids = {ch["id"] for ch in CHANNEL_REGISTRY}
        required = {
            "pat_mcafee_show",
            "bussin_with_the_boys",
            "brett_kollmann",
            "warren_sharp",
            "locked_on_nfl",
            "pff_nfl",
            "move_the_sticks",
        }
        missing = required - ids
        assert not missing, f"Missing expected channels: {missing}"


# ---------------------------------------------------------------------------
# Transcript fetching
# ---------------------------------------------------------------------------


class TestFetchSingleTranscript:
    @patch("src.youtube_transcript_ingestor._fetch_transcript_yt_api")
    def test_success_via_yt_api(self, mock_api):
        mock_api.return_value = "This is the transcript text."
        result = fetch_single_transcript("abc123")
        assert result.transcript_text == "This is the transcript text."
        assert result.error is None
        assert not result.used_ytdlp

    @patch("src.youtube_transcript_ingestor._fetch_transcript_ytdlp")
    @patch("src.youtube_transcript_ingestor._fetch_transcript_yt_api")
    def test_fallback_to_ytdlp_on_disabled(self, mock_api, mock_ytdlp):
        mock_api.side_effect = Exception("Transcripts disabled")
        mock_ytdlp.return_value = "Fallback transcript text."
        result = fetch_single_transcript("abc123")
        assert result.transcript_text == "Fallback transcript text."
        assert result.used_ytdlp is True
        assert result.error is None

    @patch("src.youtube_transcript_ingestor._fetch_transcript_ytdlp")
    @patch("src.youtube_transcript_ingestor._fetch_transcript_yt_api")
    def test_both_fail(self, mock_api, mock_ytdlp):
        mock_api.side_effect = Exception("Transcripts disabled")
        mock_ytdlp.side_effect = Exception("yt-dlp failed")
        result = fetch_single_transcript("abc123")
        assert result.transcript_text is None
        assert result.error is not None

    @patch("src.youtube_transcript_ingestor._fetch_transcript_ytdlp")
    @patch("src.youtube_transcript_ingestor._fetch_transcript_yt_api")
    def test_non_disabled_error_falls_back_to_ytdlp(self, mock_api, mock_ytdlp):
        """Any yt-api failure (including non-'disabled' errors) should fall back to yt-dlp."""
        mock_api.side_effect = Exception("Network timeout")
        mock_ytdlp.return_value = "Fallback transcript."
        result = fetch_single_transcript("abc123")
        mock_ytdlp.assert_called_once()
        assert result.transcript_text == "Fallback transcript."
        assert result.used_ytdlp is True

    @patch("src.youtube_transcript_ingestor._fetch_transcript_ytdlp")
    @patch("src.youtube_transcript_ingestor._fetch_transcript_yt_api")
    def test_both_fail_error_includes_both_causes(self, mock_api, mock_ytdlp):
        """When both yt-api and yt-dlp fail, error message should include both causes."""
        mock_api.side_effect = Exception("Network timeout")
        mock_ytdlp.side_effect = Exception("yt-dlp connection refused")
        result = fetch_single_transcript("abc123")
        assert result.transcript_text is None
        assert result.error is not None
        assert "yt-api" in result.error
        assert "yt-dlp" in result.error


class TestFetchTranscriptsParallel:
    @patch("src.youtube_transcript_ingestor.fetch_single_transcript")
    def test_parallel_fetch(self, mock_fetch):
        mock_fetch.side_effect = lambda vid: TranscriptResult(
            video_id=vid,
            url=f"https://youtube.com/watch?v={vid}",
            transcript_text=f"Transcript for {vid}",
        )
        results = fetch_transcripts_parallel(["abc", "def", "ghi"])
        assert len(results) == 3
        assert all(r.transcript_text for r in results)

    @patch("src.youtube_transcript_ingestor.fetch_single_transcript")
    def test_parallel_with_failures(self, mock_fetch):
        def side_effect(vid):
            if vid == "fail":
                return TranscriptResult(
                    video_id=vid, url="", transcript_text=None, error="error"
                )
            return TranscriptResult(video_id=vid, url="", transcript_text="ok")

        mock_fetch.side_effect = side_effect
        results = fetch_transcripts_parallel(["ok1", "fail", "ok2"])
        successes = [r for r in results if r.transcript_text]
        failures = [r for r in results if not r.transcript_text]
        assert len(successes) == 2
        assert len(failures) == 1


# ---------------------------------------------------------------------------
# Channel feed parsing
# ---------------------------------------------------------------------------


class TestListChannelVideos:
    def _make_entry(self, title, link, year=2024):
        """Create a feedparser-compatible entry mock."""
        entry = MagicMock()
        # feedparser entries use .get() like a dict
        data = {"title": title, "link": link}
        entry.get.side_effect = lambda k, d="": data.get(k, d)
        entry.published_parsed = (year, 9, 1, 12, 0, 0, 0, 0, 0)
        return entry

    # YouTube video IDs must be exactly 11 alphanumeric chars
    _PRED_VID = "pred001zzzz"  # 11 chars
    _HILIT_VID = "hilit1zzzz0"  # 11 chars
    _BOLD_VID = "bold001zzzz"  # 11 chars
    _SHORT_VID = "short001zzz"  # 11 chars (in /shorts/ path)
    _FULL_VID = "full001zzzz"  # 11 chars
    _OLD_VID = "old001zzzzz"  # 11 chars
    _NEW_VID = "new001zzzzz"  # 11 chars

    @patch("src.youtube_transcript_ingestor.feedparser.parse")
    def test_title_filter_applied(self, mock_parse):
        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.entries = [
            self._make_entry(
                "NFL Week 5 Predictions",
                f"https://www.youtube.com/watch?v={self._PRED_VID}",
            ),
            self._make_entry(
                "Highlight reel compilation",
                f"https://www.youtube.com/watch?v={self._HILIT_VID}",
            ),
            self._make_entry(
                "Bold Calls for Super Bowl",
                f"https://www.youtube.com/watch?v={self._BOLD_VID}",
            ),
        ]
        mock_parse.return_value = mock_feed

        videos, skipped = list_channel_videos(
            channel_id="UCtest",
            source_id="test",
            pundit_id=None,
            pundit_name=None,
            title_filter=True,
        )
        assert len(videos) == 2  # pred001 and bold001 pass
        assert skipped == 1

    @patch("src.youtube_transcript_ingestor.feedparser.parse")
    def test_shorts_skipped(self, mock_parse):
        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.entries = [
            self._make_entry(
                "NFL Predictions", f"https://www.youtube.com/shorts/{self._SHORT_VID}"
            ),
            self._make_entry(
                "NFL Predictions Full",
                f"https://www.youtube.com/watch?v={self._FULL_VID}",
            ),
        ]
        mock_parse.return_value = mock_feed

        videos, _ = list_channel_videos(
            channel_id="UCtest",
            source_id="test",
            pundit_id=None,
            pundit_name=None,
            title_filter=True,
        )
        assert len(videos) == 1
        assert videos[0].video_id == self._FULL_VID

    @patch("src.youtube_transcript_ingestor.feedparser.parse")
    def test_date_filter_applied(self, mock_parse):
        mock_feed = MagicMock()
        mock_feed.bozo = False
        e1 = self._make_entry(
            "NFL Predictions 2019",
            f"https://www.youtube.com/watch?v={self._OLD_VID}",
            year=2019,
        )
        e2 = self._make_entry(
            "NFL Predictions 2023",
            f"https://www.youtube.com/watch?v={self._NEW_VID}",
            year=2023,
        )
        mock_feed.entries = [e1, e2]
        mock_parse.return_value = mock_feed

        videos, _ = list_channel_videos(
            channel_id="UCtest",
            source_id="test",
            pundit_id=None,
            pundit_name=None,
            title_filter=True,
        )
        assert len(videos) == 1
        assert videos[0].video_id == self._NEW_VID


# ---------------------------------------------------------------------------
# Ingest channel
# ---------------------------------------------------------------------------


class TestIngestChannel:
    def _make_channel_cfg(self):
        return {
            "id": "test_channel",
            "name": "Test Channel",
            "channel_id": "UCtest123",
            "pundits": [{"id": "test_pundit", "name": "Test Pundit"}],
            "enabled": True,
        }

    @patch("src.youtube_transcript_ingestor.fetch_transcripts_parallel")
    @patch("src.youtube_transcript_ingestor.list_channel_videos")
    def test_dry_run_no_bq_writes(self, mock_list, mock_fetch):
        mock_list.return_value = (
            [
                VideoMeta(
                    video_id="abc123",
                    url="https://youtube.com/watch?v=abc123",
                    title="NFL Predictions Week 5",
                    published_at=datetime(2024, 9, 1, tzinfo=timezone.utc),
                    channel_id="UCtest",
                    source_id="test_channel",
                    pundit_id="test_pundit",
                    pundit_name="Test Pundit",
                )
            ],
            0,
        )
        mock_fetch.return_value = [
            TranscriptResult(
                video_id="abc123",
                url="https://youtube.com/watch?v=abc123",
                transcript_text="The Chiefs will win the Super Bowl this year.",
            )
        ]

        mock_db = MagicMock()
        summary = ingest_channel(self._make_channel_cfg(), db=mock_db, dry_run=True)

        assert summary.items_written == 1
        mock_db.append_dataframe_to_table.assert_not_called()

    @patch("src.youtube_transcript_ingestor.fetch_transcripts_parallel")
    @patch("src.youtube_transcript_ingestor.list_channel_videos")
    def test_bq_write_on_live_run(self, mock_list, mock_fetch):
        mock_list.return_value = (
            [
                VideoMeta(
                    video_id="xyz789",
                    url="https://youtube.com/watch?v=xyz789",
                    title="Bold Playoff Picks",
                    published_at=datetime(2024, 10, 1, tzinfo=timezone.utc),
                    channel_id="UCtest",
                    source_id="test_channel",
                    pundit_id="test_pundit",
                    pundit_name="Test Pundit",
                )
            ],
            0,
        )
        mock_fetch.return_value = [
            TranscriptResult(
                video_id="xyz789",
                url="https://youtube.com/watch?v=xyz789",
                transcript_text="I predict the Eagles will beat the Rams.",
            )
        ]

        mock_db = MagicMock()
        mock_db.fetch_df.return_value = __import__(
            "pandas"
        ).DataFrame()  # no existing hashes

        summary = ingest_channel(self._make_channel_cfg(), db=mock_db, dry_run=False)

        assert summary.items_written == 1
        mock_db.append_dataframe_to_table.assert_called_once()

    @patch("src.youtube_transcript_ingestor.fetch_transcripts_parallel")
    @patch("src.youtube_transcript_ingestor.list_channel_videos")
    def test_dedup_skips_existing(self, mock_list, mock_fetch):
        url = "https://youtube.com/watch?v=dedup01"
        existing_hash = _content_hash(url, 0)

        mock_list.return_value = (
            [
                VideoMeta(
                    video_id="dedup01",
                    url=url,
                    title="NFL Playoff Predictions",
                    published_at=datetime(2024, 9, 1, tzinfo=timezone.utc),
                    channel_id="UCtest",
                    source_id="test_channel",
                    pundit_id="test_pundit",
                    pundit_name="Test Pundit",
                )
            ],
            0,
        )

        import pandas as pd

        mock_db = MagicMock()
        mock_db.fetch_df.return_value = pd.DataFrame({"content_hash": [existing_hash]})

        summary = ingest_channel(self._make_channel_cfg(), db=mock_db, dry_run=False)

        # Should be skipped before transcript fetch
        mock_fetch.assert_not_called()
        assert summary.videos_skipped_dedup == 1
        assert summary.items_written == 0

    @patch("src.youtube_transcript_ingestor.list_channel_videos")
    def test_feed_error_returns_summary_with_error(self, mock_list):
        mock_list.side_effect = Exception("Feed parse failed")
        summary = ingest_channel(self._make_channel_cfg(), db=None, dry_run=True)
        assert summary.error is not None
        assert "Feed parse failed" in summary.error


# ---------------------------------------------------------------------------
# Ingest from explicit URLs
# ---------------------------------------------------------------------------


class TestIngestUrls:
    # Use full www.youtube.com URLs so _extract_video_id regex matches (exactly 11 chars)
    _URL1 = "https://www.youtube.com/watch?v=urlvid1zzzz"
    _URL2 = "https://www.youtube.com/watch?v=dryrun1zzzz"
    _VID1 = "urlvid1zzzz"
    _VID2 = "dryrun1zzzz"

    @patch("src.youtube_transcript_ingestor.fetch_transcripts_parallel")
    def test_basic_url_ingestion(self, mock_fetch):
        mock_fetch.return_value = [
            TranscriptResult(
                video_id=self._VID1,
                url=self._URL1,
                transcript_text="This is a great transcript about NFL predictions.",
            )
        ]
        mock_db = MagicMock()
        mock_db.fetch_df.return_value = __import__("pandas").DataFrame()

        summary = ingest_urls(
            urls=[self._URL1],
            source_id="test_backfill",
            db=mock_db,
            dry_run=False,
        )
        assert summary.transcripts_fetched == 1
        assert summary.items_written == 1

    @patch("src.youtube_transcript_ingestor.fetch_transcripts_parallel")
    def test_shorts_skipped(self, mock_fetch):
        summary = ingest_urls(
            urls=["https://www.youtube.com/shorts/shortid1"],
            source_id="test_backfill",
            db=None,
            dry_run=True,
        )
        mock_fetch.assert_not_called()
        assert summary.items_written == 0

    @patch("src.youtube_transcript_ingestor.fetch_transcripts_parallel")
    def test_dry_run_no_bq(self, mock_fetch):
        mock_fetch.return_value = [
            TranscriptResult(
                video_id=self._VID2,
                url=self._URL2,
                transcript_text="Lots of NFL predictions here.",
            )
        ]
        mock_db = MagicMock()
        summary = ingest_urls(
            urls=[self._URL2],
            source_id="test_backfill",
            db=mock_db,
            dry_run=True,
        )
        mock_db.append_dataframe_to_table.assert_not_called()
        assert summary.items_written == 1


# ---------------------------------------------------------------------------
# Yield monitor
# ---------------------------------------------------------------------------


class TestCheckYield:
    def test_low_yield_warning(self, caplog):
        summaries = [
            IngestSummary(
                source_id="s1", transcripts_fetched=10, predictions_extracted=5
            )
        ]
        import logging

        with caplog.at_level(logging.WARNING):
            check_yield(summaries)
        assert "Low extraction yield" in caplog.text

    def test_good_yield_no_warning(self, caplog):
        summaries = [
            IngestSummary(
                source_id="s1", transcripts_fetched=10, predictions_extracted=30
            )
        ]
        import logging

        with caplog.at_level(logging.WARNING):
            check_yield(summaries)
        assert "Low extraction yield" not in caplog.text

    def test_zero_transcripts_no_crash(self):
        summaries = [IngestSummary(source_id="s1", transcripts_fetched=0)]
        check_yield(summaries)  # should not raise
