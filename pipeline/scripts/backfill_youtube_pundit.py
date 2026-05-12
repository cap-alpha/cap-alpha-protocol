"""
YouTube channel backfill for political (and any) pundits — issue #880.

Enumerates all videos from a YouTube channel via yt-dlp, filters by date,
and ingests transcripts into bronze_layer.raw_pundit_media.

Usage:
    # Backfill all GZERO World videos since 2022:
    python pipeline/scripts/backfill_youtube_pundit.py \\
        --source-id ian_bremmer_gzero \\
        --pundit-id ian_bremmer \\
        --pundit-name "Ian Bremmer" \\
        --channel-url "https://www.youtube.com/@gzeromedia/videos" \\
        --since 2022-01-01 \\
        --sport politics

    # Backfill specific video URLs (e.g. Roubini on Bloomberg):
    python pipeline/scripts/backfill_youtube_pundit.py \\
        --source-id nouriel_roubini \\
        --pundit-id nouriel_roubini \\
        --pundit-name "Nouriel Roubini" \\
        --sport politics \\
        --video-urls \\
            "https://www.youtube.com/watch?v=VIDEO_ID_1" \\
            "https://www.youtube.com/watch?v=VIDEO_ID_2"

    # Dry run (preview only, no BQ writes):
    python pipeline/scripts/backfill_youtube_pundit.py ... --dry-run

    # Find channel ID for media_sources.yaml:
    yt-dlp --flat-playlist --print channel_id "https://www.youtube.com/@gzeromedia" | head -1

Requirements:
    brew install yt-dlp   (for channel enumeration)
    pip install google-cloud-bigquery   (for BQ writes)
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Ensure pipeline/src is on the path when running from repo root
_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "pipeline"))

from src.db_manager import get_db_manager
from src.media_ingestor import ingest_from_urls

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
logger = logging.getLogger(__name__)


def _fetch_video_date(video_id: str) -> datetime | None:
    """
    Fetch the upload date for a single video via yt-dlp --dump-json.

    Used by enumerate_channel_videos when --fetch-dates is active.
    Returns None on failure.
    """
    url = f"https://www.youtube.com/watch?v={video_id}"
    cmd = ["yt-dlp", "--dump-json", "--no-playlist", "--no-warnings", url]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        )
        data = json.loads(result.stdout)
        date_str = data.get("upload_date", "")
        if date_str and len(date_str) == 8:
            return datetime.strptime(date_str, "%Y%m%d").replace(tzinfo=timezone.utc)
    except (
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        json.JSONDecodeError,
        ValueError,
    ):
        pass
    return None


def enumerate_channel_videos(
    channel_url: str,
    since: datetime | None = None,
    limit: int | None = None,
    fetch_dates: bool = False,
) -> list[str]:
    """
    Use yt-dlp to list all video URLs from a YouTube channel.

    Accepts any yt-dlp-supported channel URL:
      https://www.youtube.com/@gzeromedia/videos
      https://www.youtube.com/c/ChannelName/videos
      https://www.youtube.com/channel/UCxxxxxxxx/videos

    Returns a list of full YouTube watch URLs, optionally filtered by upload date.

    Date filtering and --since:
        YouTube channels via --flat-playlist often return upload_date=NA.  When
        that happens the date filter is silently skipped for those videos.  Pass
        fetch_dates=True (CLI: --fetch-dates) to do a per-video yt-dlp lookup
        that always returns an accurate date.  This is substantially slower
        (~1 req/video) but guarantees --since works correctly.
    """
    cmd = [
        "yt-dlp",
        "--flat-playlist",
        "--print",
        "%(upload_date)s %(id)s",
        "--no-warnings",
        channel_url,
    ]

    logger.info(f"Enumerating videos from: {channel_url}")
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,  # channel listings can be slow for large channels
            check=True,
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"yt-dlp failed (exit {e.returncode}): {e.stderr[:500]}"
        ) from e
    except FileNotFoundError:
        raise RuntimeError("yt-dlp not found. Install with: brew install yt-dlp")

    # Collect all video IDs and whatever dates the flat-playlist returned
    entries: list[tuple[str, datetime | None]] = []  # (video_id, upload_date | None)
    na_count = 0
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue

        parts = line.split(" ", 1)
        if len(parts) != 2:
            continue

        date_str, video_id = parts
        upload_date = None

        if date_str and date_str != "NA" and len(date_str) == 8:
            try:
                upload_date = datetime.strptime(date_str, "%Y%m%d").replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                pass
        else:
            na_count += 1

        entries.append((video_id, upload_date))

    if since is not None and na_count > 0:
        if fetch_dates:
            logger.info(
                f"{na_count} video(s) have no date from flat-playlist; "
                f"fetching individual dates (--fetch-dates mode) — this is slow."
            )
            resolved: list[tuple[str, datetime | None]] = []
            for video_id, upload_date in entries:
                if upload_date is None:
                    upload_date = _fetch_video_date(video_id)
                resolved.append((video_id, upload_date))
            entries = resolved
        else:
            logger.warning(
                f"--since is set but {na_count} video(s) returned upload_date=NA from "
                f"yt-dlp flat-playlist. Those videos will NOT be filtered by date. "
                f"Re-run with --fetch-dates for accurate date filtering (slower)."
            )

    urls = []
    for video_id, upload_date in entries:
        if since is not None and upload_date is not None and upload_date < since:
            continue

        url = f"https://www.youtube.com/watch?v={video_id}"
        urls.append(url)

        if limit and len(urls) >= limit:
            break

    logger.info(f"Found {len(urls)} video(s) after date filtering")
    return urls


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill YouTube transcripts for a pundit into BigQuery",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--source-id",
        required=True,
        help="Source ID matching media_sources.yaml (e.g. ian_bremmer_gzero)",
    )
    parser.add_argument(
        "--pundit-id",
        required=True,
        help="Pundit ID (e.g. ian_bremmer)",
    )
    parser.add_argument(
        "--pundit-name",
        required=True,
        help="Pundit display name (e.g. 'Ian Bremmer')",
    )
    parser.add_argument(
        "--sport",
        default="politics",
        help="Sport/domain tag (e.g. politics, finance, NFL). Default: politics",
    )

    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument(
        "--channel-url",
        help="YouTube channel URL (yt-dlp format, e.g. https://www.youtube.com/@gzeromedia/videos)",
    )
    source_group.add_argument(
        "--video-urls",
        nargs="+",
        metavar="URL",
        help="Explicit list of YouTube video URLs to ingest",
    )
    source_group.add_argument(
        "--urls-file",
        type=Path,
        help="Text file with one YouTube URL per line",
    )

    parser.add_argument(
        "--since",
        metavar="YYYY-MM-DD",
        help="Only ingest videos published on or after this date (channel mode only)",
    )
    parser.add_argument(
        "--fetch-dates",
        action="store_true",
        help=(
            "When --since is set, fetch upload dates per-video via yt-dlp --dump-json "
            "instead of relying on flat-playlist metadata (which often returns NA for "
            "YouTube channels). Accurate but ~1 extra request per video — slow on large channels."
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Max number of videos to process (useful for testing)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=4.0,
        metavar="SECONDS",
        help="Seconds to wait between each video fetch (default: 4 — stays under YouTube rate limits)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without writing to BigQuery",
    )

    args = parser.parse_args()

    since_dt: datetime | None = None
    if args.since:
        try:
            since_dt = datetime.strptime(args.since, "%Y-%m-%d").replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            parser.error(f"--since must be YYYY-MM-DD, got: {args.since}")

    # Collect video URLs
    if args.channel_url:
        video_urls = enumerate_channel_videos(
            args.channel_url,
            since=since_dt,
            limit=args.limit,
            fetch_dates=args.fetch_dates,
        )
    elif args.video_urls:
        video_urls = args.video_urls
        if args.limit:
            video_urls = video_urls[: args.limit]
    else:  # urls-file
        raw = Path(args.urls_file).read_text(encoding="utf-8")
        video_urls = [line.strip() for line in raw.splitlines() if line.strip()]
        if args.limit:
            video_urls = video_urls[: args.limit]

    if not video_urls:
        logger.info("No videos to process — exiting.")
        return

    eta_minutes = len(video_urls) * args.delay / 60
    logger.info(
        f"Backfilling {len(video_urls)} video(s) for "
        f"source={args.source_id} pundit={args.pundit_id} "
        f"(delay={args.delay}s, ETA ~{eta_minutes:.0f} min)"
    )

    db = None if args.dry_run else get_db_manager()
    total_new = 0
    try:
        for i, url in enumerate(video_urls):
            batch = ingest_from_urls(
                urls=[url],
                source_id=args.source_id,
                pundit_id=args.pundit_id,
                pundit_name=args.pundit_name,
                sport=args.sport,
                db=db,
                dry_run=args.dry_run,
            )
            total_new += len(batch)
            if (i + 1) % 10 == 0 or (i + 1) == len(video_urls):
                logger.info(f"[{i + 1}/{len(video_urls)}] {total_new} new items so far")
            if i < len(video_urls) - 1:
                time.sleep(args.delay)
    finally:
        if db is not None:
            db.close()

    status = "DRY RUN — " if args.dry_run else ""
    logger.info(
        f"{status}Backfill complete: {total_new} new item(s) ingested "
        f"for {args.pundit_name} ({args.source_id})"
    )


if __name__ == "__main__":
    main()
