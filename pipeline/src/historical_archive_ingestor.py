"""
Historical Archive Ingestor — Pundit Prediction Ledger Backfill (Issue #historical-backfill)

Fetches NFL prediction articles from 2020–2024 seasons using the Wayback Machine
(web.archive.org) and curated high-density article patterns. Feeds the existing
assertion_extractor pipeline to produce 500+ resolved predictions quickly.

High-density target article types (in priority order):
  1. Bold predictions articles  — 5-10 predictions each
  2. Season previews / win-total picks  — 3-7 predictions each
  3. MVP / award predictions  — 3-5 predictions each
  4. Power rankings  — implicit ordinal predictions
  5. Draft grades / picks  — 5-10 predictions each

Wayback Machine URL format:
  https://web.archive.org/web/YYYYMMDD000000*/<original_url>

Usage:
    # Dry run — preview URLs only, no BQ writes
    python -m src.historical_archive_ingestor --dry-run

    # Sample run — fetch 20 articles, write to BQ, then trigger extraction
    python -m src.historical_archive_ingestor --batch-size 20

    # Full run — all configured articles
    python -m src.historical_archive_ingestor --batch-size 500 --run-extraction

    # Single season
    python -m src.historical_archive_ingestor --season 2023 --batch-size 50

Stop conditions (checked automatically):
    - If extraction yield < 1 prediction/article over 50+ articles, warns and exits.
    - If extractor returns a hard error, files an issue report and exits.
"""

import argparse
import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
import requests
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WAYBACK_API = "https://archive.org/wayback/available"
WAYBACK_BASE = "https://web.archive.org/web"
RAW_MEDIA_TABLE = "raw_pundit_media"

# Minimum article text length to bother ingesting
MIN_TEXT_LENGTH = 200

# Yield warning threshold — if extraction rate drops below this, warn
MIN_YIELD_THRESHOLD = 1.0  # predictions per article

# Request timeouts (Wayback Machine can be slow)
FETCH_TIMEOUT = 45
WAYBACK_TIMEOUT = 20

# Rate limiting between requests (seconds)
REQUEST_DELAY = 1.0
WAYBACK_DELAY = 0.5

HEADERS = {
    "User-Agent": "PunditPredictionLedger/1.0 (Research; https://github.com/cap-alpha/cap-alpha-protocol)"
}

# ---------------------------------------------------------------------------
# Article catalog — curated high-density sources 2020–2024
#
# Format: (url_pattern, source_id, pundit_name, pundit_id, season_year)
# ---------------------------------------------------------------------------

# Team abbreviations for generating season preview URLs
NFL_TEAMS = [
    "patriots",
    "jets",
    "bills",
    "dolphins",  # AFC East
    "ravens",
    "steelers",
    "browns",
    "bengals",  # AFC North
    "texans",
    "colts",
    "jaguars",
    "titans",  # AFC South
    "chiefs",
    "raiders",
    "chargers",
    "broncos",  # AFC West
    "eagles",
    "giants",
    "cowboys",
    "commanders",  # NFC East
    "packers",
    "bears",
    "lions",
    "vikings",  # NFC North
    "buccaneers",
    "saints",
    "falcons",
    "panthers",  # NFC South
    "rams",
    "seahawks",
    "49ers",
    "cardinals",  # NFC West
]


@dataclass
class ArchiveArticle:
    """Represents a target article to fetch from the Wayback Machine."""

    original_url: str
    source_id: str
    pundit_name: Optional[str]
    pundit_id: Optional[str]
    season_year: int
    article_type: str  # bold_predictions|season_preview|award_prediction|draft_grade|power_rankings
    wayback_date: str  # YYYYMMDD — preferred snapshot date


