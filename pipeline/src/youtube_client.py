"""
YouTube Data API v3 client (Issue #382).

Replaces youtube-transcript-api (IP-blocked scraping) with official YouTube
Data API v3 calls. Uses video title + description as the extractable text —
YouTube descriptions often contain the key claims.

Free tier: 10,000 units/day.
- search.list: 100 units per call → 100 searches/day free
- videos.list: 1 unit per call

Setup:
  1. Google Cloud Console → APIs & Services → Enable "YouTube Data API v3"
  2. Create an API key (Credentials → Create Credentials → API key)
  3. Set YOUTUBE_API_KEY=<your key> in your .env / Cloud Run env vars

GCP project: cap-alpha-protocol
"""

import logging
import os
from typing import Optional

import requests

logger = logging.getLogger(__name__)

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"

# Max description chars we'll store as "text" — descriptions can be very long
MAX_DESCRIPTION_CHARS = 4000


def _get_api_key() -> Optional[str]:
    """Return the YouTube API key from the environment, or None if not set."""
    return os.environ.get("YOUTUBE_API_KEY")


def _api_key_available() -> bool:
    """Return True if YOUTUBE_API_KEY is set in the environment."""
    return bool(_get_api_key())


def fetch_youtube_videos(
    channel_id: str,
    max_results: int = 10,
    timeout: int = 30,
) -> list[dict]:
    """
    Use YouTube Data API v3 search.list to get recent videos from a channel.

    Returns a list of dicts, each containing:
      - video_id (str)
      - title (str)
      - description (str)
      - published_at (str, ISO 8601)
      - channel_id (str)
      - channel_title (str)
      - url (str)

    Costs 100 quota units per call (search.list).
    Raises ValueError if YOUTUBE_API_KEY is not set.
    Raises requests.HTTPError on non-200 responses.
    """
    api_key = _get_api_key()
    if not api_key:
        raise ValueError(
            "YOUTUBE_API_KEY environment variable is not set. "
            "Get one at: Google Cloud Console → APIs & Services → "
            "Enable 'YouTube Data API v3' → Credentials → Create API key. "
            "GCP project: cap-alpha-protocol"
        )

    params = {
        "key": api_key,
        "channelId": channel_id,
        "part": "snippet",
        "order": "date",
        "maxResults": max_results,
        "type": "video",
    }

    resp = requests.get(
        f"{YOUTUBE_API_BASE}/search",
        params=params,
        timeout=timeout,
    )
    resp.raise_for_status()

    data = resp.json()
    videos = []
    for item in data.get("items", []):
        snippet = item.get("snippet", {})
        video_id = item.get("id", {}).get("videoId", "")
        if not video_id:
            continue

        videos.append(
            {
                "video_id": video_id,
                "title": snippet.get("title", ""),
                "description": snippet.get("description", ""),
                "published_at": snippet.get("publishedAt", ""),
                "channel_id": snippet.get("channelId", ""),
                "channel_title": snippet.get("channelTitle", ""),
                "url": f"https://www.youtube.com/watch?v={video_id}",
            }
        )

    return videos


def fetch_video_description(
    video_id: str,
    timeout: int = 30,
) -> dict:
    """
    Fetch video title + full description via videos.list.

    Returns a dict with:
      - video_id (str)
      - title (str)
      - description (str)  — truncated to MAX_DESCRIPTION_CHARS
      - published_at (str, ISO 8601)
      - channel_id (str)
      - channel_title (str)
      - url (str)

    Costs 1 quota unit per call (videos.list).
    Raises ValueError if YOUTUBE_API_KEY is not set.
    Raises requests.HTTPError on non-200 responses.
    Raises ValueError if video_id is not found.
    """
    api_key = _get_api_key()
    if not api_key:
        raise ValueError(
            "YOUTUBE_API_KEY environment variable is not set. "
            "Get one at: Google Cloud Console → APIs & Services → "
            "Enable 'YouTube Data API v3' → Credentials → Create API key. "
            "GCP project: cap-alpha-protocol"
        )

    params = {
        "key": api_key,
        "id": video_id,
        "part": "snippet",
    }

    resp = requests.get(
        f"{YOUTUBE_API_BASE}/videos",
        params=params,
        timeout=timeout,
    )
    resp.raise_for_status()

    data = resp.json()
    items = data.get("items", [])
    if not items:
        raise ValueError(f"Video not found: {video_id}")

    snippet = items[0].get("snippet", {})
    description = snippet.get("description", "")
    if len(description) > MAX_DESCRIPTION_CHARS:
        description = description[:MAX_DESCRIPTION_CHARS]

    return {
        "video_id": video_id,
        "title": snippet.get("title", ""),
        "description": description,
        "published_at": snippet.get("publishedAt", ""),
        "channel_id": snippet.get("channelId", ""),
        "channel_title": snippet.get("channelTitle", ""),
        "url": f"https://www.youtube.com/watch?v={video_id}",
    }


def build_video_text(video: dict) -> str:
    """
    Build a combined text string from title + description for prediction extraction.

    YouTube descriptions frequently contain explicit predictions:
      "I have Travis Hunter going #1 to Jacksonville"
    Combining title + description gives the extraction model enough signal.
    """
    parts = []
    if video.get("title"):
        parts.append(video["title"])
    if video.get("description"):
        parts.append(video["description"])
    return "\n\n".join(parts)
