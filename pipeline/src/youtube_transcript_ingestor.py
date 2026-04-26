"""
YouTube Transcript Bulk Ingestor (Issue #262)

Fetches auto-generated transcripts from NFL prediction-dense YouTube channels,
stores them as bronze-layer raw_pundit_media rows, then optionally runs the
assertion extractor to convert them to structured predictions.

Design goals:
  - Parallelised transcript fetching (ThreadPoolExecutor, ≤10 workers)
  - Title-regex filtering: only prediction-dense videos get processed
  - Duration guard: skip videos longer than 90 minutes (cost control)
  - Date guard: skip videos published before 2020 (resolver coverage)
  - yt-dlp fallback when youtube-transcript-api reports "transcripts disabled"
  - Writes to raw_pundit_media with fetch_source_type="youtube_transcript"
  - Runs extraction with allow_historical=True so past-season predictions land

Usage:
    # Dry run — print what would be fetched, no BQ writes
    python -m src.youtube_transcript_ingestor --dry-run

    # Ingest + extract for all enabled channels (writes to BQ)
    python -m src.youtube_transcript_ingestor --run-extraction

    # Single channel
    python -m src.youtube_transcript_ingestor --source bussin_with_the_boys --run-extraction

    # Explicit video URL list (good for targeted backfill)
    python -m src.youtube_transcript_ingestor --urls https://youtube.com/watch?v=ABC123 --run-extraction

    # Sample test: 5 videos, dry-run
    python -m src.youtube_transcript_ingestor --limit 5 --dry-run
"""

import argparse
import hashlib
import json
import logging
import os
import re
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, parse_qs

import feedparser
import pandas as pd

try:
    from youtube_transcript_api import YouTubeTranscriptApi

    _yt_client: Optional[YouTubeTranscriptApi] = None
    try:
        _yt_client = YouTubeTranscriptApi()
        _YT_API_V1 = True
    except TypeError:
        _YT_API_V1 = False
    _YT_AVAILABLE = True
except ImportError:
    _YT_AVAILABLE = False
    _YT_API_V1 = False
    _yt_client = None

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RAW_MEDIA_TABLE = "raw_pundit_media"
PROCESSED_TABLE = "processed_media_hashes"

