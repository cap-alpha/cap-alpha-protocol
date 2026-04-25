"""
NLP Assertion Extraction Pipeline (Issue #79, #178)

Converts unstructured pundit media text (from raw_pundit_media) into structured
prediction vectors and feeds them into the cryptographic ledger.

Pipeline flow:
  raw_pundit_media (bronze) → LLM extraction → PunditPrediction → prediction_ledger (gold)

Uses a pluggable LLM provider (Gemini, Claude, OpenAI, or Ollama local).
Provider is selected via pipeline/config/llm_config.yaml.

Usage (inside Docker):
    python -m src.assertion_extractor                  # process all unprocessed
    python -m src.assertion_extractor --limit 50       # process N items
    python -m src.assertion_extractor --dry-run        # preview without writing
    python -m src.assertion_extractor --provider ollama # override provider
"""

import argparse
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Optional

import pandas as pd
from tqdm import tqdm
from google.api_core.exceptions import NotFound
from src.cryptographic_ledger import PunditPrediction, ingest_batch
from src.db_manager import DBManager
from src.llm_provider import (
    LLMProvider,
    get_provider,
    get_provider_with_fallback,
    load_llm_config,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
logger = logging.getLogger(__name__)

RAW_MEDIA_TABLE = "raw_pundit_media"
PROCESSED_TABLE = "processed_media_hashes"

# Valid claim categories (must match prediction_ledger schema)
VALID_CATEGORIES = {
    "player_performance",
    "game_outcome",
    "trade",
    "draft_pick",
    "injury",
    "contract",
}

EXTRACTION_PROMPT = """You are a {sport} prediction extraction system. Extract testable predictions from the content below.

PUBLISHED: {published_date}

Rules — what TO extract:
- Concrete, falsifiable claims about FUTURE outcomes with a clear stance
- Must have: a SUBJECT (player/team) + a TESTABLE OUTCOME + a TIMEFRAME (season, game, date)
- Examples of good extractions:
  "Patrick Mahomes will win MVP in 2025" → stance: bullish
  "The Browns will miss the playoffs in 2025" → stance: bearish
  "Travis Kelce will retire after the 2025 season" → stance: neutral

Stance rules:
- bullish: prediction is positive/optimistic about the subject (win award, make playoffs, exceed stats target)
- bearish: prediction is negative/pessimistic about the subject (miss playoffs, underperform, get cut, lose)
- neutral: no clear directional bias (retirement, trade, purely factual future event)

Rules — what NOT to extract:
- HEDGED statements: "wouldn't surprise me if", "I could see", "most likely", "might", "probably"
- VAGUE qualitative claims: "will be good", "will make plays", "will be a factor", "well worth it"
- TAUTOLOGIES: "the deal will eventually be released", "they will bring in players"
- SCHEME/STYLE descriptions: "will run a 4-3 defense", "will use more zone coverage"
- HISTORICAL FACTS or ALREADY-RESOLVED events: if the outcome is already known at the article's publish date, do NOT extract it
- CONSENSUS RESTATING: "the Chiefs will be competitive" (everyone knows this)
- OPINIONS without testable outcomes: "he's the best QB in the league"
- ADMINISTRATIVE details: payment structures, meeting schedules, procedural items
- Claims about events from PAST SEASONS that are already concluded

If the article contains no concrete, falsifiable predictions with clear stances, return an empty list.

SOURCE: {source_name}
AUTHOR: {author}
TITLE: {title}
TEXT:
{text}"""

BATCH_EXTRACTION_PROMPT = """You are a {sport} prediction extraction system. Extract testable predictions from the MULTIPLE articles below.

Apply the same rules as single-article extraction. Each prediction MUST include an "article_index" field (0-based integer) identifying which article it came from.

Rules — what TO extract:
- Concrete, falsifiable claims about FUTURE outcomes with a clear stance
- Must have: a SUBJECT (player, team, or league-level) + a TESTABLE OUTCOME + a TIMEFRAME
- MOCK DRAFT PICKS ARE PREDICTIONS: "Pick #3: Arvell Reese to Arizona Cardinals" → draft_pick

Rules — what NOT to extract:
- HEDGED statements: "wouldn't surprise me if", "I could see", "might", "probably"
- VAGUE claims: "will be good", "will make plays"
- HISTORICAL FACTS or ALREADY-RESOLVED events
- OPINIONS without testable outcomes
- Claims from PAST SEASONS that are already concluded

{articles}

Return a single JSON array. Each object must have:
- "article_index": integer (0-based, which article this came from) — REQUIRED
- "extracted_claim": concise, testable statement — REQUIRED
- "claim_category": one of: player_performance, game_outcome, trade, draft_pick, injury, contract — REQUIRED
- "stance": "bullish" / "bearish" / "neutral" — REQUIRED
- "season_year": integer or null
- "target_player": full player name or null
- "target_team": team abbreviation or null
- "confidence_note": how explicit/confident — REQUIRED

If no articles contain predictions, return an empty array: []"""


@dataclass
class ExtractionResult:
    content_hash: str
    predictions: list[dict]
    error: Optional[str] = None
    raw_response: Optional[str] = None


def _deduplicate_claims(predictions: list[dict], threshold: float = 0.75) -> list[dict]:
    """
    Remove near-duplicate claims from a single article's extraction.
    Uses SequenceMatcher to detect semantic overlap. Keeps the longest
    (most specific) claim from each cluster.
    """
    if len(predictions) <= 1:
        return predictions

    kept = []
    for pred in predictions:
        claim = pred.get("extracted_claim", "").lower()
        is_dup = False
        for i, existing in enumerate(kept):
            existing_claim = existing.get("extracted_claim", "").lower()
            ratio = SequenceMatcher(None, claim, existing_claim).ratio()
            if ratio >= threshold:
                if len(claim) > len(existing_claim):
                    kept[i] = pred
                is_dup = True
                break
        if not is_dup:
            kept.append(pred)

    removed = len(predictions) - len(kept)
    if removed > 0:
        logger.info(f"Dedup: removed {removed} near-duplicate claims")
    return kept


def extract_assertions(
    content_hash: str,
    text: str,
    title: str = "",
    author: str = "",
    source_name: str = "",
    sport: str = "NFL",
    published_date: str = "",
    provider: Optional[LLMProvider] = None,
    # Legacy parameter — ignored if provider is set
    client=None,
) -> ExtractionResult:
    """
    Sends media text to the configured LLM for structured prediction extraction.
    Returns an ExtractionResult with parsed predictions.
    """
    if provider is None:
        # Legacy fallback: create a Gemini provider for backward compatibility
        from src.llm_provider import GeminiProvider

        provider = GeminiProvider()

    prompt = EXTRACTION_PROMPT.format(
        sport=sport,
        published_date=published_date or "Unknown",
        source_name=source_name or "Unknown",
        author=author or "Unknown",
        title=title or "Untitled",
        text=text[:4000],
    )

    try:
        predictions = provider.extract_predictions(prompt)
        # Filter empty claims, then deduplicate near-identical ones
        valid = [p for p in predictions if p.get("extracted_claim", "").strip()]
        # Hard temporal filter: reject predictions about past seasons/drafts
        current_year = datetime.now().year
        filtered = []
        for p in valid:
            sy = p.get("season_year")
            if (
                sy is not None
                and isinstance(sy, (int, float))
                and int(sy) < current_year
            ):
                logger.info(
                    f"Temporal filter: rejected stale claim (season_year={sy}): "
                    f"{p.get('extracted_claim', '')[:60]}"
                )
                continue
            filtered.append(p)
        deduped = _deduplicate_claims(filtered)
        return ExtractionResult(
            content_hash=content_hash,
            predictions=deduped,
        )
    except Exception as e:
        return ExtractionResult(
            content_hash=content_hash,
            predictions=[],
            error=str(e),
        )


def extract_batch_assertions(
    items: list[dict],
    provider: LLMProvider,
    sport: str = "NFL",
) -> list[ExtractionResult]:
    """
    Send multiple articles in a single LLM call for throughput efficiency.

    Each item dict must have: content_hash, text, title, author, source_name,
    published_date.

    Returns one ExtractionResult per input item (same order). On LLM error,
    returns empty ExtractionResults so callers always get len(items) results.
    """
    if not items:
        return []

    # Build the multi-article section of the prompt
    article_sections = []
    for idx, item in enumerate(items):
        text = str(item.get("text", ""))[:3000]
        section = (
            f"--- ARTICLE {idx} ---\n"
            f"PUBLISHED: {item.get('published_date', 'Unknown')}\n"
            f"AUTHOR: {item.get('author', 'Unknown')}\n"
            f"SOURCE: {item.get('source_name', 'Unknown')}\n"
            f"TITLE: {item.get('title', 'Untitled')}\n"
            f"TEXT:\n{text}"
        )
        article_sections.append(section)

    prompt = BATCH_EXTRACTION_PROMPT.format(
        sport=sport,
        articles="\n\n".join(article_sections),
    )

    # Initialize empty results for each item
    results: list[ExtractionResult] = [
        ExtractionResult(content_hash=item["content_hash"], predictions=[])
        for item in items
    ]

    try:
        raw_predictions = provider.extract_predictions(prompt)
    except Exception as e:
        err = str(e)
        logger.warning(f"Batch extraction error for {len(items)} articles: {err}")
        for r in results:
            r.error = err
        return results

    # Bucket predictions by article_index
    current_year = datetime.now().year
    per_article: dict[int, list[dict]] = {i: [] for i in range(len(items))}
    for pred in raw_predictions:
        if not pred.get("extracted_claim", "").strip():
            continue
        idx = pred.get("article_index")
        if not isinstance(idx, int) or idx < 0 or idx >= len(items):
            logger.warning(
                f"Batch pred has invalid article_index={idx!r}, skipping: "
                f"{pred.get('extracted_claim', '')[:60]}"
            )
            continue
        sy = pred.get("season_year")
        if sy is not None and isinstance(sy, (int, float)) and int(sy) < current_year:
            logger.info(
                f"Temporal filter (batch): rejected stale (season_year={sy}): "
                f"{pred.get('extracted_claim', '')[:60]}"
            )
            continue
        per_article[idx].append(pred)

    for idx, preds in per_article.items():
        results[idx].predictions = _deduplicate_claims(preds)

    return results


def get_unprocessed_media(
    db: DBManager, limit: int = 100, include_unmatched: bool = False
) -> pd.DataFrame:
    """
    Fetches raw_pundit_media rows that haven't been processed yet.
    Uses a processed_media_hashes tracking table to know what's been done.

    By default, only returns rows with a matched pundit to avoid wasting
    LLM calls on unattributed content. Pass include_unmatched=True
    to override and process all content regardless of pundit match.
    """
    project_id = os.environ.get("GCP_PROJECT_ID")
    if include_unmatched:
        pundit_filter = ""
        fallback_pundit_filter = ""
    else:
        pundit_filter = "\n              AND r.matched_pundit_id IS NOT NULL"
        fallback_pundit_filter = "\n              AND matched_pundit_id IS NOT NULL"

    try:
        query = f"""
            SELECT r.content_hash, r.source_id, r.title, r.raw_text,
                   r.source_url, r.author, r.matched_pundit_id,
                   r.matched_pundit_name, r.published_at,
                   COALESCE(r.sport, 'NFL') AS sport
            FROM `{project_id}.nfl_dead_money.{RAW_MEDIA_TABLE}` r
            LEFT JOIN `{project_id}.nfl_dead_money.{PROCESSED_TABLE}` p
                ON r.content_hash = p.content_hash
            WHERE p.content_hash IS NULL
              AND r.raw_text IS NOT NULL
              AND LENGTH(r.raw_text) > 50{pundit_filter}
            ORDER BY r.ingested_at DESC
            LIMIT {limit}
        """
        return db.fetch_df(query)
    except NotFound as e:
        logger.warning(f"Could not query processed_media_hashes (may not exist): {e}")
        query = f"""
            SELECT content_hash, source_id, title, raw_text,
                   source_url, author, matched_pundit_id,
                   matched_pundit_name, published_at,
                   COALESCE(sport, 'NFL') AS sport
            FROM `{project_id}.nfl_dead_money.{RAW_MEDIA_TABLE}`
            WHERE raw_text IS NOT NULL
              AND LENGTH(raw_text) > 50{fallback_pundit_filter}
            ORDER BY ingested_at DESC
            LIMIT {limit}
        """
        return db.fetch_df(query)


def mark_as_processed(content_hashes: list[str], db: DBManager) -> None:
    """Records which content_hashes have been processed to avoid re-extraction."""
    if not content_hashes:
        return
    now = datetime.now(timezone.utc)
    df = pd.DataFrame(
        {
            "content_hash": content_hashes,
            "processed_at": [now] * len(content_hashes),
        }
    )
    db.append_dataframe_to_table(df, PROCESSED_TABLE)


def reset_processed_hashes(db: DBManager, source_id: Optional[str] = None) -> int:
    """
    Clears processed_media_hashes so those items are re-extracted on the next run.
    """
    project_id = os.environ.get("GCP_PROJECT_ID")
    if source_id:
        query = f"""
            DELETE FROM `{project_id}.nfl_dead_money.{PROCESSED_TABLE}` p
            WHERE p.content_hash IN (
                SELECT content_hash FROM `{project_id}.nfl_dead_money.{RAW_MEDIA_TABLE}`
                WHERE source_id = '{source_id}'
            )
        """
        logger.info(f"Clearing processed hashes for source_id={source_id!r}...")
    else:
        query = (
            f"DELETE FROM `{project_id}.nfl_dead_money.{PROCESSED_TABLE}` WHERE TRUE"
        )
        logger.warning(
            "Clearing ALL processed hashes — full re-extraction on next run."
        )

    result = db.execute(query)
    rows_deleted = result.job.num_dml_affected_rows or 0
    logger.info(f"Deleted {rows_deleted} rows from {PROCESSED_TABLE}.")
    return rows_deleted


# ---------------------------------------------------------------------------
# Pre-filter (Issue #180)
# ---------------------------------------------------------------------------

FILTER_PROMPT = """You are a sports media classifier. Given the article text below, decide whether it contains at least one testable prediction about a future sporting event or player performance.

Answer with a single word: "yes" if the article contains predictions, or "no" if it does not (e.g. game recaps, injury reports, general analysis without predictions).

Sport: {sport}

Article (first 1500 chars):
{text}

Answer:"""


def should_filter_article(
    text: str,
    filter_provider=None,
    sport: str = "NFL",
) -> bool:
    """Return True if the article should be filtered out (no predictions), False to keep.

    Fail-open: errors or missing provider always return False (keep the article).
    """
    if filter_provider is None:
        return False
    try:
        prompt = FILTER_PROMPT.format(sport=sport, text=text[:1500])
        answer = filter_provider.classify(prompt)
        return not answer.strip().lower().startswith("yes")
    except Exception as exc:
        logger.warning(f"Pre-filter error (fail-open): {exc}")
        return False


def _row_to_pundit_predictions(
    row: dict, result: ExtractionResult, sport: str
) -> list[PunditPrediction]:
    """Convert an ExtractionResult into PunditPrediction objects for ledger ingestion."""
    pundit_id = row.get("matched_pundit_id") or "unknown"
    pundit_name = row.get("matched_pundit_name") or str(row.get("author", "Unknown"))
    source_url = str(row.get("source_url", ""))
    predictions = []
    for pred in result.predictions:
        raw_player = pred.get("target_player")
        if raw_player and "," in raw_player and len(raw_player.split(",")) > 1:
            player_name = "MULTI"
        else:
            player_name = raw_player or None
        raw_stance = pred.get("stance", "neutral")
        stance = (
            raw_stance if raw_stance in ("bullish", "bearish", "neutral") else "neutral"
        )
        predictions.append(
            PunditPrediction(
                pundit_id=str(pundit_id),
                pundit_name=str(pundit_name),
                source_url=source_url,
                raw_assertion_text=str(row.get("raw_text", ""))[:2000],
                extracted_claim=pred["extracted_claim"],
                claim_category=pred["claim_category"],
                season_year=pred.get("season_year"),
                target_player_id=None,
                target_player_name=player_name,
                target_team=pred.get("target_team"),
                stance=stance,
                sport=str(row.get("sport", sport)),
            )
        )
    return predictions


def _get_pub_date(row) -> str:
    if pd.notna(row.get("published_at")):
        try:
            return pd.Timestamp(row["published_at"]).strftime("%Y-%m-%d")
        except Exception:
            pass
    return ""


def run_extraction(
    limit: int = 100,
    dry_run: bool = False,
    sport: str = "NFL",
    include_unmatched: bool = False,
    db: Optional[DBManager] = None,
    provider: Optional[LLMProvider] = None,
    provider_name: Optional[str] = None,
    disable_filter: bool = False,
    workers: int = 3,
    batch_size: int = 1,
    # Legacy parameter — ignored if provider is set
    gemini_client=None,
) -> dict:
    """
    Main extraction entry point.

    1. Fetch unprocessed raw media from BQ
    2. Pre-filter articles (optional) then send to LLM for assertion extraction
    3. Parallel execution via ThreadPoolExecutor (workers param)
    4. Optional multi-article batching per LLM call (batch_size param)
    5. Ingest into the cryptographic ledger and mark as processed

    Args:
        workers: Number of concurrent LLM calls (default 3; use 5 for Gemini).
        batch_size: Articles per LLM call (default 1). Set 3–5 for batch throughput.

    Returns a summary dict for observability.
    """
    close_db = db is None
    if db is None:
        db = DBManager()

    if provider is None and not dry_run:
        config = load_llm_config()
        if provider_name:
            config.setdefault("extraction", {})["provider"] = provider_name
        provider = get_provider_with_fallback("extraction", config)

    summary = {
        "total_processed": 0,
        "predictions_extracted": 0,
        "predictions_ingested": 0,
        "errors": 0,
        "skipped_no_predictions": 0,
        "filtered_out": 0,
        "provider": getattr(provider, "model", "dry-run") if provider else "dry-run",
        "workers": workers,
        "batch_size": batch_size,
    }

    # Set up pre-filter provider if enabled
    filter_provider = None
    if not disable_filter and not dry_run:
        config = load_llm_config()
        filter_cfg = config.get("filter", {})
        if filter_cfg.get("enabled"):
            try:
                filter_provider = get_provider("filter", config)
            except Exception as exc:
                logger.warning(f"Pre-filter provider init failed (disabled): {exc}")

    try:
        media_df = get_unprocessed_media(
            db, limit=limit, include_unmatched=include_unmatched
        )
        if media_df.empty:
            logger.info("No unprocessed media found.")
            return summary

        rows_list = [row for _, row in media_df.iterrows()]
        logger.info(
            f"Processing {len(rows_list)} items "
            f"(workers={workers}, batch_size={batch_size})…"
        )
        summary["total_processed"] = len(rows_list)

        all_predictions: list[PunditPrediction] = []
        processed_hashes: list[str] = []

        if dry_run:
            for row in tqdm(rows_list, desc="Dry run", unit="article"):
                logger.info(
                    f"DRY RUN: would extract from {row['content_hash'][:16]}… "
                    f"({str(row.get('title', 'untitled'))[:50]})"
                )
            return summary

        # Pre-filter pass (sequential — filter calls are fast classify calls)
        to_extract: list = []  # list of row Series
        for row in rows_list:
            content_hash = row["content_hash"]
            if filter_provider is not None:
                article_sport = str(row.get("sport", sport))
                if should_filter_article(
                    str(row.get("raw_text", "")),
                    filter_provider=filter_provider,
                    sport=article_sport,
                ):
                    logger.info(
                        f"Pre-filter skipped {content_hash[:16]}… "
                        f"({str(row.get('title', 'untitled'))[:50]})"
                    )
                    summary["filtered_out"] += 1
                    processed_hashes.append(content_hash)
                    continue
            to_extract.append(row)

        # Group rows into batches for the LLM calls
        batch_size = max(1, batch_size)
        batches = [
            to_extract[i : i + batch_size]
            for i in range(0, len(to_extract), batch_size)
        ]

        def _process_batch(batch_rows) -> list[tuple]:
            """
            Extract predictions from one batch of rows.
            Returns list of (row, ExtractionResult) tuples — one per row.
            """
            if len(batch_rows) == 1:
                row = batch_rows[0]
                result = extract_assertions(
                    content_hash=row["content_hash"],
                    text=str(row.get("raw_text", "")),
                    title=str(row.get("title", "")),
                    author=str(row.get("author", "")),
                    source_name=str(row.get("source_id", "")),
                    sport=str(row.get("sport", sport)),
                    published_date=_get_pub_date(row),
                    provider=provider,
                )
                return [(row, result)]
            else:
                items = [
                    {
                        "content_hash": r["content_hash"],
                        "text": str(r.get("raw_text", "")),
                        "title": str(r.get("title", "")),
                        "author": str(r.get("author", "")),
                        "source_name": str(r.get("source_id", "")),
                        "published_date": _get_pub_date(r),
                    }
                    for r in batch_rows
                ]
                results = extract_batch_assertions(items, provider, sport=sport)
                return list(zip(batch_rows, results))

        effective_workers = min(workers, len(batches)) if batches else 1
        with tqdm(total=len(to_extract), desc="Extracting", unit="article") as pbar:
            with ThreadPoolExecutor(max_workers=effective_workers) as executor:
                future_to_batch = {
                    executor.submit(_process_batch, batch): batch for batch in batches
                }
                for future in as_completed(future_to_batch):
                    try:
                        row_results = future.result()
                    except Exception as exc:
                        # Entire batch failed — mark articles as processed to avoid infinite retry
                        batch = future_to_batch[future]
                        logger.error(f"Batch of {len(batch)} articles failed: {exc}")
                        for row in batch:
                            summary["errors"] += 1
                            processed_hashes.append(row["content_hash"])
                            pbar.update(1)
                        continue

                    for row, result in row_results:
                        content_hash = row["content_hash"]
                        if result.error:
                            logger.warning(
                                f"Extraction error for {content_hash[:16]}…: {result.error}"
                            )
                            summary["errors"] += 1
                            processed_hashes.append(content_hash)
                        elif not result.predictions:
                            summary["skipped_no_predictions"] += 1
                            processed_hashes.append(content_hash)
                        else:
                            summary["predictions_extracted"] += len(result.predictions)
                            all_predictions.extend(
                                _row_to_pundit_predictions(row, result, sport)
                            )
                            processed_hashes.append(content_hash)
                        pbar.update(1)

        # Batch ingest all predictions into the cryptographic ledger
        if all_predictions:
            try:
                hashes = ingest_batch(all_predictions, db=db)
                summary["predictions_ingested"] = len(hashes)
                logger.info(
                    f"Ingested {len(hashes)} predictions into cryptographic ledger."
                )
            except Exception as e:
                logger.error(f"Failed to ingest predictions to ledger: {e}")
                summary["errors"] += 1

        # Mark processed
        if processed_hashes:
            try:
                mark_as_processed(processed_hashes, db=db)
            except Exception as e:
                logger.warning(
                    f"Failed to mark processed (will re-extract next run): {e}"
                )

        logger.info(
            f"Extraction complete: {summary['total_processed']} processed, "
            f"{summary['predictions_extracted']} predictions extracted, "
            f"{summary['predictions_ingested']} ingested, "
            f"{summary['errors']} errors"
        )
        return summary
    finally:
        if close_db:
            db.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="NLP Assertion Extraction — Multi-provider LLM"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Max items to process per run",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without calling LLM or writing",
    )
    parser.add_argument(
        "--sport",
        type=str,
        default="NFL",
        help="Sport context for extraction (NFL, MLB, NBA, etc.)",
    )
    parser.add_argument(
        "--include-unmatched",
        action="store_true",
        help="Include media rows without a matched pundit (skipped by default)",
    )
    parser.add_argument(
        "--provider",
        choices=["gemini", "claude", "openai", "ollama"],
        help="Override LLM provider (default: from llm_config.yaml)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=3,
        help="Concurrent LLM calls (default 3; use 5 for Gemini, 2-3 for Ollama)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1,
        help="Articles per LLM call (default 1; set 3-5 for batch throughput mode)",
    )
    parser.add_argument(
        "--reset-processed",
        metavar="SOURCE_ID",
        nargs="?",
        const="__all__",
        help=(
            "Clear processed_media_hashes for SOURCE_ID (or all sources if omitted) "
            "so those items are re-extracted on the next run. Exits after reset."
        ),
    )
    args = parser.parse_args()

    if args.reset_processed is not None:
        db = DBManager()
        source = None if args.reset_processed == "__all__" else args.reset_processed
        deleted = reset_processed_hashes(db, source_id=source)
        print(json.dumps({"reset": True, "rows_deleted": deleted}))
    else:
        result = run_extraction(
            limit=args.limit,
            dry_run=args.dry_run,
            sport=args.sport,
            include_unmatched=args.include_unmatched,
            provider_name=args.provider,
            workers=args.workers,
            batch_size=args.batch_size,
        )
        print(json.dumps(result, indent=2))