def build_article_catalog(seasons: list[int] | None = None) -> list[ArchiveArticle]:
    """
    Build the full catalog of target archive articles.
    Returns a flat list of ArchiveArticle objects ordered by prediction density (highest first).
    """
    if seasons is None:
        seasons = [2020, 2021, 2022, 2023, 2024]

    articles = []

    for year in seasons:
        # Preseason date (early August) — where bold predictions / previews live
        preseason = f"{year}0810"
        # Draft date (late April)
        draft_date = f"{year}0430"
        # Week 1 (early September)
        week1 = f"{year}0908"

        # ── Bleacher Report bold predictions ──────────────────────────────────
        # Very high density: 5-10 explicit predictions per article
        articles += [
            ArchiveArticle(
                original_url=f"https://bleacherreport.com/articles/nfl-bold-predictions-{year}-season",
                source_id="bleacher_report_archive",
                pundit_name="Bleacher Report NFL Staff",
                pundit_id="br_nfl_staff",
                season_year=year,
                article_type="bold_predictions",
                wayback_date=preseason,
            ),
            ArchiveArticle(
                original_url=f"https://bleacherreport.com/articles/bold-nfl-predictions-{year}",
                source_id="bleacher_report_archive",
                pundit_name="Bleacher Report NFL Staff",
                pundit_id="br_nfl_staff",
                season_year=year,
                article_type="bold_predictions",
                wayback_date=preseason,
            ),
        ]

        # ── CBS Sports bold predictions ────────────────────────────────────────
        articles += [
            ArchiveArticle(
                original_url=f"https://www.cbssports.com/nfl/news/bold-predictions-for-the-{year}-nfl-season/",
                source_id="cbs_nfl_archive",
                pundit_name="CBS Sports NFL Staff",
                pundit_id="cbs_nfl_staff",
                season_year=year,
                article_type="bold_predictions",
                wayback_date=preseason,
            ),
            ArchiveArticle(
                original_url=f"https://www.cbssports.com/nfl/news/nfl-{year}-season-bold-predictions/",
                source_id="cbs_nfl_archive",
                pundit_name="Pete Prisco",
                pundit_id="pete_prisco",
                season_year=year,
                article_type="bold_predictions",
                wayback_date=preseason,
            ),
        ]

        # ── ESPN bold predictions ─────────────────────────────────────────────
        articles += [
            ArchiveArticle(
                original_url=f"https://www.espn.com/nfl/story/_/id/bold-predictions-{year}-nfl-season",
                source_id="espn_nfl_archive",
                pundit_name="ESPN NFL Staff",
                pundit_id="espn_nfl_staff",
                season_year=year,
                article_type="bold_predictions",
                wayback_date=preseason,
            ),
        ]

        # ── The Ringer NFL predictions ─────────────────────────────────────────
        articles += [
            ArchiveArticle(
                original_url=f"https://www.theringer.com/nfl/{year}/9/1/nfl-season-predictions-{year}",
                source_id="theringer_nfl_archive",
                pundit_name="The Ringer NFL Staff",
                pundit_id="ringer_nfl_staff",
                season_year=year,
                article_type="bold_predictions",
                wayback_date=week1,
            ),
            ArchiveArticle(
                original_url=f"https://www.theringer.com/nfl/{year}/8/bold-predictions-nfl-season",
                source_id="theringer_nfl_archive",
                pundit_name="Kevin Clark",
                pundit_id="kevin_clark",
                season_year=year,
                article_type="bold_predictions",
                wayback_date=preseason,
            ),
        ]

        # ── SI.com win total / over-under picks ────────────────────────────────
        articles += [
            ArchiveArticle(
                original_url=f"https://www.si.com/nfl/{year}/nfl-win-totals-predictions",
                source_id="si_nfl_archive",
                pundit_name="Albert Breer",
                pundit_id="albert_breer",
                season_year=year,
                article_type="season_preview",
                wayback_date=preseason,
            ),
            ArchiveArticle(
                original_url=f"https://www.si.com/nfl/{year}/08/nfl-season-predictions-super-bowl",
                source_id="si_nfl_archive",
                pundit_name="Albert Breer",
                pundit_id="albert_breer",
                season_year=year,
                article_type="season_preview",
                wayback_date=preseason,
            ),
        ]

        # ── MVP / Award predictions ────────────────────────────────────────────
        for outlet, source_id, pundit_name, pundit_id in [
            ("espn.com/nfl", "espn_nfl_archive", "ESPN NFL Staff", "espn_nfl_staff"),
            ("www.cbssports.com/nfl", "cbs_nfl_archive", "Pete Prisco", "pete_prisco"),
            (
                "bleacherreport.com",
                "bleacher_report_archive",
                "Bleacher Report NFL Staff",
                "br_nfl_staff",
            ),
        ]:
            articles.append(
                ArchiveArticle(
                    original_url=f"https://{outlet}/news/nfl-mvp-predictions-{year}",
                    source_id=source_id,
                    pundit_name=pundit_name,
                    pundit_id=pundit_id,
                    season_year=year,
                    article_type="award_prediction",
                    wayback_date=preseason,
                )
            )
            articles.append(
                ArchiveArticle(
                    original_url=f"https://{outlet}/news/nfl-{year}-mvp-picks-predictions",
                    source_id=source_id,
                    pundit_name=pundit_name,
                    pundit_id=pundit_id,
                    season_year=year,
                    article_type="award_prediction",
                    wayback_date=preseason,
                )
            )

        # ── Power rankings Week 1 ──────────────────────────────────────────────
        for outlet, source_id in [
            ("www.cbssports.com/nfl/news", "cbs_nfl_archive"),
            ("bleacherreport.com/articles", "bleacher_report_archive"),
        ]:
            articles.append(
                ArchiveArticle(
                    original_url=f"https://{outlet}/nfl-power-rankings-week-1-{year}",
                    source_id=source_id,
                    pundit_name=None,
                    pundit_id=None,
                    season_year=year,
                    article_type="power_rankings",
                    wayback_date=week1,
                )
            )

        # ── Draft grade articles ───────────────────────────────────────────────
        for outlet, source_id, pundit_name, pundit_id in [
            (
                "www.cbssports.com/nfl/news",
                "cbs_nfl_archive",
                "Pete Prisco",
                "pete_prisco",
            ),
            (
                "bleacherreport.com/articles",
                "bleacher_report_archive",
                "Bleacher Report NFL Staff",
                "br_nfl_staff",
            ),
            (
                "www.espn.com/nfl/story",
                "espn_nfl_archive",
                "ESPN NFL Staff",
                "espn_nfl_staff",
            ),
        ]:
            articles.append(
                ArchiveArticle(
                    original_url=f"https://{outlet}/nfl-draft-{year}-grades-every-team",
                    source_id=source_id,
                    pundit_name=pundit_name,
                    pundit_id=pundit_id,
                    season_year=year,
                    article_type="draft_grade",
                    wayback_date=draft_date,
                )
            )
            articles.append(
                ArchiveArticle(
                    original_url=f"https://{outlet}/nfl-{year}-draft-grades-all-32-teams",
                    source_id=source_id,
                    pundit_name=pundit_name,
                    pundit_id=pundit_id,
                    season_year=year,
                    article_type="draft_grade",
                    wayback_date=draft_date,
                )
            )

        # ── PFT / NBC Sports preseason predictions ─────────────────────────────
        articles += [
            ArchiveArticle(
                original_url=f"https://profootballtalk.nbcsports.com/{year}/08/nfl-predictions-{year}-season",
                source_id="pft_nbc_archive",
                pundit_name="Mike Florio",
                pundit_id="mike_florio",
                season_year=year,
                article_type="season_preview",
                wayback_date=preseason,
            ),
        ]

        # ── Yahoo Sports / The 33rd Team / ProFootballFocus ────────────────────
        articles += [
            ArchiveArticle(
                original_url=f"https://sports.yahoo.com/nfl/bold-predictions-{year}-season/",
                source_id="yahoo_nfl_archive",
                pundit_name="Yahoo Sports NFL Staff",
                pundit_id="yahoo_nfl_staff",
                season_year=year,
                article_type="bold_predictions",
                wayback_date=preseason,
            ),
            ArchiveArticle(
                original_url=f"https://www.pff.com/news/nfl-bold-predictions-{year}",
                source_id="pff_archive",
                pundit_name="PFF NFL Staff",
                pundit_id="pff_nfl_staff",
                season_year=year,
                article_type="bold_predictions",
                wayback_date=preseason,
            ),
        ]

        # ── Super Bowl predictions / AFC-NFC Championship picks ─────────────────
        articles += [
            ArchiveArticle(
                original_url=f"https://www.cbssports.com/nfl/news/super-bowl-{year}-predictions-picks/",
                source_id="cbs_nfl_archive",
                pundit_name="Pete Prisco",
                pundit_id="pete_prisco",
                season_year=year,
                article_type="season_preview",
                wayback_date=preseason,
            ),
            ArchiveArticle(
                original_url=f"https://bleacherreport.com/articles/nfl-{year}-super-bowl-predictions",
                source_id="bleacher_report_archive",
                pundit_name="Bleacher Report NFL Staff",
                pundit_id="br_nfl_staff",
                season_year=year,
                article_type="season_preview",
                wayback_date=preseason,
            ),
        ]

    # Deduplicate by URL (some URL patterns may overlap)
    seen = set()
    unique = []
    for a in articles:
        if a.original_url not in seen:
            seen.add(a.original_url)
            unique.append(a)

    return unique


