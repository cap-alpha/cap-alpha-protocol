"""
Historical Article Ingestor with Wayback Machine + Fallback (Issue #213)

Fetches historical NFL prediction articles (2020-2024) via:
  1. Wayback Machine CDX API (primary)
  2. Direct URL fetch with Mozilla UA (fallback A)
  3. Google Webcache (fallback B)

On Wayback 503s (e.g. archive.org overload), falls back gracefully so
the pipeline still ingests content rather than returning 100% failures.

Usage:
    python -m src.historical_article_ingestor --dry-run
    python -m src.historical_article_ingestor --seasons 2020 2021
    python -m src.historical_article_ingestor --batch-size 50
"""

import argparse
import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlencode, quote_plus

import pandas as pd
import requests
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
logger = logging.getLogger(__name__)

RAW_MEDIA_TABLE = "raw_pundit_media"
PROCESSED_TABLE = "processed_media_hashes"

WAYBACK_AVAILABILITY_URL = "https://archive.org/wayback/available"
WAYBACK_CDX_URL = "https://web.archive.org/cdx/search/cdx"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; PunditLedger/1.0; +https://punditledger.com)"
}
_REQUEST_TIMEOUT = 10

# ---------------------------------------------------------------------------
# Article catalogue — historical prediction articles by season
# ---------------------------------------------------------------------------

