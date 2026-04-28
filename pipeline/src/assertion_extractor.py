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
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Optional

import pandas as pd
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

# Bump this when the extraction prompt changes so v1 vs v2 can be compared in BQ
PROMPT_VERSION = "v2"

# Hedge words that, when present without a specific anchor (name/number/team),
# indicate a vague claim that should be dropped post-extraction.
_HEDGE_ONLY_WORDS = frozenset(
    ["might", "could", "may", "possible", "perhaps", "potentially", "maybe"]
)

# Confident language words — at least one must appear for a claim to pass
_CONFIDENT_WORDS = frozenset(
    [
        "will",
        "is going to",
        "predicts",
        "expects",
        "expect",
        "predicted",
        "going to",
        "shall",
        "won't",
        "won't",  # curly apostrophe variant
        "will not",
    ]
)

EXTRACTION_PROMPT = """You are a {sport} prediction extraction system (prompt version: v2).

STRICT QUALITY GATE — only extract a claim if ALL FOUR conditions are met:

  1. FALSIFIABLE: The claim can be proven TRUE or FALSE after the event.
  2. SPECIFIC: The claim includes at least one concrete anchor — a player name, team name,
     pick number, stat threshold (e.g. "4,500 yards"), contract value, or win total.
  3. CONFIDENT LANGUAGE: The pundit uses assertive language — "will", "is going to",
     "predicts", "expects", "I have X going to Y". NOT "might", "could", "may",
     "possible", "perhaps", "wouldn't surprise me", "I could see".
  4. FUTURE AT TIME OF WRITING: The event had not yet occurred as of PUBLISHED date below.

PUBLISHED: {published_date}

━━━ EXTRACT THESE (meet all 4 conditions) ━━━
  "Travis Hunter will be the #1 overall pick"         → specific pick, confident "will"
  "Lamar Jackson will throw for 4,500 yards this season" → player + stat threshold
  "The Eagles will win the Super Bowl"                → team + specific outcome
  "He'll sign a 4-year, $120M extension before the draft" → specific contract terms
  "I have the Chiefs going 13-4 in the regular season"   → team + win total, assertive

━━━ DO NOT EXTRACT THESE (fail at least one condition) ━━━
  "Tyreek Hill might reunite with the Kansas City Chiefs" → hedge word "might" (fails #3)
  "Taylor may have an opportunity to carve out a role"   → "may" + no specific outcome (fails #2 & #3)
  "The Jets defense will utilize four-down fronts"       → scheme description, not falsifiable (fails #1)
  "He might be a good fit"                               → vague + hedge (fails #2 & #3)
  "The defense could struggle"                           → no specific metric (fails #2 & #3)
  "Sources say talks are ongoing"                        → not a prediction (fails #1 & #3)
  "He has the talent to start"                           → not a prediction (fails #1 & #3)
  "The Chiefs will be competitive"                       → too vague, obvious consensus (fails #2)
  "wouldn't surprise me if he wins MVP"                  → hedge framing (fails #3)
  "I could see him going top 5"                          → hedge "could see" (fails #3)

ADDITIONAL rules — also skip:
- TAUTOLOGIES: "they will bring in players", "the deal will eventually be released"
- ADMINISTRATIVE details: payment structures, meeting schedules, procedural items
- HISTORICAL FACTS: outcome already known at publish date → skip entirely

Stance rules:
- bullish: positive/optimistic about the subject (win award, make playoffs, exceed stat)
- bearish: negative/pessimistic (miss playoffs, underperform, get cut, lose)
- neutral: no directional bias (retirement, trade, factual future event)

Special handling for DRAFT PICKS:
- Always extract the draft year into season_year (e.g., 2025 draft → season_year: 2025)
- "will go top 10 in the next draft" → season_year: current_year + 1

If the article contains NO claims that satisfy all four conditions, return an empty list [].

SOURCE: {source_name}
AUTHOR: {author}
TITLE: {title}
TEXT:
{text}"""


@dataclass
class ExtractionResult:
    content_hash: str
    predictions: list[dict]
    error: Optional[str] = None
    raw_response: Optional[str] = None
    filtered_low_quality: int = 0


def _deduplicate_claims(predictions: list[dict], threshold: float = 0.75) -> list[dict]:
    """
    Remove near-duplicate claims from a single article's extraction.
    Uses SequenceMatcher to detect semantic overlap. Keeps the longest
    (most specific) claim from each cluster.
    """
    if len(predictions) <= 1:
        return predictions

    from difflib import SequenceMatcher

    kept = []
    for pred in predictions:
        claim = pred.get("extracted_claim", "").lower()
        is_dup = False
        for i, existing in enumerate(kept):
            existing_claim = existing.get("extracted_claim", "").lower()
            ratio = SequenceMatcher(None, claim, existing_claim).ratio()
            if ratio >= threshold:
                # Keep the longer (more specific) one
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