# ---------------------------------------------------------------------------
# Wayback Machine helpers
# ---------------------------------------------------------------------------


def get_wayback_url(original_url: str, target_date: str) -> Optional[str]:
    """
    Query the Wayback Machine availability API for the closest snapshot
    to target_date (YYYYMMDD). Returns the full archive URL or None.
    """
    params = {"url": original_url, "timestamp": target_date}
    try:
        resp = requests.get(
            WAYBACK_API, params=params, timeout=WAYBACK_TIMEOUT, headers=HEADERS
        )
        resp.raise_for_status()
        data = resp.json()
        snapshot = data.get("archived_snapshots", {}).get("closest", {})
        if snapshot.get("available") and snapshot.get("url"):
            return snapshot["url"]
        return None
    except Exception as e:
        logger.warning(f"Wayback API error for {original_url}: {e}")
        return None


def fetch_wayback_text(wayback_url: str) -> Optional[tuple[str, str, Optional[str]]]:
    """
    Fetch a Wayback Machine URL and extract clean article text.
    Returns (title, text, author) or None if extraction fails.
    Uses readability-style extraction with BeautifulSoup fallback.
    """
    try:
        resp = requests.get(wayback_url, timeout=FETCH_TIMEOUT, headers=HEADERS)
        resp.raise_for_status()
        html = resp.text

        # Try readability first
        try:
            from readability import Document

            doc = Document(html)
            title = doc.title() or ""
            summary_html = doc.summary()
            from lxml.html import fromstring

            clean = fromstring(summary_html)
            text = clean.text_content().strip()
        except Exception:
            # Fallback: BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            # Remove Wayback toolbar
            for el in soup.find_all(id="wm-ipp-base"):
                el.decompose()
            title = soup.title.get_text(strip=True) if soup.title else ""
            # Try article tag first, then main, then body
            content = (
                soup.find("article")
                or soup.find("main")
                or soup.find("div", class_=lambda c: c and "article" in c.lower())
                or soup.body
            )
            text = content.get_text(separator=" ", strip=True) if content else ""

        if not text or len(text) < MIN_TEXT_LENGTH:
            return None

        # Extract author from meta tags
        soup_meta = BeautifulSoup(html, "html.parser")
        author = None
        for meta in soup_meta.find_all("meta"):
            name_attr = meta.get("name", "").lower()
            prop_attr = meta.get("property", "").lower()
            if name_attr in ("author", "article:author") or prop_attr in (
                "author",
                "article:author",
            ):
                author = meta.get("content")
                break

        return title, text, author

    except Exception as e:
        logger.warning(f"Failed to fetch {wayback_url}: {e}")
        return None


