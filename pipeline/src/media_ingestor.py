"""
Daily Media Ingestion Pipeline (Issue #78)

Config-driven, fault-tolerant ingestor that fetches pundit content from RSS feeds
and YouTube channels, deduplicates by content hash, and lands everything in
bronze_layer (raw_pundit_media BigQuery table).

Designed to run every day without fail:
  - Each source is fetched independently — one failure doesn't block others
  - Per-source retries with exponential backoff
  - Content-hash dedup prevents re-ingesting the same article
  - Run manifest logged for observability

Usage (inside Docker):
    python -m src.media_ingestor                    # full daily run
    python -m src.media_ingestor --source espn_nfl  # single source
    python -m src.media_ingestor --dry-run          # preview without writing
"""

import argparse
import hashlib
import json
import logging
import os
import re
import time
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import feedparser
import pandas as pd
import requests
import yaml
from bs4 import BeautifulSoup
from google.cloud import bigquery
from youtube_transcript_api import YouTubeTranscriptApi

try:
    _yt_client = YouTubeTranscriptApi()
    _YT_API_V1 = True
except TypeError:
    _yt_client = None
    _YT_API_V1 = False

from src.db_manager import DBManager

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
logger = logging.getLogger(__name__)

RAW_MEDIA_TABLE = "raw_pundit_media"
CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "media_sources.yaml"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class MediaItem:
    content_hash: str
    source_id: str
    title: Optional[str]
    raw_text: Optional[str]
    source_url: str
    author: Optional[str]
    matched_pundit_id: Optional[str]
    matched_pundit_name: Optional[str]
    published_at: Optional[datetime]
    ingested_at: datetime
    content_type: str
    fetch_source_type: str
    sport: str = "NFL"  # NFL|MLB|NBA|NHL|NCAAF|NCAAB — set from media_sources.yaml
    raw_metadata: Optional[str] = None
    match_method: Optional[str] = (
        None  # author_field|byline_scan|source_default|unmatched
    )


@dataclass
class SourceResult:
    source_id: str
    source_name: str
    items_fetched: int = 0
    items_new: int = 0
    items_deduped: int = 0
    error: Optional[str] = None
    duration_seconds: float = 0.0


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------


def load_media_config(config_path: Optional[Path] = None) -> dict:
    path = config_path or CONFIG_PATH
    with open(path) as f:
        return yaml.safe_load(f)


def load_config_from_bq(
    db: DBManager, fallback_yaml_path: Optional[Path] = None
) -> dict:
    """Load source/pundit config from BigQuery registry, falling back to YAML.

    Tries to read from nfl_dead_money.source_registry and pundit_registry via
    RegistryManager.  If the registry is empty or unavailable, silently falls
    back to the static YAML config so the ingestor never stops working.

    Args:
        db: Active DBManager instance.
        fallback_yaml_path: Path to media_sources.yaml; uses default if None.

    Returns:
        Config dict in the same shape as load_media_config() (YAML format).
    """
    from src.registry_manager import RegistryManager  # local import to avoid circular

    try:
        rm = RegistryManager(db)
        config = rm.get_source_config()
        if config.get("sources"):
            logger.info(f"Loaded {len(config['sources'])} source(s) from BQ registry")
            # Merge YAML defaults section (BQ registry doesn't store global defaults)
            try:
                yaml_config = load_media_config(fallback_yaml_path)
                config.setdefault("defaults", yaml_config.get("defaults", {}))
            except Exception:
                config.setdefault("defaults", {})
            return config
        logger.info("BQ registry is empty — falling back to YAML config")
    except Exception as e:
        logger.warning(f"BQ registry unavailable ({e}) — falling back to YAML config")

    return load_media_config(fallback_yaml_path)


# ---------------------------------------------------------------------------
# Content hashing & dedup
# ---------------------------------------------------------------------------