def _heuristic_quality_gate(predictions: list[dict]) -> tuple[list[dict], int]:
    """
    Post-LLM heuristic filter: drop claims that contain ONLY hedge words
    (might/could/may/possible/perhaps) with no specific anchor (player name,
    team, number, dollar amount).

    Returns (kept_predictions, filtered_count).
    """
    import re

    # Regex for a "specific anchor": a capitalised multi-char proper-noun token
    # (min 3 chars to exclude pronouns like "He", "It"), a number, or a dollar
    # amount — any of these rescue a claim from being pure hedging.
    _ANCHOR_RE = re.compile(
        r"(?:"
        r"\$\d+"  # dollar amounts like $120M
        r"|\d+"  # any number (yards, picks, wins, etc.)
        r"|[A-Z][a-z]{2,}"  # proper noun ≥ 3 chars (excludes He/It/I/A)
        r")"
    )

    kept = []
    filtered = 0
    for pred in predictions:
        claim = pred.get("extracted_claim", "")
        claim_lower = claim.lower()
        words = set(claim_lower.split())

        has_hedge = bool(words & _HEDGE_ONLY_WORDS)
        has_confident = any(cw in claim_lower for cw in _CONFIDENT_WORDS)
        has_anchor = bool(_ANCHOR_RE.search(claim))

        # Drop if: has hedge word AND no confident language AND no specific anchor
        if has_hedge and not has_confident and not has_anchor:
            logger.info(
                f"Heuristic quality gate: filtered hedge-only claim: {claim[:80]!r}"
            )
            filtered += 1
            continue

        kept.append(pred)

    return kept, filtered


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
        # Filter empty claims
        valid = [p for p in predictions if p.get("extracted_claim", "").strip()]
        # Hard temporal filter: reject predictions about past seasons/drafts
        current_year = datetime.now().year
        temporally_filtered = []
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
            temporally_filtered.append(p)
        # Post-LLM heuristic quality gate: drop hedge-only vague claims
        quality_passed, quality_filtered = _heuristic_quality_gate(temporally_filtered)
        if quality_filtered:
            logger.info(
                f"Heuristic gate: dropped {quality_filtered} low-quality claim(s) "
                f"from {content_hash[:16]}…"
            )
        deduped = _deduplicate_claims(quality_passed)
        return ExtractionResult(
            content_hash=content_hash,
            predictions=deduped,
            filtered_low_quality=quality_filtered,
        )
    except Exception as e:
        return ExtractionResult(
            content_hash=content_hash,
            predictions=[],
            error=str(e),
        )


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


def run_extraction(
    limit: int = 100,
    dry_run: bool = False,
    sport: str = "NFL",
    include_unmatched: bool = False,
    db: Optional[DBManager] = None,
    provider: Optional[LLMProvider] = None,
    provider_name: Optional[str] = None,
    disable_filter: bool = False,
    # Legacy parameter — ignored if provider is set
    gemini_client=None,
) -> dict:
    """
    Main extraction entry point.

    1. Fetch unprocessed raw media from BQ
    2. Send each to LLM for assertion extraction
    3. Convert extracted predictions into PunditPredictions
    4. Ingest into the cryptographic ledger
    5. Mark as processed

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
        "filtered_low_quality": 0,
        "prompt_version": PROMPT_VERSION,
        "provider": getattr(provider, "model", "dry-run") if provider else "dry-run",
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

        logger.info(f"Processing {len(media_df)} unprocessed media items...")

        all_predictions = []
        processed_hashes = []

        for _, row in media_df.iterrows():
            content_hash = row["content_hash"]
            summary["total_processed"] += 1

            if dry_run:
                logger.info(
                    f"DRY RUN: would extract from {content_hash[:16]}… "
                    f"({row.get('title', 'untitled')[:50]})"
                )
                continue

            # Pre-filter: skip articles with no predictions
            if filter_provider is not None:
                article_sport = str(row.get("sport", sport))
                if should_filter_article(
                    str(row.get("raw_text", "")),
                    filter_provider=filter_provider,
                    sport=article_sport,
                ):
                    logger.info(
                        f"Pre-filter skipped {content_hash[:16]}… "
                        f"({row.get('title', 'untitled')[:50]})"
                    )
                    summary["filtered_out"] += 1
                    processed_hashes.append(content_hash)
                    continue

            # Format publish date for the prompt
            pub_date = ""
            if pd.notna(row.get("published_at")):
                try:
                    pub_date = pd.Timestamp(row["published_at"]).strftime("%Y-%m-%d")
                except Exception:
                    pub_date = ""

            result = extract_assertions(
                content_hash=content_hash,
                text=str(row.get("raw_text", "")),
                title=str(row.get("title", "")),
                author=str(row.get("author", "")),
                source_name=str(row.get("source_id", "")),
                sport=str(row.get("sport", sport)),
                published_date=pub_date,
                provider=provider,
            )

            if result.error:
                logger.warning(
                    f"Extraction error for {content_hash[:16]}…: {result.error}"
                )
                summary["errors"] += 1
                processed_hashes.append(content_hash)
                continue

            summary["filtered_low_quality"] += result.filtered_low_quality

            if not result.predictions:
                summary["skipped_no_predictions"] += 1
                processed_hashes.append(content_hash)
                continue

            summary["predictions_extracted"] += len(result.predictions)

            # Convert to PunditPredictions for ledger ingestion
            pundit_id = row.get("matched_pundit_id") or "unknown"
            pundit_name = row.get("matched_pundit_name") or str(
                row.get("author", "Unknown")
            )
            source_url = str(row.get("source_url", ""))

            for pred in result.predictions:
                raw_player = pred.get("target_player")
                player_name = None
                if raw_player:
                    if "," in raw_player and len(raw_player.split(",")) > 1:
                        player_name = "MULTI"
                    else:
                        player_name = raw_player

                raw_stance = pred.get("stance", "neutral")
                stance = (
                    raw_stance
                    if raw_stance in ("bullish", "bearish", "neutral")
                    else "neutral"
                )
                all_predictions.append(
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

            processed_hashes.append(content_hash)

            # Rate limiting — configurable per provider
            time.sleep(4)

        # Batch ingest all predictions into the cryptographic ledger
        if all_predictions and not dry_run:
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
        if processed_hashes and not dry_run:
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
        )
        print(json.dumps(result, indent=2))
