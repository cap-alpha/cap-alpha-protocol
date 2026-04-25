"""
Search-based article crawler + URL ingestor.

Searches the web for NFL draft prediction articles, discovers URLs automatically,
fetches and ingests them, then runs extraction.

Usage:
    python -m src.url_ingestor --search [--dry-run] [--max-results 100]
    python -m src.url_ingestor --config config/draft_seed_urls.yaml [--dry-run]
    python -m src.url_ingestor --urls "https://..." --source espn_nfl --pundit "Mel Kiper"
"""

import argparse
import hashlib
import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

import pandas as pd
import requests
import yaml
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
from readability import Document

from src.db_manager import DBManager
from src.media_ingestor import MediaItem, compute_content_hash

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def fetch_article_text(url: str) -> dict:
    """Fetch and extract article text from a URL."""
    headers = {"User-Agent": "PunditLedger/1.0"}
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()

    doc = Document(resp.text)
    title = doc.title()
    html = doc.summary()
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator=" ", strip=True)

    # Try to extract author from meta tags
    full_soup = BeautifulSoup(resp.text, "html.parser")
    author = None
    for meta in full_soup.find_all("meta"):
        name = meta.get("name", "").lower()
        prop = meta.get("property", "").lower()
        if name in ("author", "article:author") or prop in (
            "author",
            "article:author",
        ):
            author = meta.get("content")
            break

    # Try publish date
    pub_date = None
    for meta in full_soup.find_all("meta"):
        prop = meta.get("property", "").lower()
        name = meta.get("name", "").lower()
        if prop in ("article:published_time", "og:published_time") or name in (
            "publish-date",
            "date",
        ):
            try:
                pub_date = datetime.fromisoformat(
                    meta.get("content", "").replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                pass
            break

    return {
        "title": title,
        "text": text,
        "author": author,
        "published_at": pub_date,
        "url": url,
    }


def discover_articles(
    config_path: str = "config/draft_seed_urls.yaml",
    max_results_per_query: int = 30,
) -> list[dict]:
    """
    Search the web for NFL draft prediction articles and return URL configs.
    Uses DuckDuckGo search (no API key needed).
    """
    with open(config_path) as f:
        config = yaml.safe_load(f)

    queries = config.get("search_queries", [])
    source_mapping = config.get("source_mapping", {})
    skip_domains = set(config.get("skip_domains", []))

    seen_urls = set()
    url_configs = []

    for query in queries:
        logger.info(f"Searching: {query}")
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=max_results_per_query))
        except Exception as e:
            logger.warning(f"Search failed for '{query}': {e}")
            continue

        for r in results:
            url = r.get("href", r.get("link", ""))
            if not url or url in seen_urls:
                continue

            # Check domain
            domain = urlparse(url).netloc.lower().replace("www.", "")
            if any(skip in domain for skip in skip_domains):
                continue

            # Map to source
            source_id = "web_search"
            for pattern, mapping in source_mapping.items():
                if pattern in domain:
                    source_id = mapping.get("source_id", "web_search")
                    break

            # Filter: title must mention draft/mock/pick/prediction
            title = r.get("title", "").lower()
            if not any(
                kw in title
                for kw in ["draft", "mock", "pick", "prediction", "prospect"]
            ):
                continue

            seen_urls.add(url)
            url_configs.append(
                {
                    "url": url,
                    "source_id": source_id,
                    "title": r.get("title", ""),
                }
            )

        # Rate limit between queries
        time.sleep(1)

    logger.info(
        f"Discovered {len(url_configs)} unique article URLs from {len(queries)} queries"
    )
    return url_configs