def compute_content_hash(source_url: str, title: str = "") -> str:
    """Deterministic hash for dedup. Based on URL + title to handle URL-only dupes."""
    payload = f"{source_url}|{title or ''}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def get_existing_hashes(db: DBManager, source_id: str, window_days: int = 7) -> set:
    """Fetches content_hashes ingested in the last N days for a source to dedup against."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=window_days)).isoformat()
    project_id = os.environ.get("GCP_PROJECT_ID")
    query = f"""
        SELECT content_hash
        FROM `{project_id}.nfl_dead_money.{RAW_MEDIA_TABLE}`
        WHERE source_id = '{source_id}'
          AND ingested_at >= '{cutoff}'
    """
    try:
        df = db.fetch_df(query)
        return set(df["content_hash"].tolist()) if not df.empty else set()
    except Exception as e:
        logger.warning(f"Could not fetch existing hashes for {source_id}: {e}")
        return set()


# ---------------------------------------------------------------------------
# Pundit matching (cascade: author field → byline scan → source-level → DLQ)
# ---------------------------------------------------------------------------


def match_pundit_by_author(
    author: Optional[str], pundits: list[dict]
) -> tuple[Optional[str], Optional[str]]:
    """
    Matches an article's author field against the pundit registry.
    Returns (pundit_id, pundit_name) or (None, None).
    """
    if not author:
        return None, None

    author_lower = author.lower().strip()
    for pundit in pundits:
        for pattern in pundit.get("match_authors", []):
            if pattern.lower() in author_lower:
                return pundit["id"], pundit["name"]
    return None, None


def match_pundit_by_byline(
    raw_text: Optional[str], pundits: list[dict]
) -> tuple[Optional[str], Optional[str]]:
    """
    Scans the first 500 characters of article text for pundit names.
    Catches cases where RSS author field is missing but the byline is in body text.
    Returns (pundit_id, pundit_name) or (None, None).
    """
    if not raw_text:
        return None, None

    # Bylines are almost always in the first 500 chars
    head = raw_text[:500].lower()
    for pundit in pundits:
        name = pundit["name"].lower()
        if name in head:
            return pundit["id"], pundit["name"]
        # Also try match_authors patterns (handles "mflorio" etc.)
        for pattern in pundit.get("match_authors", []):
            if pattern.lower() in head:
                return pundit["id"], pundit["name"]
    return None, None


def match_pundit(
    author: Optional[str],
    pundits: list[dict],
    raw_text: Optional[str] = None,
    source: Optional[dict] = None,
) -> tuple[Optional[str], Optional[str], str]:
    """
    Three-tier pundit matching cascade. Returns (pundit_id, pundit_name, match_method).

    Cascade:
      1. Author field match (RSS author / dc:creator)
      2. Byline scan (first 500 chars of article body)
      3. Source-level attribution (e.g. "ESPN Staff" for multi-author feeds)

    match_method is one of: "author_field", "byline_scan", "source_default", "unmatched"
    """
    # Tier 1: author field
    pid, pname = match_pundit_by_author(author, pundits)
    if pid:
        return pid, pname, "author_field"

    # Tier 2: byline scan (body text)
    pid, pname = match_pundit_by_byline(raw_text, pundits)
    if pid:
        return pid, pname, "byline_scan"

    # Tier 3: source-level default attribution
    if source:
        default = source.get("default_pundit")
        if default:
            return default["id"], default["name"], "source_default"

    return None, None, "unmatched"


# ---------------------------------------------------------------------------
# Fetchers — one per source type
# ---------------------------------------------------------------------------


def _passes_keyword_filter(title: str, text: str, keywords: list[str]) -> bool:
    """Check if title or text contains at least one keyword (case-insensitive)."""
    combined = f"{title} {text}".lower()
    return any(kw.lower() in combined for kw in keywords)


def fetch_rss(source: dict, defaults: dict) -> list[MediaItem]:
    """Fetches and parses an RSS feed, returning MediaItems."""
    url = source["url"]
    source_id = source["id"]
    pundits = source.get("pundits", [])
    sport = source.get("sport", "NFL")
    max_items = defaults.get("max_items_per_feed", 50)
    timeout = defaults.get("fetch_timeout_seconds", 30)
    keyword_filter = source.get("keyword_filter", [])

    logger.info(f"Fetching RSS: {source['name']} ({url})")
    feed = feedparser.parse(url, request_headers={"User-Agent": "PunditLedger/1.0"})

    if feed.bozo and not feed.entries:
        raise ValueError(f"Feed parse error for {source_id}: {feed.bozo_exception}")

    items = []
    now = datetime.now(timezone.utc)
    skipped_by_filter = 0

    for entry in feed.entries[:max_items]:
        title = entry.get("title", "")
        link = entry.get("link", "")
        if not link:
            continue

        # Extract author
        author = entry.get("author", entry.get("dc_creator", None))

        # Parse published date
        published = None
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            try:
                published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            except Exception:
                pass

        # Extract text content
        raw_text = ""
        if hasattr(entry, "summary"):
            raw_text = BeautifulSoup(entry.summary, "html.parser").get_text(
                separator=" ", strip=True
            )
        if hasattr(entry, "content"):
            for c in entry.content:
                text = BeautifulSoup(c.get("value", ""), "html.parser").get_text(
                    separator=" ", strip=True
                )
                if len(text) > len(raw_text):
                    raw_text = text

        # Apply keyword filter if configured (skip non-matching entries)
        if keyword_filter and not _passes_keyword_filter(
            title, raw_text, keyword_filter
        ):
            skipped_by_filter += 1
            continue

        pundit_id, pundit_name, match_method = match_pundit(
            author, pundits, raw_text=raw_text, source=source
        )
        content_hash = compute_content_hash(link, title)

        content_type = "article"
        if source.get("type") == "youtube_rss":
            content_type = "video"

        metadata = {}
        if entry.get("tags"):
            metadata["tags"] = [t.get("term", "") for t in entry.tags]
        if match_method:
            metadata["match_method"] = match_method

        items.append(
            MediaItem(
                content_hash=content_hash,
                source_id=source_id,
                title=title,
                raw_text=raw_text,
                source_url=link,
                author=author,
                matched_pundit_id=pundit_id,
                matched_pundit_name=pundit_name,
                published_at=published,
                ingested_at=now,
                content_type=content_type,
                fetch_source_type=source.get("type", "rss"),
                sport=sport,
                raw_metadata=json.dumps(metadata) if metadata else None,
            )
        )

    if skipped_by_filter:
        logger.info(
            f"[{source_id}] Keyword filter skipped {skipped_by_filter} non-matching entries"
        )

    return items


TRANSCRIPT_CHUNK_SIZE = 3500

# Prediction-dense title filter — skip YouTube videos that are clearly not
# prediction content (game recaps, highlight compilations, interviews, etc.)
_PREDICTION_TITLE_RE = re.compile(
    r"""
    predict|bold|will\s|won['']?t|preview|grade|rank|MVP|
    playoff|over[.\-/]under|win\s+total|lock\s+of|pick\s|picks\s|
    bold\s+call|super\s+bowl|nfl\s+draft|free\s+agent|hot\s+take|
    week\s+\d+|game\s+day|breakdown|who\s+wins|should\s+the|
    bet|prop|sleeper|bust|breakout|fantasy
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _chunk_transcript(text: str, max_chars: int = TRANSCRIPT_CHUNK_SIZE) -> list[str]:
    """Split transcript text into chunks of ~max_chars, splitting at sentence boundaries."""
    if len(text) <= max_chars:
        return [text]

    chunks = []
    remaining = text
    while remaining:
        if len(remaining) <= max_chars:
            chunks.append(remaining)
            break

        # Find last sentence boundary within the limit
        split_at = max_chars
        # Look for sentence-ending punctuation followed by a space
        last_sentence = -1
        for match in re.finditer(r"[.!?]\s", remaining[:max_chars]):
            last_sentence = match.end()

        if last_sentence > 0:
            split_at = last_sentence
        else:
            # Fall back to last space
            last_space = remaining[:max_chars].rfind(" ")
            if last_space > 0:
                split_at = last_space + 1

        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()

    return chunks