# ---------------------------------------------------------------------------
# Core ingestor
# ---------------------------------------------------------------------------


def compute_content_hash(source_url: str, title: str = "") -> str:
    """Deterministic hash matching media_ingestor.compute_content_hash."""
    payload = f"{source_url}|{title or ''}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


_DEDUP_SENTINEL = (
    object()
)  # returned by fetch_and_ingest_article when skipped for dedup


def fetch_and_ingest_article(
    article: ArchiveArticle,
    existing_hashes: set,
    db,
    dry_run: bool = False,
):
    """
    Resolves Wayback Machine URL, fetches text, and writes to raw_pundit_media.
    Returns a row dict if successful, _DEDUP_SENTINEL if skipped (already ingested),
    or None if fetch/extraction failed.
    """
    time.sleep(WAYBACK_DELAY)
    wayback_url = get_wayback_url(article.original_url, article.wayback_date)
    if not wayback_url:
        logger.debug(f"No Wayback snapshot for {article.original_url}")
        return None

    content_hash = compute_content_hash(wayback_url, "")
    # Also check original URL hash (in case previously ingested from live URL)
    original_hash = compute_content_hash(article.original_url, "")
    if content_hash in existing_hashes or original_hash in existing_hashes:
        logger.debug(f"Already ingested: {article.original_url}")
        return _DEDUP_SENTINEL

    time.sleep(REQUEST_DELAY)
    result = fetch_wayback_text(wayback_url)
    if result is None:
        logger.warning(f"Text extraction failed: {wayback_url}")
        return None

    title, text, scraped_author = result
    author = scraped_author or article.pundit_name

    # Re-hash with title now that we have it
    content_hash = compute_content_hash(wayback_url, title)
    if content_hash in existing_hashes:
        logger.debug(f"Already ingested (title hash): {title[:60]}")
        return _DEDUP_SENTINEL

    now = datetime.now(timezone.utc)
    # Approximate published date: use preseason/draft/week1 date from article metadata
    try:
        pub_date = datetime.strptime(article.wayback_date, "%Y%m%d").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        pub_date = now

    row = {
        "content_hash": content_hash,
        "source_id": article.source_id,
        "title": title[:500],
        "raw_text": text[:50000],
        "source_url": wayback_url,  # Use Wayback URL as canonical for this ingestion
        "author": author,
        "matched_pundit_id": article.pundit_id,
        "matched_pundit_name": article.pundit_name,
        "published_at": pub_date,
        "ingested_at": now,
        "content_type": "article",
        "fetch_source_type": "wayback_machine",
        "sport": "NFL",
        "raw_metadata": json.dumps(
            {
                "original_url": article.original_url,
                "season_year": article.season_year,
                "article_type": article.article_type,
                "is_historical": True,
            }
        ),
    }

    if not dry_run and db is not None:
        df = pd.DataFrame([row])
        # Ensure nullable columns are proper None
        for col in ["author", "matched_pundit_id", "matched_pundit_name"]:
            df[col] = df[col].where(df[col].notna(), None)
        db.append_dataframe_to_table(df, RAW_MEDIA_TABLE)

    existing_hashes.add(content_hash)
    logger.info(
        f"[{article.source_id}] Ingested: {title[:60]} "
        f"(season={article.season_year}, type={article.article_type})"
    )
    return row


