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
from dataclasses import asdict, dataclass, field
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
# Pundit matching
# ---------------------------------------------------------------------------


def match_pundit(
    author: Optional[str], pundits: list[dict]
) -> tuple[Optional[str], Optional[str]]:
    """
    Matches an article author against the pundit registry for a source.
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


# ---------------------------------------------------------------------------
# Fetchers — one per source type
# ---------------------------------------------------------------------------


def fetch_rss(source: dict, defaults: dict) -> list[MediaItem]:
    """Fetches and parses an RSS feed, returning MediaItems."""
    url = source["url"]
    source_id = source["id"]
    pundits = source.get("pundits", [])
    sport = source.get("sport", "NFL")
    max_items = defaults.get("max_items_per_feed", 50)
    timeout = defaults.get("fetch_timeout_seconds", 30)

    logger.info(f"Fetching RSS: {source['name']} ({url})")
    feed = feedparser.parse(url, request_headers={"User-Agent": "PunditLedger/1.0"})

    if feed.bozo and not feed.entries:
        raise ValueError(f"Feed parse error for {source_id}: {feed.bozo_exception}")

    items = []
    now = datetime.now(timezone.utc)

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

        pundit_id, pundit_name = match_pundit(author, pundits)
        content_hash = compute_content_hash(link, title)

        content_type = "article"
        if source.get("type") == "youtube_rss":
            content_type = "video"

        metadata = {}
        if entry.get("tags"):
            metadata["tags"] = [t.get("term", "") for t in entry.tags]

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

    return items


TRANSCRIPT_CHUNK_SIZE = 3500


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
    """Extract video ID from a YouTube URL."""
    match = re.search(r"[?&]v=([a-zA-Z0-9_-]{11})", url)
    return match.group(1) if match else None


def fetch_youtube_transcripts(source: dict, defaults: dict) -> list[MediaItem]:
    """
    Fetches recent videos from a YouTube channel via RSS, then downloads
    auto-generated transcripts for each video.
    """
    url = source["url"]
    source_id = source["id"]
    pundits = source.get("pundits", [])
    sport = source.get("sport", "NFL")
    max_items = defaults.get("max_items_per_feed", 50)

    # Default pundit for YouTube channels (usually single-pundit channels)
    default_pundit = pundits[0] if pundits else {}
    author = default_pundit.get("name")
    pundit_id = default_pundit.get("id")
    pundit_name = default_pundit.get("name")

    logger.info(f"Fetching YouTube transcripts: {source['name']} ({url})")
    feed = feedparser.parse(url, request_headers={"User-Agent": "PunditLedger/1.0"})

    if feed.bozo and not feed.entries:
        raise ValueError(f"Feed parse error for {source_id}: {feed.bozo_exception}")

    items = []
    now = datetime.now(timezone.utc)

    for entry in feed.entries[:max_items]:
        title = entry.get("title", "")
        link = entry.get("link", "")
        if not link:
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

        # Download transcript
        try:
            transcript_data = YouTubeTranscriptApi.get_transcript(video_id)
            transcript_text = " ".join(segment["text"] for segment in transcript_data)
        except Exception as e:
            logger.warning(
                f"[{source_id}] Transcript unavailable for {video_id} "
                f"({title}): {e}"
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
) -> list[SourceResult]:
    """
    Main daily entry point. Iterates all enabled sources, fetches content,
    deduplicates, and writes to BigQuery.

    Returns a manifest of SourceResults for observability.
    """
    config = load_media_config(config_path)
    defaults = config.get("defaults", {})
    sources = config.get("sources", [])

    close_db = db is None
    if db is None:
        db = DBManager()

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
    args = parser.parse_args()

    config_path = Path(args.config) if args.config else None
    results = run_daily_ingestion(
        config_path=config_path,
        source_filter=args.source,
        dry_run=args.dry_run,
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