def _extract_video_id(url: str) -> str | None:
    """Extract video ID from a YouTube URL (watch?v= or /shorts/)."""
    match = re.search(r"[?&]v=([a-zA-Z0-9_-]{11})", url)
    if match:
        return match.group(1)
    match = re.search(r"/shorts/([a-zA-Z0-9_-]{11})", url)
    return match.group(1) if match else None


def _is_youtube_short(url: str) -> bool:
    """Return True if the URL points to a YouTube Short."""
    return "/shorts/" in url


def _fetch_transcript_ytdlp(video_id: str) -> str:
    """Fallback: use yt-dlp to download auto-generated subtitles as VTT, return plain text."""
    import subprocess
    import tempfile
    from pathlib import Path as _Path

    url = f"https://www.youtube.com/watch?v={video_id}"
    with tempfile.TemporaryDirectory() as tmpdir:
        out_template = str(_Path(tmpdir) / "%(id)s.%(ext)s")
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
            timeout=60,
        )
        vtt_files = list(_Path(tmpdir).glob("*.vtt"))
        if not vtt_files:
            raise FileNotFoundError(f"yt-dlp produced no VTT for {video_id}")
        vtt_text = vtt_files[0].read_text(encoding="utf-8", errors="ignore")
    lines = []
    for line in vtt_text.splitlines():
        line = line.strip()
        if not line or line.startswith("WEBVTT") or line.startswith("NOTE"):
            continue
        if re.match(r"^\d{2}:\d{2}:\d{2}", line) or re.match(
            r"^<\d{2}:\d{2}:\d{2}", line
        ):
            continue
        cleaned = re.sub(r"<[^>]+>", "", line).strip()
        if cleaned:
            lines.append(cleaned)
    return " ".join(lines)