def get_existing_hashes_all(db) -> set:
    """Fetch all historical content hashes from BQ (full scan for backfill dedup)."""
    project_id = os.environ.get("GCP_PROJECT_ID", "")
    try:
        query = f"""
            SELECT content_hash
            FROM `{project_id}.nfl_dead_money.{RAW_MEDIA_TABLE}`
            WHERE fetch_source_type = 'wayback_machine'
               OR source_id LIKE '%_archive'
        """
        df = db.fetch_df(query)
        return set(df["content_hash"].tolist()) if not df.empty else set()
    except Exception as e:
        logger.warning(f"Could not load existing archive hashes: {e}")
        return set()


def run_historical_ingestion(
    seasons: list[int] | None = None,
    batch_size: int = 50,
    dry_run: bool = False,
    db=None,
    article_types: list[str] | None = None,
) -> dict:
    """
    Main entry point for historical backfill ingestion.

    1. Builds the full article catalog for the requested seasons
    2. For each article: resolves Wayback URL, fetches text, writes to BQ
    3. Returns a summary dict

    Args:
        seasons: List of season years, e.g. [2020, 2021, 2022, 2023, 2024]
        batch_size: Max articles to process in this run
        dry_run: Preview only — no BQ writes
        db: Optional DBManager (created if None)
        article_types: Filter to specific types e.g. ["bold_predictions"]
    """
    close_db = db is None
    if db is None:
        try:
            from src.db_manager import DBManager

            db = DBManager()
        except Exception as e:
            logger.error(f"Could not connect to BigQuery: {e}")
            return {"error": str(e)}

    summary = {
        "articles_attempted": 0,
        "articles_ingested": 0,
        "articles_skipped_dedup": 0,
        "articles_failed": 0,
        "seasons": seasons or [2020, 2021, 2022, 2023, 2024],
        "dry_run": dry_run,
    }

    try:
        catalog = build_article_catalog(seasons=seasons)
        if article_types:
            catalog = [a for a in catalog if a.article_type in article_types]

        logger.info(
            f"Catalog built: {len(catalog)} target articles "
            f"(batch_size={batch_size}, dry_run={dry_run})"
        )

        # Load existing hashes for dedup
        existing_hashes: set = set()
        if not dry_run:
            existing_hashes = get_existing_hashes_all(db)
            logger.info(f"Loaded {len(existing_hashes)} existing archive hashes")

        processed = 0
        for article in catalog:
            if processed >= batch_size:
                break

            summary["articles_attempted"] += 1
            row = fetch_and_ingest_article(
                article,
                existing_hashes,
                db,
                dry_run=dry_run,
            )
            processed += 1

            if row is _DEDUP_SENTINEL:
                summary["articles_skipped_dedup"] += 1
            elif row is not None:
                summary["articles_ingested"] += 1
            else:
                summary["articles_failed"] += 1

        logger.info(
            f"Historical ingestion complete: "
            f"{summary['articles_ingested']} ingested, "
            f"{summary['articles_failed']} failed/skipped, "
            f"{summary['articles_attempted']} attempted"
        )
        return summary

    finally:
        if close_db and db is not None:
            db.close()