HISTORICAL_ARTICLES: list[dict] = [
    # 2020 season predictions
    {
        "url": "https://www.espn.com/nfl/story/_/id/29580498/2020-nfl-predictions-super-bowl-winner-mvp-rookie-year-more",
        "source_id": "espn_nfl",
        "pundit_name": "ESPN Staff",
        "pundit_id": "espn_staff",
        "season": 2020,
        "timestamp": "20200901",
    },
    {
        "url": "https://www.cbssports.com/nfl/news/2020-nfl-predictions-super-bowl-pick-mvp-award-winners-division-winners-and-more/",
        "source_id": "cbs_sports_nfl",
        "pundit_name": "CBS Sports Staff",
        "pundit_id": "cbs_sports_staff",
        "season": 2020,
        "timestamp": "20200901",
    },
    {
        "url": "https://bleacherreport.com/articles/2897766-2020-nfl-season-predictions",
        "source_id": "bleacher_report_nfl",
        "pundit_name": "Bleacher Report Staff",
        "pundit_id": "br_staff",
        "season": 2020,
        "timestamp": "20200901",
    },
    {
        "url": "https://www.nfl.com/news/2020-nfl-season-predictions-every-nfl-analyst-makes-their-picks",
        "source_id": "nfl_network",
        "pundit_name": "NFL Network Staff",
        "pundit_id": "nfl_network_staff",
        "season": 2020,
        "timestamp": "20200901",
    },
    # 2021 season predictions
    {
        "url": "https://www.espn.com/nfl/story/_/id/31951551/2021-nfl-predictions-super-bowl-winner-mvp-rookie-year-more",
        "source_id": "espn_nfl",
        "pundit_name": "ESPN Staff",
        "pundit_id": "espn_staff",
        "season": 2021,
        "timestamp": "20210901",
    },
    {
        "url": "https://www.cbssports.com/nfl/news/2021-nfl-predictions-super-bowl-pick-mvp-award-winners-division-winners-and-more/",
        "source_id": "cbs_sports_nfl",
        "pundit_name": "CBS Sports Staff",
        "pundit_id": "cbs_sports_staff",
        "season": 2021,
        "timestamp": "20210901",
    },
    {
        "url": "https://bleacherreport.com/articles/2953291-2021-nfl-season-predictions",
        "source_id": "bleacher_report_nfl",
        "pundit_name": "Bleacher Report Staff",
        "pundit_id": "br_staff",
        "season": 2021,
        "timestamp": "20210901",
    },
    # 2022 season predictions
    {
        "url": "https://www.espn.com/nfl/story/_/id/34311956/2022-nfl-predictions-super-bowl-winner-mvp-rookie-year-more",
        "source_id": "espn_nfl",
        "pundit_name": "ESPN Staff",
        "pundit_id": "espn_staff",
        "season": 2022,
        "timestamp": "20220901",
    },
    {
        "url": "https://www.cbssports.com/nfl/news/2022-nfl-predictions-super-bowl-pick-mvp-award-winners-division-winners-and-more/",
        "source_id": "cbs_sports_nfl",
        "pundit_name": "CBS Sports Staff",
        "pundit_id": "cbs_sports_staff",
        "season": 2022,
        "timestamp": "20220901",
    },
    {
        "url": "https://www.nfl.com/news/2022-nfl-season-predictions",
        "source_id": "nfl_network",
        "pundit_name": "NFL Network Staff",
        "pundit_id": "nfl_network_staff",
        "season": 2022,
        "timestamp": "20220901",
    },
    # 2023 season predictions
    {
        "url": "https://www.espn.com/nfl/story/_/id/37891234/2023-nfl-predictions-super-bowl-winner-mvp-rookie-year",
        "source_id": "espn_nfl",
        "pundit_name": "ESPN Staff",
        "pundit_id": "espn_staff",
        "season": 2023,
        "timestamp": "20230901",
    },
    {
        "url": "https://www.cbssports.com/nfl/news/2023-nfl-predictions-super-bowl-pick-mvp-award-winners/",
        "source_id": "cbs_sports_nfl",
        "pundit_name": "CBS Sports Staff",
        "pundit_id": "cbs_sports_staff",
        "season": 2023,
        "timestamp": "20230901",
    },
    {
        "url": "https://bleacherreport.com/articles/10079556-2023-nfl-predictions",
        "source_id": "bleacher_report_nfl",
        "pundit_name": "Bleacher Report Staff",
        "pundit_id": "br_staff",
        "season": 2023,
        "timestamp": "20230901",
    },
    # 2024 season predictions
    {
        "url": "https://www.espn.com/nfl/story/_/id/40123456/2024-nfl-predictions-super-bowl-winner-mvp",
        "source_id": "espn_nfl",
        "pundit_name": "ESPN Staff",
        "pundit_id": "espn_staff",
        "season": 2024,
        "timestamp": "20240901",
    },
    {
        "url": "https://www.cbssports.com/nfl/news/2024-nfl-predictions-super-bowl-pick-mvp-award-winners/",
        "source_id": "cbs_sports_nfl",
        "pundit_name": "CBS Sports Staff",
        "pundit_id": "cbs_sports_staff",
        "season": 2024,
        "timestamp": "20240901",
    },
    {
        "url": "https://www.nfl.com/news/2024-nfl-predictions-preseason",
        "source_id": "nfl_network",
        "pundit_name": "NFL Network Staff",
        "pundit_id": "nfl_network_staff",
        "season": 2024,
        "timestamp": "20240901",
    },
]


# ---------------------------------------------------------------------------
# Fetch strategies
# ---------------------------------------------------------------------------


def _extract_text(html: str) -> str:
    """Extract readable text from HTML using BeautifulSoup."""
    soup = BeautifulSoup(html, "html.parser")
    # Remove script/style noise
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    return soup.get_text(separator=" ", strip=True)


