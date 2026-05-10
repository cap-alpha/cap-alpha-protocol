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
from datetime import datetime, timezone
from pathlib import Path

# Ensure pipeline/src is on the path when running from repo root
_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "pipeline"))

from src.db_manager import DBManager
from src.media_ingestor import ingest_from_urls

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
logger = logging.getLogger(__name__)


def enumerate_channel_videos(
    channel_url: str,
    since: datetime | None = None,
    limit: int | None = None,
) -> list[str]:
    """
    Use yt-dlp to list all video URLs from a YouTube channel.

    Accepts any yt-dlp-supported channel URL:
      https://www.youtube.com/@gzeromedia/videos
      https://www.youtube.com/c/ChannelName/videos
      https://www.youtube.com/channel/UCxxxxxxxx/videos

    Returns a list of full YouTube watch URLs, optionally filtered by upload date.
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

    urls = []
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
        "--limit",
        type=int,
        help="Max number of videos to process (useful for testing)",
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
            args.channel_url, since=since_dt, limit=args.limit
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

    logger.info(
        f"Backfilling {len(video_urls)} video(s) for "
        f"source={args.source_id} pundit={args.pundit_id}"
    )

    db = None if args.dry_run else DBManager()
    try:
        new_items = ingest_from_urls(
            urls=video_urls,
            source_id=args.source_id,
            pundit_id=args.pundit_id,
            pundit_name=args.pundit_name,
            sport=args.sport,
            db=db,
            dry_run=args.dry_run,
        )
    finally:
        if db is not None:
            db.close()

    status = "DRY RUN — " if args.dry_run else ""
    logger.info(
        f"{status}Backfill complete: {len(new_items)} new item(s) ingested "
        f"for {args.pundit_name} ({args.source_id})"
    )

    if args.dry_run and new_items:
        sample = new_items[0]
        print("\nSample item (dry run):")
        print(f"  source_url : {sample.source_url}")
        print(f"  title      : {sample.title}")
        print(f"  pundit     : {sample.matched_pundit_name}")
        print(f"  sport      : {sample.sport}")
        print(f"  text_len   : {len(sample.raw_text or '')} chars")


if __name__ == "__main__":
    main()
