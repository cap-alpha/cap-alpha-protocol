"""
Tests for YouTube Data API v3 client (Issue #382).
Unit tests — no real network calls or API keys required.
"""

import os
from unittest.mock import MagicMock, patch

import pytest
import requests

from src.youtube_client import (
    MAX_DESCRIPTION_CHARS,
    _api_key_available,
    _get_api_key,
    build_video_text,
    fetch_video_description,
    fetch_youtube_videos,
)


# ---------------------------------------------------------------------------
# API key helpers
# ---------------------------------------------------------------------------


class TestApiKeyHelpers:
    def test_get_api_key_returns_env_var(self):
        with patch.dict(os.environ, {"YOUTUBE_API_KEY": "test_key_123"}):
            assert _get_api_key() == "test_key_123"

    def test_get_api_key_returns_none_when_not_set(self):
        env = {k: v for k, v in os.environ.items() if k != "YOUTUBE_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            assert _get_api_key() is None

    def test_api_key_available_true_when_set(self):
        with patch.dict(os.environ, {"YOUTUBE_API_KEY": "some_key"}):
            assert _api_key_available() is True

    def test_api_key_available_false_when_not_set(self):
        env = {k: v for k, v in os.environ.items() if k != "YOUTUBE_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            assert _api_key_available() is False

    def test_api_key_available_false_for_empty_string(self):
        with patch.dict(os.environ, {"YOUTUBE_API_KEY": ""}):
            assert _api_key_available() is False


# ---------------------------------------------------------------------------
# fetch_youtube_videos
# ---------------------------------------------------------------------------


class TestFetchYoutubeVideos:
    CHANNEL_ID = "UCa5oCHMV7ImHb6FxJGqz9cQ"

    def _mock_search_response(self):
        return {
            "kind": "youtube#searchListResponse",
            "items": [
                {
                    "id": {"videoId": "abc12345678"},
                    "snippet": {
                        "title": "Pat McAfee Show April 28 2026",
                        "description": "Travis Hunter goes #1 to Jacksonville",
                        "publishedAt": "2026-04-28T12:00:00Z",
                        "channelId": self.CHANNEL_ID,
                        "channelTitle": "The Pat McAfee Show",
                    },
                },
                {
                    "id": {"videoId": "def12345678"},
                    "snippet": {
                        "title": "McAfee Show April 27",
                        "description": "I think the Bears take Shedeur Sanders",
                        "publishedAt": "2026-04-27T12:00:00Z",
                        "channelId": self.CHANNEL_ID,
                        "channelTitle": "The Pat McAfee Show",
                    },
                },
            ],
        }

    def test_raises_without_api_key(self):
        env = {k: v for k, v in os.environ.items() if k != "YOUTUBE_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValueError, match="YOUTUBE_API_KEY"):
                fetch_youtube_videos(self.CHANNEL_ID)

    @patch("src.youtube_client.requests.get")
    def test_returns_video_list(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = self._mock_search_response()
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        with patch.dict(os.environ, {"YOUTUBE_API_KEY": "test_key"}):
            videos = fetch_youtube_videos(self.CHANNEL_ID)

        assert len(videos) == 2
        assert videos[0]["video_id"] == "abc12345678"
        assert videos[0]["title"] == "Pat McAfee Show April 28 2026"
        assert videos[0]["url"] == "https://www.youtube.com/watch?v=abc12345678"
        assert videos[0]["channel_id"] == self.CHANNEL_ID

    @patch("src.youtube_client.requests.get")
    def test_passes_correct_params(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"items": []}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        with patch.dict(os.environ, {"YOUTUBE_API_KEY": "my_key"}):
            fetch_youtube_videos(self.CHANNEL_ID, max_results=5)

        call_kwargs = mock_get.call_args
        params = call_kwargs[1]["params"]
        assert params["key"] == "my_key"
        assert params["channelId"] == self.CHANNEL_ID
        assert params["maxResults"] == 5
        assert params["type"] == "video"
        assert params["order"] == "date"

    @patch("src.youtube_client.requests.get")
    def test_skips_items_without_video_id(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "items": [
                {"id": {}, "snippet": {"title": "No video ID here", "description": ""}},
                {
                    "id": {"videoId": "abc12345678"},
                    "snippet": {
                        "title": "Valid video",
                        "description": "text",
                        "publishedAt": "2026-04-28T12:00:00Z",
                        "channelId": self.CHANNEL_ID,
                        "channelTitle": "Channel",
                    },
                },
            ]
        }
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        with patch.dict(os.environ, {"YOUTUBE_API_KEY": "test_key"}):
            videos = fetch_youtube_videos(self.CHANNEL_ID)

        assert len(videos) == 1
        assert videos[0]["video_id"] == "abc12345678"

    @patch("src.youtube_client.requests.get")
    def test_empty_items_returns_empty_list(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"items": []}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        with patch.dict(os.environ, {"YOUTUBE_API_KEY": "test_key"}):
            videos = fetch_youtube_videos(self.CHANNEL_ID)

        assert videos == []

    @patch("src.youtube_client.requests.get")
    def test_raises_on_http_error(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = requests.HTTPError("403 Forbidden")
        mock_get.return_value = mock_resp

        with patch.dict(os.environ, {"YOUTUBE_API_KEY": "test_key"}):
            with pytest.raises(requests.HTTPError):
                fetch_youtube_videos(self.CHANNEL_ID)


# ---------------------------------------------------------------------------
# fetch_video_description
# ---------------------------------------------------------------------------


class TestFetchVideoDescription:
    VIDEO_ID = "abc12345678"

    def _mock_videos_response(self, description="Draft predictions for 2026"):
        return {
            "kind": "youtube#videoListResponse",
            "items": [
                {
                    "snippet": {
                        "title": "Mock Video Title",
                        "description": description,
                        "publishedAt": "2026-04-28T12:00:00Z",
                        "channelId": "UCa5oCHMV7ImHb6FxJGqz9cQ",
                        "channelTitle": "Test Channel",
                    }
                }
            ],
        }

    def test_raises_without_api_key(self):
        env = {k: v for k, v in os.environ.items() if k != "YOUTUBE_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValueError, match="YOUTUBE_API_KEY"):
                fetch_video_description(self.VIDEO_ID)

    @patch("src.youtube_client.requests.get")
    def test_returns_video_dict(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = self._mock_videos_response()
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        with patch.dict(os.environ, {"YOUTUBE_API_KEY": "test_key"}):
            result = fetch_video_description(self.VIDEO_ID)

        assert result["video_id"] == self.VIDEO_ID
        assert result["title"] == "Mock Video Title"
        assert result["description"] == "Draft predictions for 2026"
        assert result["url"] == f"https://www.youtube.com/watch?v={self.VIDEO_ID}"

    @patch("src.youtube_client.requests.get")
    def test_truncates_long_description(self, mock_get):
        long_desc = "x" * (MAX_DESCRIPTION_CHARS + 500)
        mock_resp = MagicMock()
        mock_resp.json.return_value = self._mock_videos_response(description=long_desc)
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        with patch.dict(os.environ, {"YOUTUBE_API_KEY": "test_key"}):
            result = fetch_video_description(self.VIDEO_ID)

        assert len(result["description"]) == MAX_DESCRIPTION_CHARS

    @patch("src.youtube_client.requests.get")
    def test_raises_when_video_not_found(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"items": []}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        with patch.dict(os.environ, {"YOUTUBE_API_KEY": "test_key"}):
            with pytest.raises(ValueError, match="Video not found"):
                fetch_video_description(self.VIDEO_ID)

    @patch("src.youtube_client.requests.get")
    def test_passes_correct_params(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = self._mock_videos_response()
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        with patch.dict(os.environ, {"YOUTUBE_API_KEY": "my_key"}):
            fetch_video_description(self.VIDEO_ID)

        call_kwargs = mock_get.call_args
        params = call_kwargs[1]["params"]
        assert params["key"] == "my_key"
        assert params["id"] == self.VIDEO_ID
        assert params["part"] == "snippet"


# ---------------------------------------------------------------------------
# build_video_text
# ---------------------------------------------------------------------------


class TestBuildVideoText:
    def test_combines_title_and_description(self):
        video = {
            "title": "Pat McAfee Show Predictions",
            "description": "I have Travis Hunter going #1 to Jacksonville",
        }
        text = build_video_text(video)
        assert "Pat McAfee Show Predictions" in text
        assert "Travis Hunter" in text

    def test_title_only_when_no_description(self):
        video = {"title": "Test Title", "description": ""}
        text = build_video_text(video)
        assert text == "Test Title"

    def test_description_only_when_no_title(self):
        video = {"title": "", "description": "Big predictions here"}
        text = build_video_text(video)
        assert text == "Big predictions here"

    def test_empty_video_returns_empty_string(self):
        video = {"title": "", "description": ""}
        text = build_video_text(video)
        assert text == ""

    def test_separator_between_title_and_description(self):
        video = {"title": "Title", "description": "Description"}
        text = build_video_text(video)
        assert text == "Title\n\nDescription"


# ---------------------------------------------------------------------------
# fetch_youtube_data_api (integration with media_ingestor)
# ---------------------------------------------------------------------------


class TestFetchYoutubeDataApiIngestor:
    """Tests for the ingestor-level wrapper that calls youtube_client."""

    YOUTUBE_SOURCE = {
        "id": "pat_mcafee_show",
        "name": "The Pat McAfee Show",
        "sport": "NFL",
        "type": "youtube_data_api",
        "channel_id": "UCa5oCHMV7ImHb6FxJGqz9cQ",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCa5oCHMV7ImHb6FxJGqz9cQ",
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

    def test_returns_empty_list_when_no_api_key(self):
        from src.media_ingestor import fetch_youtube_data_api

        env = {k: v for k, v in os.environ.items() if k != "YOUTUBE_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            items = fetch_youtube_data_api(self.YOUTUBE_SOURCE, self.DEFAULTS)

        assert items == []

    @patch("src.media_ingestor.fetch_youtube_videos")
    def test_returns_media_items_from_videos(self, mock_fetch):
        from src.media_ingestor import MediaItem, fetch_youtube_data_api

        mock_fetch.return_value = [
            {
                "video_id": "abc12345678",
                "title": "McAfee Show Draft Predictions",
                "description": "I have Cam Ward going #1 to Tennessee",
                "published_at": "2026-04-28T12:00:00Z",
                "channel_id": "UCa5oCHMV7ImHb6FxJGqz9cQ",
                "channel_title": "The Pat McAfee Show",
                "url": "https://www.youtube.com/watch?v=abc12345678",
            }
        ]

        with patch.dict(os.environ, {"YOUTUBE_API_KEY": "test_key"}):
            items = fetch_youtube_data_api(self.YOUTUBE_SOURCE, self.DEFAULTS)

        assert len(items) == 1
        item = items[0]
        assert isinstance(item, MediaItem)
        assert item.source_id == "pat_mcafee_show"
        assert item.content_type == "video"
        assert item.fetch_source_type == "youtube_data_api"
        assert item.matched_pundit_id == "pat_mcafee"
        assert item.matched_pundit_name == "Pat McAfee"
        assert "McAfee Show Draft Predictions" in item.title
        assert "Cam Ward" in item.raw_text

    @patch("src.media_ingestor.fetch_youtube_videos")
    def test_skips_youtube_shorts(self, mock_fetch):
        from src.media_ingestor import fetch_youtube_data_api

        mock_fetch.return_value = [
            {
                "video_id": "abc12345678",
                "title": "Short Clip",
                "description": "A short clip",
                "published_at": "2026-04-28T12:00:00Z",
                "channel_id": "UCa5oCHMV7ImHb6FxJGqz9cQ",
                "channel_title": "Channel",
                "url": "https://www.youtube.com/shorts/abc12345678",
            }
        ]

        with patch.dict(os.environ, {"YOUTUBE_API_KEY": "test_key"}):
            items = fetch_youtube_data_api(self.YOUTUBE_SOURCE, self.DEFAULTS)

        assert items == []

    @patch("src.media_ingestor.fetch_youtube_videos")
    def test_returns_empty_when_no_videos(self, mock_fetch):
        from src.media_ingestor import fetch_youtube_data_api

        mock_fetch.return_value = []

        with patch.dict(os.environ, {"YOUTUBE_API_KEY": "test_key"}):
            items = fetch_youtube_data_api(self.YOUTUBE_SOURCE, self.DEFAULTS)

        assert items == []

    @patch("src.media_ingestor.fetch_youtube_videos")
    def test_channel_id_extracted_from_url_when_missing(self, mock_fetch):
        from src.media_ingestor import fetch_youtube_data_api

        source_no_channel_id = {**self.YOUTUBE_SOURCE}
        del source_no_channel_id["channel_id"]

        mock_fetch.return_value = []

        with patch.dict(os.environ, {"YOUTUBE_API_KEY": "test_key"}):
            fetch_youtube_data_api(source_no_channel_id, self.DEFAULTS)

        # Should have called with the channel_id extracted from the URL
        called_channel_id = mock_fetch.call_args[1]["channel_id"]
        assert called_channel_id == "UCa5oCHMV7ImHb6FxJGqz9cQ"

    @patch("src.media_ingestor.fetch_youtube_videos")
    def test_published_at_parsed_correctly(self, mock_fetch):
        from datetime import timezone
        from src.media_ingestor import fetch_youtube_data_api

        mock_fetch.return_value = [
            {
                "video_id": "abc12345678",
                "title": "Draft Day",
                "description": "My picks",
                "published_at": "2026-04-24T18:00:00Z",
                "channel_id": "UCa5oCHMV7ImHb6FxJGqz9cQ",
                "channel_title": "Channel",
                "url": "https://www.youtube.com/watch?v=abc12345678",
            }
        ]

        with patch.dict(os.environ, {"YOUTUBE_API_KEY": "test_key"}):
            items = fetch_youtube_data_api(self.YOUTUBE_SOURCE, self.DEFAULTS)

        assert items[0].published_at is not None
        assert items[0].published_at.tzinfo == timezone.utc
        assert items[0].published_at.year == 2026
        assert items[0].published_at.month == 4
        assert items[0].published_at.day == 24

    @patch("src.media_ingestor.fetch_youtube_videos")
    def test_keyword_filter_skips_non_matching_videos(self, mock_fetch):
        """nouriel_roubini (and similar multi-guest channels) rely on
        keyword_filter to scope a channel-wide feed down to relevant
        appearances — this must keep working after switching from
        youtube_transcript to youtube_data_api (#pipeline-ingestion-recovery)."""
        from src.media_ingestor import fetch_youtube_data_api

        source_with_filter = {
            **self.YOUTUBE_SOURCE,
            "keyword_filter": ["Roubini", "Dr. Doom"],
        }
        mock_fetch.return_value = [
            {
                "video_id": "match123456",
                "title": "Nouriel Roubini on the global economy",
                "description": "Dr. Doom joins to discuss recession risk",
                "published_at": "2026-04-28T12:00:00Z",
                "channel_id": "UCa5oCHMV7ImHb6FxJGqz9cQ",
                "channel_title": "Bloomberg Television",
                "url": "https://www.youtube.com/watch?v=match123456",
            },
            {
                "video_id": "nomatch12345",
                "title": "Markets close higher on Fed news",
                "description": "A recap of today's trading session",
                "published_at": "2026-04-28T12:00:00Z",
                "channel_id": "UCa5oCHMV7ImHb6FxJGqz9cQ",
                "channel_title": "Bloomberg Television",
                "url": "https://www.youtube.com/watch?v=nomatch12345",
            },
        ]

        with patch.dict(os.environ, {"YOUTUBE_API_KEY": "test_key"}):
            items = fetch_youtube_data_api(source_with_filter, self.DEFAULTS)

        assert len(items) == 1
        assert items[0].source_url == "https://www.youtube.com/watch?v=match123456"

    def test_no_channel_id_anywhere_returns_empty(self):
        from src.media_ingestor import fetch_youtube_data_api

        source_no_ids = {
            **self.YOUTUBE_SOURCE,
            "url": "https://www.youtube.com/channel/UCsomething",
        }
        del source_no_ids["channel_id"]

        with patch.dict(os.environ, {"YOUTUBE_API_KEY": "test_key"}):
            items = fetch_youtube_data_api(source_no_ids, self.DEFAULTS)

        # URL has no channel_id= param, so it fails gracefully
        assert items == []