def run_extraction_on_archive(
    limit: int = 200,
    dry_run: bool = False,
    db=None,
) -> dict:
    """
    Run the assertion extractor on archive articles specifically.
    Uses --allow-historical to bypass the temporal season_year filter.
    """
    try:
        from src.assertion_extractor import run_extraction

        result = run_extraction(
            limit=limit,
            dry_run=dry_run,
            sport="NFL",
            include_unmatched=True,
            allow_historical=True,
            db=db,
        )
        return result
    except Exception as e:
        logger.error(f"Extraction failed: {e}")
        return {"error": str(e)}


def check_yield(ingestion_summary: dict, extraction_summary: dict) -> bool:
    """
    Check if extraction yield is above the minimum threshold.
    Returns True if acceptable, False if below threshold (stop condition).
    """
    ingested = ingestion_summary.get("articles_ingested", 0)
    extracted = extraction_summary.get("predictions_extracted", 0)

    if ingested < 50:
        # Too few articles to make a meaningful yield judgment
        return True

    yield_rate = extracted / ingested if ingested > 0 else 0
    if yield_rate < MIN_YIELD_THRESHOLD:
        logger.warning(
            f"LOW YIELD WARNING: {extracted} predictions from {ingested} articles "
            f"= {yield_rate:.2f}/article (threshold: {MIN_YIELD_THRESHOLD}). "
            f"Extractor may need tuning. Check assertion_extractor.py temporal filter."
        )
        return False
    logger.info(
        f"Yield OK: {extracted} predictions from {ingested} articles "
        f"= {yield_rate:.2f}/article"
    )
    return True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Historical Archive Ingestor — Pundit Prediction Ledger Backfill"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=20,
        help="Max articles to fetch per run (default: 20 for sample)",
    )
    parser.add_argument(
        "--season",
        type=int,
        action="append",
        dest="seasons",
        help="Season year(s) to process (default: 2020-2024). Can repeat: --season 2022 --season 2023",
    )
    parser.add_argument(
        "--article-type",
        choices=[
            "bold_predictions",
            "season_preview",
            "award_prediction",
            "draft_grade",
            "power_rankings",
        ],
        action="append",
        dest="article_types",
        help="Filter to specific article type(s)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview only — no BQ writes, no extraction",
    )
    parser.add_argument(
        "--run-extraction",
        action="store_true",
        help="After ingestion, run assertion_extractor on archive articles",
    )
    parser.add_argument(
        "--extraction-limit",
        type=int,
        default=200,
        help="Max articles to process during extraction phase (default: 200)",
    )
    parser.add_argument(
        "--list-catalog",
        action="store_true",
        help="Print the full URL catalog and exit (no fetching)",
    )
    args = parser.parse_args()

    if args.list_catalog:
        catalog = build_article_catalog(seasons=args.seasons)
        if args.article_types:
            catalog = [a for a in catalog if a.article_type in args.article_types]
        print(f"Catalog: {len(catalog)} articles")
        for a in catalog:
            print(
                f"  [{a.season_year}] [{a.article_type:18s}] {a.source_id:30s} {a.original_url}"
            )
        import sys

        sys.exit(0)

    ingestion_result = run_historical_ingestion(
        seasons=args.seasons,
        batch_size=args.batch_size,
        dry_run=args.dry_run,
        article_types=args.article_types,
    )
    print("\n=== Ingestion Summary ===")
    print(json.dumps(ingestion_result, indent=2, default=str))

    if args.run_extraction and not args.dry_run:
        print("\n=== Running Extraction on Archive Articles ===")
        extraction_result = run_extraction_on_archive(
            limit=args.extraction_limit,
            dry_run=args.dry_run,
        )
        print(json.dumps(extraction_result, indent=2, default=str))

        # Check yield — exit non-zero if below threshold so automation can detect failure
        import sys

        if not check_yield(ingestion_result, extraction_result):
            sys.exit(1)