def _fetch_transcript(video_id: str) -> str:
    """Fetch transcript text, trying youtube-transcript-api then yt-dlp fallback."""
    e1 = None
    try:
        if _YT_API_V1 and _yt_client is not None:
            result = _yt_client.fetch(video_id)
            text = " ".join(snippet.text for snippet in result)
        else:
            transcript_data = YouTubeTranscriptApi.get_transcript(video_id)
            text = " ".join(segment["text"] for segment in transcript_data)
        if text.strip():
            return text
    except Exception as exc:
        e1 = exc

    # Fallback: yt-dlp (handles blocked/disabled captions and API changes)
    try:
        text = _fetch_transcript_ytdlp(video_id)
        if text.strip():
            return text
    except Exception as e2:
        raise RuntimeError(
            f"Transcript unavailable via yt-api ({e1}) and yt-dlp ({e2})"
        ) from e2

    raise RuntimeError(f"Empty transcript for {video_id} (yt-api error: {e1})")


_MAX_YOUTUBE_DURATION_SECONDS = 90 * 60  # 90 minutes
_MIN_YOUTUBE_PUBLISH_YEAR = 2020


def fetch_youtube_transcripts(source: dict, defaults: dict) -> list[MediaItem]:
    """
    Fetches recent videos from a YouTube channel via RSS, then downloads
    auto-generated transcripts for each video.

    Applies optional filters from source config:
      - title_filter: false (default, opt-in) — set true to only fetch prediction-dense titles
      - max_duration_seconds: skip videos longer than N seconds (default 5400 = 90 min)
      - min_publish_year: skip videos published before this year (default 2020)
    """
    url = source["url"]
    source_id = source["id"]
    pundits = source.get("pundits", [])
    sport = source.get("sport", "NFL")
    max_items = defaults.get("max_items_per_feed", 50)
    apply_title_filter = source.get("title_filter", False)
    max_duration = source.get("max_duration_seconds", _MAX_YOUTUBE_DURATION_SECONDS)
    min_year = source.get("min_publish_year", _MIN_YOUTUBE_PUBLISH_YEAR)

    # Default pundit for YouTube channels (usually single-pundit channels)
    default_pundit = pundits[0] if pundits else source.get("default_pundit", {})
    author = default_pundit.get("name")
    pundit_id = default_pundit.get("id")
    pundit_name = default_pundit.get("name")

    logger.info(f"Fetching YouTube transcripts: {source['name']} ({url})")
    feed = feedparser.parse(url, request_headers={"User-Agent": "PunditLedger/1.0"})

    if feed.bozo and not feed.entries:
        raise ValueError(f"Feed parse error for {source_id}: {feed.bozo_exception}")

    if not feed.entries:
        logger.warning(
            f"[{source_id}] YouTube feed returned 0 entries — "
            f"check channel ID in URL: {url}"
        )

    items = []
    now = datetime.now(timezone.utc)
    skipped_title = 0
    skipped_date = 0

    for entry in feed.entries[: max_items * 3]:  # over-fetch to allow for filtering
        if len(items) >= max_items:
            break

        title = entry.get("title", "")
        link = entry.get("link", "")
        if not link:
            continue

        # Skip Shorts — they are clips (<60s), rarely have auto-captions,
        # and don't contain full-length pundit commentary worth extracting.
        if _is_youtube_short(link):
            logger.debug(f"[{source_id}] Skipping Short: {title}")
            continue

        # Title filter: skip videos that are clearly not prediction content
        if apply_title_filter and not _PREDICTION_TITLE_RE.search(title):
            skipped_title += 1
            logger.debug(f"[{source_id}] Title filter skipped: {title}")
            continue

        video_id = _extract_video_id(link)
        if not video_id:
            logger.warning(f"[{source_id}] Could not extract video ID from {link}")
            continue

        # Parse published date
        published = None
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            try:
                published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            except Exception:
                pass

        # Date filter: skip pre-2020 content (resolver coverage limit)
        if published is not None and published.year < min_year:
            skipped_date += 1
            logger.debug(
                f"[{source_id}] Date filter skipped ({published.year}): {title}"
            )
            continue

        # Download transcript
        try:
            transcript_text = _fetch_transcript(video_id)
        except Exception as e:
            logger.warning(
                f"[{source_id}] Transcript unavailable for {video_id} ({title}): {e}"
            )
            continue

        if not transcript_text.strip():
            continue

        # Chunk if needed
        chunks = _chunk_transcript(transcript_text)

        for i, chunk in enumerate(chunks):
            is_chunked = len(chunks) > 1
            chunk_suffix = f"|chunk_{i}" if is_chunked else ""
            chunk_title = f"{title} (part {i + 1})" if is_chunked else title

            content_hash = compute_content_hash(link + chunk_suffix)

            items.append(
                MediaItem(
                    content_hash=content_hash,
                    source_id=source_id,
                    title=chunk_title,
                    raw_text=chunk,
                    source_url=link,
                    author=author,
                    matched_pundit_id=pundit_id,
                    matched_pundit_name=pundit_name,
                    published_at=published,
                    ingested_at=now,
                    content_type="transcript",
                    fetch_source_type="youtube_transcript",
                    sport=sport,
                )
            )

    if skipped_title:
        logger.info(
            f"[{source_id}] Title filter skipped {skipped_title} non-prediction videos"
        )
    if skipped_date:
        logger.info(
            f"[{source_id}] Date filter skipped {skipped_date} pre-{min_year} videos"
        )
    if not items and feed.entries:
        logger.warning(
            f"[{source_id}] Feed had {len(feed.entries)} entries "
            f"but 0 transcripts succeeded"
        )

    return items


