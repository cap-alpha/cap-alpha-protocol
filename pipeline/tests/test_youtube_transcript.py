"""
Tests for YouTube transcript fetcher (Issue #126).
Unit tests — no network access required.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.media_ingestor import (
    MediaItem,
    _chunk_transcript,
    _extract_video_id,
    compute_content_hash,
    fetch_youtube_transcripts,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

YOUTUBE_SOURCE = {
    "id": "pat_mcafee_show",
    "name": "The Pat McAfee Show",
    "sport": "NFL",
    "type": "youtube_transcript",
    "url": (
        "https://www.youtube.com/feeds/videos.xml?channel_id=UCxcTeAKWJca6XyJ37_ZoKIQ"
    ),
    "enabled": True,
    "pundits": [
        {
            "id": "pat_mcafee",
            "name": "Pat McAfee",
            "match_authors": ["Pat McAfee"],
        }
    ],
}

DEFAULTS = {
    "fetch_timeout_seconds": 10,
    "max_retries": 2,
    "retry_backoff_seconds": 0,
    "max_items_per_feed": 10,
    "dedup_window_days": 7,
}


def _make_feed_entry(
    title="Test Video",
    link="https://www.youtube.com/watch?v=abc12345678",
):
    entry = MagicMock()
    entry.get = lambda k, d=None: {"title": title, "link": link}.get(k, d)
    entry.title = title
    entry.link = link
    entry.published_parsed = (2025, 9, 1, 12, 0, 0, 0, 0, 0)
    return entry


def _make_feed(entries):
    feed = MagicMock()
    feed.bozo = False
    feed.entries = entries
    return feed


# ---------------------------------------------------------------------------
# Video ID extraction
# ---------------------------------------------------------------------------


class TestExtractVideoId:
    def test_standard_url(self):
        assert (
            _extract_video_id("https://www.youtube.com/watch?v=abc12345678")
            == "abc12345678"
        )

    def test_url_with_extra_params(self):
        assert (
            _extract_video_id("https://www.youtube.com/watch?v=abc12345678&t=120")
            == "abc12345678"
        )

    def test_no_video_id(self):
        assert _extract_video_id("https://www.youtube.com/channel/UCxyz") is None

    def test_short_id_rejected(self):
        # Video IDs are exactly 11 characters
        assert _extract_video_id("https://www.youtube.com/watch?v=short") is None


# ---------------------------------------------------------------------------
# Transcript chunking
# ---------------------------------------------------------------------------


class TestChunkTranscript:
    def test_short_text_no_chunking(self):
        text = "This is a short transcript."
        chunks = _chunk_transcript(text, max_chars=3500)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_long_text_chunked(self):
        # Create text > 3500 chars
        sentences = ["This is sentence number %d." % i for i in range(200)]
        text = " ".join(sentences)
        assert len(text) > 3500

        chunks = _chunk_transcript(text, max_chars=3500)
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk) <= 3500

    def test_all_text_preserved(self):
        sentences = ["Sentence %d is here." % i for i in range(200)]
        text = " ".join(sentences)
        chunks = _chunk_transcript(text, max_chars=3500)
        # Rejoin and verify all content is present
        rejoined = " ".join(chunks)
        # All original sentences should appear
        for s in sentences:
            assert s in rejoined

    def test_splits_at_sentence_boundary(self):
        # Build text that forces a split
        text = "First sentence. " * 100 + "Last sentence."
        chunks = _chunk_transcript(text, max_chars=500)
        assert len(chunks) > 1
        # Each chunk should end at a sentence boundary (or be the last chunk)
        for chunk in chunks[:-1]:
            assert chunk.rstrip().endswith(".")

    def test_exact_size_no_split(self):
        text = "a" * 3500
        chunks = _chunk_transcript(text, max_chars=3500)
        assert len(chunks) == 1

    def test_10000_chars_produces_multiple_chunks(self):
        text = "Word. " * 2000  # ~12000 chars
        chunks = _chunk_transcript(text, max_chars=3500)
        assert len(chunks) >= 3


# ---------------------------------------------------------------------------
# fetch_youtube_transcripts
# ---------------------------------------------------------------------------


class TestFetchYoutubeTranscripts:
    @patch("src.media_ingestor._YT_API_V1", False)
    @patch("src.media_ingestor.YouTubeTranscriptApi")
    @patch("src.media_ingestor.feedparser")
    def test_returns_media_items(self, mock_fp, mock_yt_api):
        entry = _make_feed_entry()
        mock_fp.parse.return_value = _make_feed([entry])
        mock_yt_api.get_transcript.return_value = [
            {"text": "Hello everyone", "start": 0.0, "duration": 2.0},
            {"text": "welcome to the show", "start": 2.0, "duration": 3.0},
        ]

        items = fetch_youtube_transcripts(YOUTUBE_SOURCE, DEFAULTS)

        assert len(items) == 1
        assert isinstance(items[0], MediaItem)
        assert items[0].source_id == "pat_mcafee_show"
        assert items[0].content_type == "transcript"
        assert items[0].fetch_source_type == "youtube_transcript"
        assert items[0].raw_text == "Hello everyone welcome to the show"

    @patch("src.media_ingestor._YT_API_V1", False)
    @patch("src.media_ingestor.YouTubeTranscriptApi")
    @patch("src.media_ingestor.feedparser")
    def test_pundit_fields_set_from_source(self, mock_fp, mock_yt_api):
        entry = _make_feed_entry()
        mock_fp.parse.return_value = _make_feed([entry])
        mock_yt_api.get_transcript.return_value = [
            {"text": "test content", "start": 0.0, "duration": 1.0},
        ]

        items = fetch_youtube_transcripts(YOUTUBE_SOURCE, DEFAULTS)

        assert items[0].matched_pundit_id == "pat_mcafee"
        assert items[0].matched_pundit_name == "Pat McAfee"
        assert items[0].author == "Pat McAfee"

    @patch("src.media_ingestor._YT_API_V1", False)
    @patch("src.media_ingestor.YouTubeTranscriptApi")
    @patch("src.media_ingestor.feedparser")
    def test_transcript_unavailable_skips_video(self, mock_fp, mock_yt_api):
        entry = _make_feed_entry()
        mock_fp.parse.return_value = _make_feed([entry])
        mock_yt_api.get_transcript.side_effect = Exception("Subtitles disabled")

        items = fetch_youtube_transcripts(YOUTUBE_SOURCE, DEFAULTS)

        assert len(items) == 0

    @patch("src.media_ingestor._YT_API_V1", False)
    @patch("src.media_ingestor.YouTubeTranscriptApi")
    @patch("src.media_ingestor.feedparser")
    def test_chunked_transcript_produces_multiple_items(self, mock_fp, mock_yt_api):
        entry = _make_feed_entry(title="Long Video")
        mock_fp.parse.return_value = _make_feed([entry])

        # Generate a long transcript (~10000 chars)
        segments = [
            {"text": f"This is segment number {i}.", "start": float(i), "duration": 1.0}
            for i in range(500)
        ]
        mock_yt_api.get_transcript.return_value = segments

        items = fetch_youtube_transcripts(YOUTUBE_SOURCE, DEFAULTS)

        assert len(items) > 1
        # Check titles include part numbers
        assert items[0].title == "Long Video (part 1)"
        assert items[1].title == "Long Video (part 2)"

    @patch("src.media_ingestor._YT_API_V1", False)
    @patch("src.media_ingestor.YouTubeTranscriptApi")
    @patch("src.media_ingestor.feedparser")
    def test_chunked_content_hash_includes_chunk_suffix(self, mock_fp, mock_yt_api):
        entry = _make_feed_entry(title="Long Video")
        mock_fp.parse.return_value = _make_feed([entry])

        segments = [
            {"text": f"This is segment number {i}.", "start": float(i), "duration": 1.0}
            for i in range(500)
        ]
        mock_yt_api.get_transcript.return_value = segments

        items = fetch_youtube_transcripts(YOUTUBE_SOURCE, DEFAULTS)

        # All hashes should be unique
        hashes = [item.content_hash for item in items]
        assert len(hashes) == len(set(hashes))

        # Verify chunk 0 hash uses chunk suffix
        video_url = "https://www.youtube.com/watch?v=abc12345678"
        expected_hash_0 = compute_content_hash(video_url + "|chunk_0")
        assert items[0].content_hash == expected_hash_0

    @patch("src.media_ingestor._YT_API_V1", False)
    @patch("src.media_ingestor.YouTubeTranscriptApi")
    @patch("src.media_ingestor.feedparser")
    def test_single_item_no_chunk_suffix(self, mock_fp, mock_yt_api):
        entry = _make_feed_entry()
        mock_fp.parse.return_value = _make_feed([entry])
        mock_yt_api.get_transcript.return_value = [
            {"text": "Short video.", "start": 0.0, "duration": 1.0},
        ]

        items = fetch_youtube_transcripts(YOUTUBE_SOURCE, DEFAULTS)

        assert len(items) == 1
        # No chunk suffix for single items
        video_url = "https://www.youtube.com/watch?v=abc12345678"
        expected_hash = compute_content_hash(video_url)
        assert items[0].content_hash == expected_hash
        assert items[0].title == "Test Video"  # no "(part 1)"

    @patch("src.media_ingestor.feedparser")
    def test_feed_parse_error_raises(self, mock_fp):
        feed = _make_feed([])
        feed.bozo = True
        feed.bozo_exception = "XML parse error"
        mock_fp.parse.return_value = feed

        with pytest.raises(ValueError, match="Feed parse error"):
            fetch_youtube_transcripts(YOUTUBE_SOURCE, DEFAULTS)

    @patch("src.media_ingestor._YT_API_V1", False)
    @patch("src.media_ingestor.YouTubeTranscriptApi")
    @patch("src.media_ingestor.feedparser")
    def test_sport_field_from_source(self, mock_fp, mock_yt_api):
        entry = _make_feed_entry()
        mock_fp.parse.return_value = _make_feed([entry])
        mock_yt_api.get_transcript.return_value = [
            {"text": "test", "start": 0.0, "duration": 1.0},
        ]

        items = fetch_youtube_transcripts(YOUTUBE_SOURCE, DEFAULTS)
        assert items[0].sport == "NFL"

    @patch("src.media_ingestor._YT_API_V1", False)
    @patch("src.media_ingestor.YouTubeTranscriptApi")
    @patch("src.media_ingestor.feedparser")
    def test_multiple_videos_some_without_transcripts(self, mock_fp, mock_yt_api):
        entries = [
            _make_feed_entry(
                title="Video 1", link="https://www.youtube.com/watch?v=vid00000001"
            ),
            _make_feed_entry(
                title="Video 2", link="https://www.youtube.com/watch?v=vid00000002"
            ),
            _make_feed_entry(
                title="Video 3", link="https://www.youtube.com/watch?v=vid00000003"
            ),
        ]
        mock_fp.parse.return_value = _make_feed(entries)

        def side_effect(video_id):
            if video_id == "vid00000002":
                raise Exception("Subtitles disabled")
            return [
                {"text": f"Transcript for {video_id}", "start": 0.0, "duration": 1.0}
            ]

        mock_yt_api.get_transcript.side_effect = side_effect

        items = fetch_youtube_transcripts(YOUTUBE_SOURCE, DEFAULTS)

        # Video 2 should be skipped
        assert len(items) == 2
        assert "vid00000001" in items[0].raw_text
        assert "vid00000003" in items[1].raw_text