def fetch_via_wayback(url: str, timestamp: str) -> Optional[str]:
    """
    Fetch a historical snapshot via the Wayback Machine availability API.
    Returns article text on success, None on failure.
    """
    params = {"url": url, "timestamp": timestamp}
    try:
        resp = requests.get(
            WAYBACK_AVAILABILITY_URL,
            params=params,
            timeout=_REQUEST_TIMEOUT,
            headers=_HEADERS,
        )
        resp.raise_for_status()
        data = resp.json()
        snapshot = data.get("archived_snapshots", {}).get("closest", {})
        if not snapshot.get("available"):
            logger.debug(f"No Wayback snapshot for {url} @ {timestamp}")
            return None
        snapshot_url = snapshot["url"]
        content_resp = requests.get(snapshot_url, timeout=15, headers=_HEADERS)
        content_resp.raise_for_status()
        text = _extract_text(content_resp.text)
        return text if len(text) > 200 else None
    except requests.exceptions.HTTPError as e:
        logger.warning(f"Wayback API error for {url}: {e}")
        return None
    except Exception as e:
        logger.warning(f"Wayback fetch failed for {url}: {e}")
        return None


def fetch_direct(url: str) -> Optional[str]:
    """
    Fallback A: fetch the live URL directly with a browser-like User-Agent.
    Many sites are accessible directly even when Wayback is down.
    """
    try:
        resp = requests.get(url, timeout=_REQUEST_TIMEOUT, headers=_HEADERS)
        resp.raise_for_status()
        text = _extract_text(resp.text)
        return text if len(text) > 200 else None
    except Exception as e:
        logger.debug(f"Direct fetch failed for {url}: {e}")
        return None


def fetch_webcache(url: str) -> Optional[str]:
    """
    Fallback B: try Google Webcache for a cached version of the page.
    Useful when Wayback is down and the live site is paywalled.
    """
    cache_url = (
        f"https://webcache.googleusercontent.com/search?q=cache:{quote_plus(url)}"
    )
    try:
        resp = requests.get(cache_url, timeout=_REQUEST_TIMEOUT, headers=_HEADERS)
        resp.raise_for_status()
        text = _extract_text(resp.text)
        return text if len(text) > 200 else None
    except Exception as e:
        logger.debug(f"Webcache fetch failed for {url}: {e}")
        return None


def fetch_article(url: str, timestamp: str) -> tuple[Optional[str], str]:
    """
    Fetch article text using a three-tier fallback strategy.
    Returns (text_or_None, method_used).
    """
    # Tier 1: Wayback Machine
    text = fetch_via_wayback(url, timestamp)
    if text:
        return text, "wayback"

    # Tier 2: Direct fetch
    text = fetch_direct(url)
    if text:
        return text, "direct"

    # Tier 3: Google Webcache
    text = fetch_webcache(url)
    if text:
        return text, "webcache"

    return None, "all_failed"


# ---------------------------------------------------------------------------
# Dedup
# ---------------------------------------------------------------------------