def _scrape_article_text(url: str, timeout: int = 15) -> Optional[str]:
    """Fetch a URL and extract article body text using readability-lxml."""
    try:
        from readability import Document

        resp = requests.get(
            url, timeout=timeout, headers={"User-Agent": "PunditLedger/1.0"}
        )
        resp.raise_for_status()
        doc = Document(resp.text)
        from lxml.html import fromstring

        clean = fromstring(doc.summary())
        text = clean.text_content().strip()
        return text if len(text) > 100 else None  # skip if extraction failed
    except Exception as e:
        logger.warning(f"Failed to scrape {url}: {e}")
        return None


def _enrich_with_full_text(items: list[MediaItem], source: dict) -> list[MediaItem]:
    """If source has scrape_full_text enabled, fetch full article text for each item."""
    if not source.get("scrape_full_text"):
        return items

    scrape_delay = source.get("scrape_delay_seconds", 0.5)
    enriched = []
    for i, item in enumerate(items):
        full_text = _scrape_article_text(item.source_url)
        if full_text:
            item = replace(item, raw_text=full_text)
        enriched.append(item)
        # Rate-limit between requests (skip delay after last item)
        if i < len(items) - 1:
            time.sleep(scrape_delay)

    return enriched


def ingest_from_urls(
    urls: list[str],
    source_id: str,
    pundit_id: Optional[str] = None,
    pundit_name: Optional[str] = None,
    sport: str = "NFL",
    db: Optional["DBManager"] = None,
    dry_run: bool = False,
) -> list[MediaItem]:
    """
    Ingest content from an explicit list of URLs (historical backfill).

    - YouTube URLs (youtube.com/watch, youtu.be): fetch transcript
    - Web articles: scrape full text via readability-lxml
    - Deduplicates against all existing BQ records for source_id
    - Writes new items to raw_pundit_media unless dry_run=True

    Returns the list of new MediaItems ingested (or that would be ingested).
    """
    now = datetime.now(timezone.utc)

    # Use a very wide window (all-time) for backfill dedup
    existing_hashes: set = set()
    if db is not None:
        existing_hashes = get_existing_hashes(db, source_id, window_days=3650)

    items: list[MediaItem] = []
    for url in urls:
        is_yt = "youtube.com/watch" in url or "youtu.be/" in url or "/shorts/" in url

        if is_yt:
            video_id = _extract_video_id(url)
            if not video_id:
                logger.warning(f"[backfill] Could not extract video ID from {url}")
                continue

            try:
                transcript_text = _fetch_transcript(video_id)
            except Exception as e:
                logger.warning(f"[backfill] Transcript unavailable for {video_id}: {e}")
                continue

            if not transcript_text.strip():
                continue

            chunks = _chunk_transcript(transcript_text)
            for i, chunk in enumerate(chunks):
                is_chunked = len(chunks) > 1
                chunk_suffix = f"|chunk_{i}" if is_chunked else ""
                chunk_title = f"YouTube video {video_id}" + (
                    f" (part {i + 1})" if is_chunked else ""
                )
                content_hash = compute_content_hash(url + chunk_suffix)
                if content_hash in existing_hashes:
                    continue

                items.append(
                    MediaItem(
                        content_hash=content_hash,
                        source_id=source_id,
                        title=chunk_title,
                        raw_text=chunk,
                        source_url=url,
                        author=pundit_name,
                        matched_pundit_id=pundit_id,
                        matched_pundit_name=pundit_name,
                        published_at=None,
                        ingested_at=now,
                        content_type="transcript",
                        fetch_source_type="youtube_transcript",
                        sport=sport,
                        match_method="source_default" if pundit_id else "unmatched",
                    )
                )

        else:
            # Web article — scrape full text
            raw_text = _scrape_article_text(url)
            if not raw_text:
                logger.warning(f"[backfill] Failed to scrape article: {url}")
                continue

            content_hash = compute_content_hash(url)
            if content_hash in existing_hashes:
                logger.debug(f"[backfill] Already ingested: {url}")
                continue

            items.append(
                MediaItem(
                    content_hash=content_hash,
                    source_id=source_id,
                    title=None,
                    raw_text=raw_text,
                    source_url=url,
                    author=pundit_name,
                    matched_pundit_id=pundit_id,
                    matched_pundit_name=pundit_name,
                    published_at=None,
                    ingested_at=now,
                    content_type="article",
                    fetch_source_type="web_scrape",
                    sport=sport,
                    match_method="source_default" if pundit_id else "unmatched",
                )
            )

    if items and not dry_run and db is not None:
        rows = [
            {
                "content_hash": item.content_hash,
                "source_id": item.source_id,
                "title": item.title,
                "raw_text": item.raw_text,
                "source_url": item.source_url,
                "author": item.author,
                "matched_pundit_id": item.matched_pundit_id,
                "matched_pundit_name": item.matched_pundit_name,
                "published_at": item.published_at,
                "ingested_at": item.ingested_at,
                "content_type": item.content_type,
                "fetch_source_type": item.fetch_source_type,
                "sport": item.sport,
                "raw_metadata": item.raw_metadata,
            }
            for item in items
        ]
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
        logger.info(f"[backfill] Wrote {len(items)} new items for source '{source_id}'")
    elif dry_run and items:
        logger.info(
            f"[backfill] DRY RUN: would write {len(items)} new items "
            f"for source '{source_id}'"
        )

    return items


