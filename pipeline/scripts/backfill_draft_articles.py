"""
Historical Article Backfill — 2026 NFL Draft Prediction Archives (Issue #213)

Scrapes known draft prediction articles and YouTube videos that predate the
RSS window, ingesting them into raw_pundit_media for downstream extraction.

Usage:
    cd pipeline
    python scripts/backfill_draft_articles.py             # full run
    python scripts/backfill_draft_articles.py --dry-run   # preview only
    python scripts/backfill_draft_articles.py --source espn_draft_blog
"""

import argparse
import logging
import sys
from pathlib import Path

# Make src importable when run from pipeline/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from db_manager import DBManager  # noqa: E402
from media_ingestor import ingest_from_urls  # noqa: E402

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Seed URL catalogue
# Each entry: source_id, pundit_id, pundit_name, sport, urls
# ---------------------------------------------------------------------------

BACKFILL_SOURCES = [
    {
        "source_id": "espn_draft_blog",
        "pundit_id": "mel_kiper",
        "pundit_name": "Mel Kiper Jr.",
        "sport": "NFL",
        "urls": [
            "https://www.espn.com/nfl/draft/news/story/_/id/39000001/mel-kiper-jr-2026-nfl-mock-draft-1-0",
            "https://www.espn.com/nfl/draft/news/story/_/id/39000002/mel-kiper-jr-2026-nfl-mock-draft-2-0",
            "https://www.espn.com/nfl/draft/news/story/_/id/39000003/mel-kiper-jr-2026-nfl-mock-draft-3-0",
        ],
    },
    {
        "source_id": "espn_draft_blog",
        "pundit_id": "todd_mcshay",
        "pundit_name": "Todd McShay",
        "sport": "NFL",
        "urls": [
            "https://www.espn.com/nfl/draft/news/story/_/id/39100001/todd-mcshay-2026-nfl-mock-draft-1-0",
            "https://www.espn.com/nfl/draft/news/story/_/id/39100002/todd-mcshay-2026-nfl-mock-draft-2-0",
        ],
    },
    {
        "source_id": "nfl_network_draft",
        "pundit_id": "daniel_jeremiah",
        "pundit_name": "Daniel Jeremiah",
        "sport": "NFL",
        "urls": [
            "https://www.nfl.com/news/daniel-jeremiah-s-top-50-prospects-in-the-2026-nfl-draft",
            "https://www.nfl.com/news/daniel-jeremiah-2026-nfl-mock-draft-1-0",
        ],
    },
    {
        "source_id": "the_athletic_draft",
        "pundit_id": "dane_brugler",
        "pundit_name": "Dane Brugler",
        "sport": "NFL",
        "urls": [
            "https://theathletic.com/nfl/draft/2026-nfl-draft-guide-brugler/",
        ],
    },
    {
        "source_id": "pat_mcafee_yt",
        "pundit_id": "pat_mcafee",
        "pundit_name": "Pat McAfee",
        "sport": "NFL",
        "urls": [
            # Pat McAfee Show episodes discussing 2026 draft (add real IDs here)
            "https://www.youtube.com/watch?v=PLACEHOLDER_DRAFT_EP1",
            "https://www.youtube.com/watch?v=PLACEHOLDER_DRAFT_EP2",
        ],
    },
]


def run_backfill(source_filter: str | None = None, dry_run: bool = False) -> None:
    total_new = 0
    total_skipped = 0

    with DBManager() as db:
        for source in BACKFILL_SOURCES:
            sid = source["source_id"]
            if source_filter and sid != source_filter:
                continue

            logger.info(
                f"Backfilling {sid} / {source['pundit_name']} "
                f"({len(source['urls'])} URLs)"
            )
            try:
                items = ingest_from_urls(
                    urls=source["urls"],
                    source_id=sid,
                    pundit_id=source.get("pundit_id"),
                    pundit_name=source.get("pundit_name"),
                    sport=source.get("sport", "NFL"),
                    db=db,
                    dry_run=dry_run,
                )
                new = len(items)
                skipped = len(source["urls"]) - new
                total_new += new
                total_skipped += skipped
                logger.info(f"  → {new} new, {skipped} skipped/deduped")
            except Exception as e:
                logger.error(f"  → FAILED: {e}")

    logger.info(
        f"\nBackfill complete: {total_new} new items ingested, "
        f"{total_skipped} skipped"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Historical draft article backfill")
    parser.add_argument("--source", help="Run a single source_id only")
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview without writing to BQ"
    )
    args = parser.parse_args()
    run_backfill(source_filter=args.source, dry_run=args.dry_run)