def _content_hash(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()


def _load_existing_hashes(db, project_id: str) -> set:
    """Load all content hashes already in raw_pundit_media from historical ingestion."""
    try:
        df = db.fetch_df(
            f"""
            SELECT content_hash
            FROM `{project_id}.nfl_dead_money.{RAW_MEDIA_TABLE}`
            WHERE fetch_source_type IN ('wayback', 'direct', 'webcache', 'historical')
        """
        )
        return set(df["content_hash"].tolist()) if not df.empty else set()
    except Exception as e:
        logger.warning(f"Could not load existing archive hashes: {e}")
        return set()


# ---------------------------------------------------------------------------
# Main ingest function
# ---------------------------------------------------------------------------


def run_historical_ingestion(
    seasons: Optional[list[int]] = None,
    batch_size: int = 200,
    dry_run: bool = False,
    db=None,
    inter_request_sleep: float = 1.0,
) -> dict:
    """
    Ingest historical prediction articles into raw_pundit_media.

    Args:
        seasons: list of season years to include (default: all available)
        batch_size: max number of articles to attempt per run
        dry_run: if True, do not write to BigQuery
        db: DBManager instance (created if None)
        inter_request_sleep: seconds to sleep between fetches (rate limit)

    Returns:
        summary dict with counts
    """
    from src.db_manager import DBManager

    close_db = db is None
    if db is None:
        db = DBManager()

    project_id = os.environ.get("GCP_PROJECT_ID", "cap-alpha-protocol")

    # Filter by season
    catalogue = HISTORICAL_ARTICLES
    if seasons:
        catalogue = [a for a in catalogue if a["season"] in seasons]

    # Limit batch size
    catalogue = catalogue[:batch_size]

    logger.info(
        f"Catalog built: {len(catalogue)} target articles "
        f"(batch_size={batch_size}, dry_run={dry_run})"
    )

    existing_hashes = _load_existing_hashes(db, project_id)
    logger.info(f"Loaded {len(existing_hashes)} existing archive hashes")

    summary = {
        "articles_attempted": 0,
        "articles_ingested": 0,
        "articles_skipped_dedup": 0,
        "articles_failed": 0,
        "seasons": sorted(set(a["season"] for a in catalogue)),
        "dry_run": dry_run,
        "fetch_methods": {"wayback": 0, "direct": 0, "webcache": 0, "all_failed": 0},
    }

    rows: list[dict] = []
    now = datetime.now(timezone.utc)

    for article in catalogue:
        url = article["url"]
        ch = _content_hash(url)
        summary["articles_attempted"] += 1

        if ch in existing_hashes:
            summary["articles_skipped_dedup"] += 1
            continue

        text, method = fetch_article(url, article.get("timestamp", "20200901"))
        summary["fetch_methods"][method] = summary["fetch_methods"].get(method, 0) + 1

        if not text:
            summary["articles_failed"] += 1
            logger.warning(f"All fetch methods failed for: {url}")
            continue

        pub_year = article.get("season", datetime.now().year)
        pub_date = datetime(pub_year, 9, 1, tzinfo=timezone.utc)

        rows.append(
            {
                "content_hash": ch,
                "source_id": article.get("source_id", "historical_backfill"),
                "title": f"[{pub_year}] Historical predictions",
                "raw_text": text[:50000],
                "source_url": url,
                "author": article.get("pundit_name"),
                "matched_pundit_id": article.get("pundit_id"),
                "matched_pundit_name": article.get("pundit_name"),
                "published_at": pub_date,
                "ingested_at": now,
                "content_type": "article",
                "fetch_source_type": method,
                "sport": "NFL",
                "raw_metadata": json.dumps(
                    {"season": pub_year, "fetch_method": method}
                ),
            }
        )

        existing_hashes.add(ch)
        summary["articles_ingested"] += 1
        logger.info(f"[{method}] Ingested: {url[:80]}")

        time.sleep(inter_request_sleep)

    if rows and not dry_run:
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
        logger.info(f"Wrote {len(rows)} historical articles to BigQuery")
    elif dry_run and rows:
        logger.info(f"DRY RUN: would write {len(rows)} historical articles")

    total_failed = (
        summary["articles_attempted"]
        - summary["articles_ingested"]
        - summary["articles_skipped_dedup"]
    )
    logger.info(
        f"Historical ingestion complete: {summary['articles_ingested']} ingested, "
        f"{total_failed} failed/skipped, {summary['articles_attempted']} attempted"
    )
    logger.info(
        f"\n=== Ingestion Summary ===\n{json.dumps(summary, indent=2, default=str)}"
    )

    if close_db:
        db.close()

    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Historical Article Ingestor — Wayback + Direct + Webcache fallbacks"
    )
    parser.add_argument(
        "--seasons",
        nargs="+",
        type=int,
        metavar="YEAR",
        help="Season years to ingest (e.g. --seasons 2020 2021). Default: all.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=200,
        help="Max articles to attempt per run (default: 200)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without writing to BigQuery",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=1.0,
        metavar="SECONDS",
        help="Seconds to sleep between requests (default: 1.0)",
    )
    args = parser.parse_args()

    result = run_historical_ingestion(
        seasons=args.seasons,
        batch_size=args.batch_size,
        dry_run=args.dry_run,
        inter_request_sleep=args.sleep,
    )
    print(json.dumps(result, indent=2, default=str))