FETCHERS = {
    "rss": fetch_rss,
    "youtube_rss": fetch_rss,  # YouTube Atom feeds work with feedparser
    "youtube_transcript": fetch_youtube_transcripts,
}


# ---------------------------------------------------------------------------
# Core ingestor
# ---------------------------------------------------------------------------


def ingest_source(
    source: dict,
    defaults: dict,
    db: DBManager,
    dry_run: bool = False,
) -> SourceResult:
    """
    Fetches content from a single source, deduplicates, and writes new items to BQ.
    Returns a SourceResult manifest entry.
    """
    source_id = source["id"]
    source_name = source["name"]
    source_type = source.get("type", "rss")
    max_retries = defaults.get("max_retries", 3)
    backoff = defaults.get("retry_backoff_seconds", 5)
    dedup_window = defaults.get("dedup_window_days", 7)

    result = SourceResult(source_id=source_id, source_name=source_name)
    start = time.time()

    fetcher = FETCHERS.get(source_type)
    if not fetcher:
        result.error = f"No fetcher for source type: {source_type}"
        logger.error(result.error)
        return result

    # Retry loop
    items = []
    for attempt in range(1, max_retries + 1):
        try:
            items = fetcher(source, defaults)
            break
        except Exception as e:
            if attempt == max_retries:
                result.error = f"Failed after {max_retries} attempts: {e}"
                logger.error(f"[{source_id}] {result.error}")
                result.duration_seconds = time.time() - start
                return result
            logger.warning(
                f"[{source_id}] Attempt {attempt}/{max_retries} failed: {e}. "
                f"Retrying in {backoff * attempt}s..."
            )
            time.sleep(backoff * attempt)

    result.items_fetched = len(items)

    if not items:
        result.duration_seconds = time.time() - start
        return result

    # Enrich with full article text if configured
    items = _enrich_with_full_text(items, source)

    # Dedup against existing BQ data
    existing_hashes = get_existing_hashes(db, source_id, dedup_window)
    new_items = [item for item in items if item.content_hash not in existing_hashes]
    result.items_deduped = len(items) - len(new_items)
    result.items_new = len(new_items)

    if new_items and not dry_run:
        rows = [
            {
                "content_hash": item.content_hash,
                "source_id": item.source_id,
                "title": item.title,
                "raw_text": item.raw_text,
                "source_url": item.source_url,
                "author": item.author,
                "matched_pundit_id": item.matched_pundit_id,
                "matched_pundit_name": item.matched_pundit_name,
                "published_at": item.published_at,
                "ingested_at": item.ingested_at,
                "content_type": item.content_type,
                "fetch_source_type": item.fetch_source_type,
                "sport": item.sport,
                "raw_metadata": item.raw_metadata,
            }
            for item in new_items
        ]
        df = pd.DataFrame(rows)
        # Ensure nullable columns don't write string "None" to BigQuery
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
        logger.info(
            f"[{source_id}] Wrote {len(new_items)} new items "
            f"({result.items_deduped} deduped)"
        )
    elif dry_run and new_items:
        logger.info(f"[{source_id}] DRY RUN: would write {len(new_items)} new items")

    result.duration_seconds = time.time() - start
    return result