def ingest_from_urls(
    url_configs: list[dict],
    db: DBManager,
    dry_run: bool = False,
) -> dict:
    """
    Ingest articles from a list of URL configs.

    Each config: {
        "url": "https://...",
        "source_id": "espn_nfl",
        "pundit_name": "Mel Kiper",  # optional, overrides auto-detection
        "pundit_id": "mel_kiper",    # optional
    }
    """
    summary = {"fetched": 0, "new": 0, "errors": 0, "skipped": 0}

    # Get existing hashes to dedup
    all_hashes = set()
    try:
        df = db.fetch_df(
            "SELECT content_hash FROM raw_pundit_media "
            "WHERE ingested_at > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY)"
        )
        if not df.empty:
            all_hashes = set(df["content_hash"].tolist())
    except Exception:
        pass

    items = []
    now = datetime.now(timezone.utc)

    for config in url_configs:
        url = config["url"]
        source_id = config.get("source_id", "manual_seed")
        pundit_name = config.get("pundit_name")
        pundit_id = config.get("pundit_id")

        try:
            article = fetch_article_text(url)
            summary["fetched"] += 1
        except Exception as e:
            logger.warning(f"Failed to fetch {url}: {e}")
            summary["errors"] += 1
            continue

        content_hash = compute_content_hash(url, article["title"] or "")
        if content_hash in all_hashes:
            logger.info(f"  DEDUP: {url[:60]}")
            summary["skipped"] += 1
            continue

        # Use config pundit or fall back to article author
        author = pundit_name or article["author"]
        p_name = pundit_name
        p_id = pundit_id

        text = article["text"] or ""
        if len(text) < 100:
            logger.warning(f"  SHORT: {url[:60]} ({len(text)} chars)")
            summary["skipped"] += 1
            continue

        items.append(
            MediaItem(
                content_hash=content_hash,
                source_id=source_id,
                title=article["title"] or "",
                raw_text=text[:50000],
                source_url=url,
                author=author,
                matched_pundit_id=p_id,
                matched_pundit_name=p_name,
                published_at=article["published_at"],
                ingested_at=now,
                content_type="article",
                fetch_source_type="url_seed",
                sport="NFL",
            )
        )
        all_hashes.add(content_hash)
        logger.info(f"  NEW: [{source_id}] {article['title'][:50]} by {author}")

    if items and not dry_run:
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
        ]
        for col in nullable_cols:
            if col in df.columns:
                df[col] = df[col].where(df[col].notna(), None)
        # Ensure published_at is proper datetime
        if "published_at" in df.columns:
            df["published_at"] = pd.to_datetime(
                df["published_at"], errors="coerce", utc=True
            )
        db.append_dataframe_to_table(df, "raw_pundit_media")
        logger.info(f"Wrote {len(items)} articles to raw_pundit_media")
        summary["new"] = len(items)
    elif items and dry_run:
        summary["new"] = len(items)
        logger.info(f"DRY RUN: would write {len(items)} articles")

    logger.info(
        f"URL ingest complete: {summary['fetched']} fetched, "
        f"{summary['new']} new, {summary['skipped']} deduped, "
        f"{summary['errors']} errors"
    )
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Search-based article crawler + ingestor"
    )
    parser.add_argument(
        "--search", action="store_true", help="Search web for articles automatically"
    )
    parser.add_argument(
        "--config", default="config/draft_seed_urls.yaml", help="Search config YAML"
    )
    parser.add_argument("--urls", nargs="+", help="Direct URLs to ingest")
    parser.add_argument(
        "--source", default="manual_seed", help="Source ID for direct URLs"
    )
    parser.add_argument("--pundit", help="Pundit name override for direct URLs")
    parser.add_argument("--pundit-id", help="Pundit ID override for direct URLs")
    parser.add_argument(
        "--max-results", type=int, default=30, help="Max results per search query"
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    db = DBManager()

    if args.search:
        logger.info("=== SEARCH MODE: discovering articles from the web ===")
        url_configs = discover_articles(
            config_path=args.config,
            max_results_per_query=args.max_results,
        )
    elif args.urls:
        url_configs = [
            {
                "url": u,
                "source_id": args.source,
                "pundit_name": args.pundit,
                "pundit_id": args.pundit_id,
            }
            for u in args.urls
        ]
    else:
        parser.error("Must provide --search or --urls")

    result = ingest_from_urls(url_configs, db, dry_run=args.dry_run)
    print(json.dumps(result, indent=2))