# Videos matching any of these patterns in the title are worth processing
PREDICTION_TITLE_RE = re.compile(
    r"""
    predict|bold|will\s|won['']?t|preview|grade|rank|MVP|
    playoff|over[.\-/]under|win\s+total|lock\s+of|pick\s|picks\s|
    bold\s+call|super\s+bowl|nfl\s+draft|free\s+agent|hot\s+take|
    week\s+\d+|game\s+day|breakdown|who\s+wins|should\s+the|
    bet|prop|sleeper|bust|breakout|fantasy
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Skip videos longer than this (in seconds)
MAX_DURATION_SECONDS = 90 * 60  # 90 minutes

# Skip videos published before this year
MIN_PUBLISH_YEAR = 2020

# Parallelism cap for transcript fetches
MAX_WORKERS = 10

# How many videos per channel to consider (limited to keep batches fast)
DEFAULT_MAX_VIDEOS = 25

# ---------------------------------------------------------------------------
# Channel registry
# Used by --list-sources and when no --source / --urls is given.
# channel_id: YouTube channel ID, used to build the Atom feed URL.
# ---------------------------------------------------------------------------

CHANNEL_REGISTRY: list[dict] = [
    {
        "id": "pat_mcafee_show",
        "name": "The Pat McAfee Show",
        "channel_id": "UCxcTeAKWJca6XyJ37_ZoKIQ",
        "pundits": [{"id": "pat_mcafee", "name": "Pat McAfee"}],
        "enabled": True,
    },
    {
        "id": "bussin_with_the_boys",
        "name": "Bussin' With The Boys",
        "channel_id": "UCEJeEfpnO_2J3DVovs-0Pkw",
        "pundits": [
            {"id": "taylor_lewan", "name": "Taylor Lewan"},
            {"id": "will_compton", "name": "Will Compton"},
        ],
        "enabled": True,
    },
    {
        "id": "brett_kollmann",
        "name": "Brett Kollmann",
        "channel_id": "UCHGx4e5K0-_n3RMcWHiTb4A",
        "pundits": [{"id": "brett_kollmann", "name": "Brett Kollmann"}],
        "enabled": True,
    },
    {
        "id": "warren_sharp",
        "name": "Warren Sharp / Sharp Football",
        "channel_id": "UCcaGl7bsLaVBnDlK-TGFKqA",
        "pundits": [{"id": "warren_sharp", "name": "Warren Sharp"}],
        "enabled": True,
    },
    {
        "id": "locked_on_nfl",
        "name": "Locked On NFL",
        "channel_id": "UCFkI6HvC2a-Y33IfiBqLKhg",
        "pundits": [{"id": "locked_on_nfl_staff", "name": "Locked On NFL Staff"}],
        "enabled": True,
    },
    {
        "id": "the_ringer_nfl",
        "name": "The Ringer NFL Show",
        "channel_id": "UCMqF6BdstA43vNQzs2BMR0w",
        "pundits": [{"id": "ringer_nfl_staff", "name": "The Ringer NFL"}],
        "enabled": True,
    },
    {
        "id": "pff_nfl",
        "name": "PFF (Pro Football Focus)",
        "channel_id": "UCijBMkVMuT1hl4vAAGjxJPA",
        "pundits": [{"id": "pff_staff", "name": "PFF Staff"}],
        "enabled": True,
    },
    {
        "id": "move_the_sticks",
        "name": "Move The Sticks (Daniel Jeremiah)",
        "channel_id": "UCaWLWkqRKcVgkz3jocJUjHg",
        "pundits": [{"id": "daniel_jeremiah", "name": "Daniel Jeremiah"}],
        "enabled": True,
    },
    {
        "id": "athletic_football_show",
        "name": "The Athletic Football Show",
        "channel_id": "UCEShWcVeWL3jL0lNfM4kO8Q",
        "pundits": [{"id": "athletic_nfl_staff", "name": "The Athletic NFL Staff"}],
        "enabled": True,
    },
    {
        "id": "rich_eisen_show",
        "name": "The Rich Eisen Show",
        "channel_id": "UCqMtxjKnR7ySbEZSs2N-v0Q",
        "pundits": [{"id": "rich_eisen", "name": "Rich Eisen"}],
        "enabled": True,
    },
    {
        "id": "dan_patrick_show",
        "name": "The Dan Patrick Show",
        "channel_id": "UCORy0Yqzd8bVj2Gb4xyq6HA",
        "pundits": [{"id": "dan_patrick", "name": "Dan Patrick"}],
        "enabled": True,
    },
]


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class VideoMeta:
    """Metadata for a YouTube video before transcript fetch."""

    video_id: str
    url: str
    title: str
    published_at: Optional[datetime]
    channel_id: str
    source_id: str
    pundit_id: Optional[str]
    pundit_name: Optional[str]
    duration_seconds: Optional[int] = None
    # True once transcript has been fetched
    transcript_fetched: bool = False


@dataclass
class TranscriptResult:
    """Result of a single transcript fetch attempt."""

    video_id: str
    url: str
    transcript_text: Optional[str]
    error: Optional[str] = None
    used_ytdlp: bool = False


@dataclass
class IngestSummary:
    source_id: str
    videos_considered: int = 0
    videos_skipped_title: int = 0
    videos_skipped_duration: int = 0
    videos_skipped_date: int = 0
    videos_skipped_dedup: int = 0
    transcripts_fetched: int = 0
    transcripts_failed: int = 0
    transcripts_disabled_count: int = 0
    items_written: int = 0
    predictions_extracted: int = 0
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# YouTube helpers
# ---------------------------------------------------------------------------


def _channel_feed_url(channel_id: str) -> str:
    return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"


def _extract_video_id(url: str) -> Optional[str]:
    """Extract 11-char video ID from various YouTube URL formats."""
    # Standard watch URL
    match = re.search(r"[?&]v=([a-zA-Z0-9_-]{11})", url)
    if match:
        return match.group(1)
    # Shortened youtu.be/ID
    match = re.search(r"youtu\.be/([a-zA-Z0-9_-]{11})", url)
    if match:
        return match.group(1)
    # Shorts
    match = re.search(r"/shorts/([a-zA-Z0-9_-]{11})", url)
    if match:
        return match.group(1)
    return None


def _is_short(url: str) -> bool:
    return "/shorts/" in url


def _passes_title_filter(title: str) -> bool:
    """Return True if the video title suggests prediction-dense content."""
    return bool(PREDICTION_TITLE_RE.search(title))


def _passes_date_filter(published_at: Optional[datetime]) -> bool:
    """Return True if the video was published in MIN_PUBLISH_YEAR or later."""
    if published_at is None:
        return True  # optimistic: don't reject unknowns
    return published_at.year >= MIN_PUBLISH_YEAR


def _parse_duration_iso(duration_str: str) -> Optional[int]:
    """Parse ISO 8601 duration (PT1H30M45S) → seconds. Returns None on parse failure."""
    if not duration_str:
        return None
    match = re.match(
        r"PT(?:(?P<h>\d+)H)?(?:(?P<m>\d+)M)?(?:(?P<s>\d+)S)?", duration_str
    )
    if not match:
        return None
    h = int(match.group("h") or 0)
    m = int(match.group("m") or 0)
    s = int(match.group("s") or 0)
    return h * 3600 + m * 60 + s


# ---------------------------------------------------------------------------
# Transcript fetching
# ---------------------------------------------------------------------------


def _fetch_transcript_yt_api(video_id: str) -> str:
    """Fetch transcript via youtube-transcript-api. Raises on failure."""
    if not _YT_AVAILABLE:
        raise ImportError("youtube-transcript-api not installed")
    if _YT_API_V1 and _yt_client is not None:
        result = _yt_client.fetch(video_id)
        return " ".join(snippet.text for snippet in result)
    else:
        transcript_data = YouTubeTranscriptApi.get_transcript(video_id)
        return " ".join(seg["text"] for seg in transcript_data)


def _fetch_transcript_ytdlp(video_id: str) -> str:
    """
    Fallback: use yt-dlp to download auto-generated subtitles as a VTT file,
    then strip the VTT markup and return plain text.
    Raises subprocess.CalledProcessError on failure.
    """
    url = f"https://www.youtube.com/watch?v={video_id}"
    with tempfile.TemporaryDirectory() as tmpdir:
        out_template = str(Path(tmpdir) / "%(id)s.%(ext)s")
        subprocess.run(
            [
                "yt-dlp",
                "--write-auto-sub",
                "--sub-lang",
                "en",
                "--skip-download",
                "--convert-subs",
                "vtt",
                "-o",
                out_template,
                url,
            ],
            check=True,
            capture_output=True,
            timeout=120,
        )
        # Find the downloaded VTT file
        vtt_files = list(Path(tmpdir).glob("*.vtt"))
        if not vtt_files:
            raise FileNotFoundError(f"yt-dlp produced no VTT for {video_id}")
        vtt_text = vtt_files[0].read_text(encoding="utf-8", errors="ignore")
    # Strip VTT markup: remove header, timestamps, tags
    lines = []
    for line in vtt_text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("WEBVTT") or line.startswith("NOTE"):
            continue
        if re.match(r"^\d{2}:\d{2}:\d{2}", line):
            continue
        if re.match(r"^<\d{2}:\d{2}:\d{2}", line):
            continue
        # Strip inline VTT tags like <00:00:01.000> and <c>
        cleaned = re.sub(r"<[^>]+>", "", line).strip()
        if cleaned:
            lines.append(cleaned)
    return " ".join(lines)


def fetch_single_transcript(video_id: str) -> TranscriptResult:
    """
    Fetch transcript for a single video ID, trying youtube-transcript-api first,
    then falling back to yt-dlp.
    Returns a TranscriptResult (never raises).
    """
    url = f"https://www.youtube.com/watch?v={video_id}"
    # Attempt 1: youtube-transcript-api
    try:
        text = _fetch_transcript_yt_api(video_id)
        if text.strip():
            return TranscriptResult(video_id=video_id, url=url, transcript_text=text)
    except Exception as e1:
        err_msg = str(e1)
        disabled = "disabled" in err_msg.lower() or "no transcript" in err_msg.lower()

        if disabled:
            # Attempt 2: yt-dlp fallback
            try:
                text = _fetch_transcript_ytdlp(video_id)
                if text.strip():
                    return TranscriptResult(
                        video_id=video_id,
                        url=url,
                        transcript_text=text,
                        used_ytdlp=True,
                    )
            except Exception as e2:
                return TranscriptResult(
                    video_id=video_id,
                    url=url,
                    transcript_text=None,
                    error=f"yt-api: {e1}; yt-dlp: {e2}",
                )
        else:
            return TranscriptResult(
                video_id=video_id,
                url=url,
                transcript_text=None,
                error=str(e1),
            )
    return TranscriptResult(
        video_id=video_id,
        url=url,
        transcript_text=None,
        error="Empty transcript returned",
    )


def fetch_transcripts_parallel(
    video_ids: list[str],
    max_workers: int = MAX_WORKERS,
) -> list[TranscriptResult]:
    """Fetch transcripts for multiple video IDs in parallel."""
    results: list[TranscriptResult] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_map = {
            pool.submit(fetch_single_transcript, vid): vid for vid in video_ids
        }
        for future in as_completed(future_map):
            results.append(future.result())
    return results


# ---------------------------------------------------------------------------
# Channel feed parsing
# ---------------------------------------------------------------------------


def list_channel_videos(
    channel_id: str,
    source_id: str,
    pundit_id: Optional[str],
    pundit_name: Optional[str],
    max_videos: int = DEFAULT_MAX_VIDEOS,
    title_filter: bool = True,
    skip_shorts: bool = True,
) -> tuple[list[VideoMeta], int]:
    """
    Fetch a channel's Atom feed and return VideoMeta objects for videos that
    pass the title/date/shorts filters.

    Returns (filtered_videos, total_skipped_by_title).
    """
    feed_url = _channel_feed_url(channel_id)
    feed = feedparser.parse(
        feed_url, request_headers={"User-Agent": "PunditLedger/1.0"}
    )

    videos: list[VideoMeta] = []
    skipped_title = 0

    for entry in feed.entries[: max_videos * 3]:  # fetch 3x to allow for filtering
        title = entry.get("title", "")
        link = entry.get("link", "")
        if not link:
            continue

        if skip_shorts and _is_short(link):
            continue

        video_id = _extract_video_id(link)
        if not video_id:
            continue

        # Title filter
        if title_filter and not _passes_title_filter(title):
            skipped_title += 1
            continue

        # Parse published date
        published: Optional[datetime] = None
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            try:
                published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            except Exception:
                pass

        # Date filter
        if not _passes_date_filter(published):
            continue

        # Parse duration from yt:statistics or media:group if available
        duration_seconds: Optional[int] = None
        for ns_key in ("yt_duration", "media_duration"):
            val = entry.get(ns_key)
            if val:
                duration_seconds = _parse_duration_iso(str(val))
                break

        videos.append(
            VideoMeta(
                video_id=video_id,
                url=link,
                title=title,
                published_at=published,
                channel_id=channel_id,
                source_id=source_id,
                pundit_id=pundit_id,
                pundit_name=pundit_name,
                duration_seconds=duration_seconds,
            )
        )

        if len(videos) >= max_videos:
            break

    return videos, skipped_title


# ---------------------------------------------------------------------------
# Content hashing and dedup
# ---------------------------------------------------------------------------


def _content_hash(url: str, chunk_index: int = 0) -> str:
    chunk_suffix = f"|chunk_{chunk_index}" if chunk_index > 0 else ""
    return hashlib.sha256(f"{url}{chunk_suffix}".encode()).hexdigest()


def _get_existing_hashes(db, source_id: str) -> set:
    """Fetch all previously ingested content_hashes for this source (all-time)."""
    project_id = os.environ.get("GCP_PROJECT_ID")
    try:
        df = db.fetch_df(
            f"""
            SELECT content_hash
            FROM `{project_id}.nfl_dead_money.{RAW_MEDIA_TABLE}`
            WHERE source_id = '{source_id}'
        """
        )
        return set(df["content_hash"].tolist()) if not df.empty else set()
    except Exception as e:
        logger.warning(f"Could not fetch existing hashes for {source_id}: {e}")
        return set()


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

CHUNK_SIZE = 3500


def _chunk_text(text: str) -> list[str]:
    if len(text) <= CHUNK_SIZE:
        return [text]
    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= CHUNK_SIZE:
            chunks.append(remaining)
            break
        split_at = CHUNK_SIZE
        last_sentence = -1
        for m in re.finditer(r"[.!?]\s", remaining[:CHUNK_SIZE]):
            last_sentence = m.end()
        if last_sentence > 0:
            split_at = last_sentence
        else:
            last_space = remaining[:CHUNK_SIZE].rfind(" ")
            if last_space > 0:
                split_at = last_space + 1
        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    return chunks


# ---------------------------------------------------------------------------
# Core ingest function
# ---------------------------------------------------------------------------


def ingest_channel(
    channel_cfg: dict,
    db=None,
    dry_run: bool = False,
    max_videos: int = DEFAULT_MAX_VIDEOS,
    title_filter: bool = True,
    run_extraction: bool = False,
) -> IngestSummary:
    """
    Full ingest pipeline for a single channel:
      1. Fetch channel feed
      2. Filter videos (title, date, duration)
      3. Parallel transcript fetch
      4. Dedup + write to raw_pundit_media
      5. (Optional) Run assertion extractor on new items

    Returns IngestSummary with counts for observability.
    """
    source_id = channel_cfg["id"]
    channel_id = channel_cfg["channel_id"]
    pundits = channel_cfg.get("pundits", [])
    pundit = pundits[0] if pundits else {}
    pundit_id = pundit.get("id")
    pundit_name = pundit.get("name")

    summary = IngestSummary(source_id=source_id)

    logger.info(f"[{source_id}] Fetching channel feed: {channel_cfg['name']}")
    try:
        videos, skipped_title = list_channel_videos(
            channel_id=channel_id,
            source_id=source_id,
            pundit_id=pundit_id,
            pundit_name=pundit_name,
            max_videos=max_videos,
            title_filter=title_filter,
        )
    except Exception as e:
        summary.error = f"Feed fetch failed: {e}"
        logger.error(f"[{source_id}] {summary.error}")
        return summary

    summary.videos_considered = len(videos) + skipped_title
    summary.videos_skipped_title = skipped_title

    # Duration filter (applied after feed parse since duration isn't always in feed)
    duration_filtered = []
    for v in videos:
        if v.duration_seconds is not None and v.duration_seconds > MAX_DURATION_SECONDS:
            summary.videos_skipped_duration += 1
            logger.debug(
                f"[{source_id}] Skipping long video ({v.duration_seconds}s): {v.title}"
            )
        else:
            duration_filtered.append(v)

    videos = duration_filtered

    if not videos:
        logger.warning(f"[{source_id}] No videos passed filters")
        return summary

    logger.info(
        f"[{source_id}] Fetching transcripts for {len(videos)} videos (parallel)"
    )

    # Dedup against BQ before fetching transcripts
    existing_hashes: set = set()
    if db is not None and not dry_run:
        existing_hashes = _get_existing_hashes(db, source_id)

    # Check which videos we'd dedup before even fetching
    videos_to_fetch = []
    for v in videos:
        h = _content_hash(v.url)
        if h in existing_hashes:
            summary.videos_skipped_dedup += 1
        else:
            videos_to_fetch.append(v)

    if not videos_to_fetch:
        logger.info(f"[{source_id}] All videos already ingested (dedup)")
        return summary

    # Parallel transcript fetch
    video_ids = [v.video_id for v in videos_to_fetch]
    transcript_results = fetch_transcripts_parallel(video_ids, max_workers=MAX_WORKERS)

    # Map results back to VideoMeta
    result_by_id = {r.video_id: r for r in transcript_results}
    disabled_count = sum(
        1
        for r in transcript_results
        if r.error and "disabled" in (r.error or "").lower()
    )
    summary.transcripts_disabled_count = disabled_count

    # Stop condition: >50% transcripts disabled
    if len(transcript_results) > 0:
        disabled_ratio = disabled_count / len(transcript_results)
        if disabled_ratio > 0.5:
            logger.warning(
                f"[{source_id}] {disabled_ratio:.0%} of transcripts disabled — "
                "yt-dlp fallback already attempted; channel may not support captions"
            )

    # Build MediaItem rows
    rows: list[dict] = []
    now = datetime.now(timezone.utc)

    for v in videos_to_fetch:
        result = result_by_id.get(v.video_id)
        if result is None or result.transcript_text is None:
            summary.transcripts_failed += 1
            continue

        summary.transcripts_fetched += 1
        chunks = _chunk_text(result.transcript_text)

        for i, chunk in enumerate(chunks):
            is_chunked = len(chunks) > 1
            chunk_suffix = f"|chunk_{i}" if is_chunked else ""
            chunk_title = f"{v.title} (part {i + 1})" if is_chunked else v.title
            ch = _content_hash(v.url, i)

            if ch in existing_hashes:
                continue

            metadata = {
                "used_ytdlp": result.used_ytdlp,
                "is_historical": v.published_at.year < datetime.now().year
                if v.published_at
                else False,
            }

            rows.append(
                {
                    "content_hash": ch,
                    "source_id": source_id,
                    "title": chunk_title,
                    "raw_text": chunk,
                    "source_url": v.url,
                    "author": pundit_name,
                    "matched_pundit_id": pundit_id,
                    "matched_pundit_name": pundit_name,
                    "published_at": v.published_at,
                    "ingested_at": now,
                    "content_type": "transcript",
                    "fetch_source_type": "youtube_transcript",
                    "sport": "NFL",
                    "raw_metadata": json.dumps(metadata),
                }
            )

    summary.items_written = len(rows)

    if rows and not dry_run and db is not None:
        df = pd.DataFrame(rows)
        nullable_cols = [
            "title",
            "raw_text",
            "author",
            "matched_pundit_id",
            "matched_pundit_name",
            "published_at",
            "raw_metadata",
        ]
        for col in nullable_cols:
            if col in df.columns:
                df[col] = df[col].where(df[col].notna(), None)
        db.append_dataframe_to_table(df, RAW_MEDIA_TABLE)
        logger.info(f"[{source_id}] Wrote {len(rows)} transcript chunks to BQ")
    elif dry_run:
        logger.info(f"[{source_id}] DRY RUN: would write {len(rows)} transcript chunks")

    # Optional: run assertion extractor on newly ingested items
    if run_extraction and rows and not dry_run and db is not None:
        hashes_just_written = [r["content_hash"] for r in rows]
        n_predictions = _run_extraction_for_hashes(hashes_just_written, db)
        summary.predictions_extracted = n_predictions

    return summary


def _run_extraction_for_hashes(content_hashes: list[str], db) -> int:
    """Run assertion extraction on a specific set of content_hashes (just written)."""
    try:
        from src.assertion_extractor import (
            extract_assertions,
            get_unprocessed_media,
            mark_as_processed,
            run_extraction,
        )
        from src.llm_provider import get_provider_with_fallback, load_llm_config

        llm_cfg = load_llm_config()
        provider = get_provider_with_fallback(llm_cfg)

        # Use run_extraction with a high limit so it picks up our new rows
        # allow_historical=True to preserve past-season predictions
        result = run_extraction(
            limit=len(content_hashes) * 3,  # margin for dedup/concurrency
            dry_run=False,
            sport="NFL",
            include_unmatched=False,
            db=db,
            provider=provider,
            allow_historical=True,
        )
        n = result.get("predictions_ingested", 0)
        logger.info(
            f"Extraction: {n} predictions from {len(content_hashes)} transcript chunks"
        )
        return n
    except Exception as e:
        logger.error(f"Extraction failed: {e}")
        return 0


# ---------------------------------------------------------------------------
# Ingest from explicit URL list
# ---------------------------------------------------------------------------


def ingest_urls(
    urls: list[str],
    source_id: str = "youtube_backfill",
    pundit_id: Optional[str] = None,
    pundit_name: Optional[str] = None,
    db=None,
    dry_run: bool = False,
    run_extraction: bool = False,
) -> IngestSummary:
    """
    Ingest transcripts from an explicit list of YouTube video URLs.
    Useful for targeted backfill without needing channel feed access.
    """
    summary = IngestSummary(source_id=source_id)
    existing_hashes: set = set()
    if db is not None and not dry_run:
        existing_hashes = _get_existing_hashes(db, source_id)

    video_ids_to_fetch: list[tuple[str, str]] = []  # (video_id, url)
    for url in urls:
        if "/shorts/" in url:
            logger.debug(f"Skipping Short: {url}")
            continue
        vid = _extract_video_id(url)
        if not vid:
            logger.warning(f"Could not extract video ID: {url}")
            continue
        h = _content_hash(url)
        if h in existing_hashes:
            summary.videos_skipped_dedup += 1
            continue
        video_ids_to_fetch.append((vid, url))

    summary.videos_considered = len(urls)

    if not video_ids_to_fetch:
        logger.info(f"[{source_id}] All URLs already ingested or invalid")
        return summary

    transcript_results = fetch_transcripts_parallel(
        [vid for vid, _ in video_ids_to_fetch], max_workers=MAX_WORKERS
    )
    result_by_id = {r.video_id: r for r in transcript_results}

    rows: list[dict] = []
    now = datetime.now(timezone.utc)

    for vid, url in video_ids_to_fetch:
        result = result_by_id.get(vid)
        if result is None or result.transcript_text is None:
            summary.transcripts_failed += 1
            continue
        summary.transcripts_fetched += 1
        chunks = _chunk_text(result.transcript_text)
        for i, chunk in enumerate(chunks):
            ch = _content_hash(url, i)
            if ch in existing_hashes:
                continue
            rows.append(
                {
                    "content_hash": ch,
                    "source_id": source_id,
                    "title": f"YouTube video {vid}"
                    + (f" (part {i + 1})" if len(chunks) > 1 else ""),
                    "raw_text": chunk,
                    "source_url": url,
                    "author": pundit_name,
                    "matched_pundit_id": pundit_id,
                    "matched_pundit_name": pundit_name,
                    "published_at": None,
                    "ingested_at": now,
                    "content_type": "transcript",
                    "fetch_source_type": "youtube_transcript",
                    "sport": "NFL",
                    "raw_metadata": json.dumps({"used_ytdlp": result.used_ytdlp}),
                }
            )

    summary.items_written = len(rows)

    if rows and not dry_run and db is not None:
        df = pd.DataFrame(rows)
        nullable_cols = [
            "title",
            "raw_text",
            "author",
            "matched_pundit_id",
            "matched_pundit_name",
            "published_at",
            "raw_metadata",
        ]
        for col in nullable_cols:
            if col in df.columns:
                df[col] = df[col].where(df[col].notna(), None)
        db.append_dataframe_to_table(df, RAW_MEDIA_TABLE)
        logger.info(f"[{source_id}] Wrote {len(rows)} chunks for {len(urls)} URLs")
    elif dry_run:
        logger.info(f"[{source_id}] DRY RUN: would write {len(rows)} chunks")

    if run_extraction and rows and not dry_run and db is not None:
        n = _run_extraction_for_hashes([r["content_hash"] for r in rows], db)
        summary.predictions_extracted = n

    return summary


# ---------------------------------------------------------------------------
# Multi-channel orchestration
# ---------------------------------------------------------------------------


def run_all_channels(
    db=None,
    dry_run: bool = False,
    source_filter: Optional[str] = None,
    max_videos: int = DEFAULT_MAX_VIDEOS,
    title_filter: bool = True,
    run_extraction: bool = False,
) -> list[IngestSummary]:
    """Run ingest for all enabled channels (or a single one via source_filter)."""
    summaries: list[IngestSummary] = []

    for cfg in CHANNEL_REGISTRY:
        if not cfg.get("enabled", True):
            continue
        if source_filter and cfg["id"] != source_filter:
            continue

        summary = ingest_channel(
            channel_cfg=cfg,
            db=db,
            dry_run=dry_run,
            max_videos=max_videos,
            title_filter=title_filter,
            run_extraction=run_extraction,
        )
        summaries.append(summary)

    total_written = sum(s.items_written for s in summaries)
    total_predictions = sum(s.predictions_extracted for s in summaries)
    total_failed = sum(s.transcripts_failed for s in summaries)
    logger.info(
        f"YouTube ingest complete: {len(summaries)} channels, "
        f"{total_written} chunks written, {total_predictions} predictions extracted, "
        f"{total_failed} transcript failures"
    )
    return summaries


# ---------------------------------------------------------------------------
# Yield monitor
# ---------------------------------------------------------------------------


def check_yield(summaries: list[IngestSummary]) -> None:
    """
    Warn if prediction yield per transcript is below the 1 pred/transcript threshold.
    This is a signal to re-tune the extractor prompt.
    """
    total_transcripts = sum(s.transcripts_fetched for s in summaries)
    total_predictions = sum(s.predictions_extracted for s in summaries)
    if total_transcripts == 0:
        return
    yield_rate = total_predictions / total_transcripts
    if yield_rate < 1.0 and total_predictions > 0:
        logger.warning(
            f"Low extraction yield: {yield_rate:.2f} predictions/transcript "
            f"({total_predictions}/{total_transcripts}). "
            "Consider re-tuning the extraction prompt."
        )
    elif total_predictions == 0 and total_transcripts >= 5:
        logger.error(
            "STOP CONDITION: 0 predictions extracted from "
            f"{total_transcripts} transcripts. Check extractor."
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="YouTube Transcript Bulk Ingestor for Pundit Prediction Ledger"
    )
    parser.add_argument(
        "--source", help="Run a single channel by source ID (e.g. bussin_with_the_boys)"
    )
    parser.add_argument(
        "--urls",
        nargs="+",
        metavar="URL",
        help="Explicit YouTube video URLs to ingest (backfill mode)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without writing to BigQuery",
    )
    parser.add_argument(
        "--run-extraction",
        action="store_true",
        help="Run assertion extractor on newly ingested transcripts",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_MAX_VIDEOS,
        help=f"Max videos per channel (default: {DEFAULT_MAX_VIDEOS})",
    )
    parser.add_argument(
        "--no-title-filter",
        action="store_true",
        help="Disable title-based prediction filter (process all videos)",
    )
    parser.add_argument(
        "--list-sources",
        action="store_true",
        help="Print registered channels and exit",
    )
    args = parser.parse_args()

    if args.list_sources:
        print(f"\n{'ID':<35} {'Name':<40} {'Enabled'}")
        print("-" * 85)
        for cfg in CHANNEL_REGISTRY:
            print(
                f"{cfg['id']:<35} {cfg['name']:<40} {'yes' if cfg.get('enabled') else 'no'}"
            )
        return

    # Import DBManager here to allow --dry-run / --list-sources without BQ creds
    from src.db_manager import DBManager

    db = None if args.dry_run else DBManager()

    try:
        if args.urls:
            summary = ingest_urls(
                urls=args.urls,
                source_id=args.source or "youtube_backfill",
                db=db,
                dry_run=args.dry_run,
                run_extraction=args.run_extraction,
            )
            summaries = [summary]
        else:
            summaries = run_all_channels(
                db=db,
                dry_run=args.dry_run,
                source_filter=args.source,
                max_videos=args.limit,
                title_filter=not args.no_title_filter,
                run_extraction=args.run_extraction,
            )

        # Print summary table
        print(
            f"\n{'Source':<35} {'Vids':>5} {'Skip-T':>7} {'Skip-D':>7} "
            f"{'TxFetch':>8} {'Fail':>5} {'Chunks':>7} {'Preds':>6} {'Status'}"
        )
        print("-" * 100)
        for s in summaries:
            status = "OK" if not s.error else f"ERR: {s.error[:25]}"
            print(
                f"{s.source_id:<35} {s.videos_considered:>5} {s.videos_skipped_title:>7} "
                f"{s.videos_skipped_duration:>7} {s.transcripts_fetched:>8} "
                f"{s.transcripts_failed:>5} {s.items_written:>7} "
                f"{s.predictions_extracted:>6} {status}"
            )

        if args.run_extraction:
            check_yield(summaries)

    finally:
        if db is not None:
            db.close()


if __name__ == "__main__":
    main()