def run_daily_ingestion(
    config_path: Optional[Path] = None,
    source_filter: Optional[str] = None,
    dry_run: bool = False,
    db: Optional[DBManager] = None,
    use_bq_registry: bool = False,
) -> list[SourceResult]:
    """
    Main daily entry point. Iterates all enabled sources, fetches content,
    deduplicates, and writes to BigQuery.

    Args:
        config_path: Path to media_sources.yaml. Ignored when use_bq_registry=True.
        source_filter: If set, only process the source with this ID.
        dry_run: Preview without writing to BQ.
        db: Existing DBManager to reuse; creates one if None.
        use_bq_registry: When True, load source/pundit config from BQ registry
            (nfl_dead_money.source_registry + pundit_registry) with automatic
            YAML fallback. When False (default), load from YAML only.

    Returns a manifest of SourceResults for observability.
    """
    close_db = db is None
    if db is None:
        db = DBManager()

    if use_bq_registry:
        config = load_config_from_bq(db, fallback_yaml_path=config_path)
    else:
        config = load_media_config(config_path)
    defaults = config.get("defaults", {})
    sources = config.get("sources", [])

    results = []
    try:
        for source in sources:
            if not source.get("enabled", True):
                logger.info(f"Skipping disabled source: {source['id']}")
                continue

            if source_filter and source["id"] != source_filter:
                continue

            try:
                result = ingest_source(source, defaults, db, dry_run=dry_run)
                results.append(result)
            except Exception as e:
                # Catch-all: never let one source crash the entire run
                logger.error(f"Unexpected error on source {source['id']}: {e}")
                results.append(
                    SourceResult(
                        source_id=source["id"],
                        source_name=source.get("name", ""),
                        error=str(e),
                    )
                )

        # Log run manifest
        total_new = sum(r.items_new for r in results)
        total_errors = sum(1 for r in results if r.error)
        logger.info(
            f"Daily ingestion complete: {len(results)} sources, "
            f"{total_new} new items, {total_errors} errors"
        )

        if total_errors > 0:
            for r in results:
                if r.error:
                    logger.warning(f"  FAILED: {r.source_id} — {r.error}")

        return results
    finally:
        if close_db:
            db.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Daily Pundit Media Ingestor")
    parser.add_argument("--source", help="Run a single source by ID (e.g. espn_nfl)")
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview without writing to BQ"
    )
    parser.add_argument(
        "--config", help="Path to media_sources.yaml (default: pipeline/config/)"
    )
    parser.add_argument(
        "--use-bq-registry",
        action="store_true",
        help="Load source/pundit config from BQ registry (falls back to YAML)",
    )
    args = parser.parse_args()

    config_path = Path(args.config) if args.config else None
    results = run_daily_ingestion(
        config_path=config_path,
        source_filter=args.source,
        dry_run=args.dry_run,
        use_bq_registry=args.use_bq_registry,
    )

    # Print summary table
    print(
        f"\n{'Source':<25} {'Fetched':>8} {'New':>6} {'Dedup':>6} {'Time':>8} {'Status'}"
    )
    print("-" * 75)
    for r in results:
        status = "OK" if not r.error else f"ERR: {r.error[:30]}"
        print(
            f"{r.source_id:<25} {r.items_fetched:>8} {r.items_new:>6} "
            f"{r.items_deduped:>6} {r.duration_seconds:>7.1f}s {status}"
        )
