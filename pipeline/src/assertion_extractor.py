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
import hashlib
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
    "award_prediction",  # Named NFL awards: MVP, OPOY, DPOY, ROY, etc.
    "fa_signing",  # Free agency: player signs with a specific team
}

EXTRACTION_PROMPT = """You are a {sport} prediction extraction system. Extract testable predictions from the content below.

PUBLISHED: {published_date}
AUTHOR: {author}

Rules — what TO extract:
- Concrete, falsifiable claims about FUTURE outcomes with a clear stance
- Must have: a SUBJECT (player, team, or league-level) + a TESTABLE OUTCOME + a TIMEFRAME
- Predictions can be about players, teams, or the league — they don't have to name a specific player
- MOCK DRAFT PICKS ARE PREDICTIONS: when an author projects "Pick #3: Arvell Reese to Arizona Cardinals", that is a draft_pick prediction
- For draft_pick predictions: extract the player's FULL CORRECT NAME, the PICK NUMBER, and the TEAM
- FREE AGENCY SIGNING PREDICTIONS: "Player X will sign with Team Y" are fa_signing predictions
- AWARD PREDICTIONS: "Player X will win MVP/OPOY/DPOY/Rookie of the Year" are award_prediction predictions

⚠️ CRITICAL — TEMPORAL VALIDITY (REJECT retroactive recaps):
- A prediction MUST be FORWARD-LOOKING relative to the article's PUBLISHED date above.
- REJECT any statement where the outcome has ALREADY OCCURRED at the article's publication date.
- If an article is published AFTER the NFL Draft and says "Player X was drafted #N by Team Y" — that is a RECAP FACT, not a prediction. REJECT it.
- If an article is published AFTER a trade/signing was announced and says "Team Z signed Player Q" — REJECT it.
- ACCEPT only statements that describe events that had NOT yet happened when the article was published.
- Each extracted prediction that you INCLUDE in your output must have a "prediction_horizon_days" field: the estimated number of days from publication to when the event resolves. This value MUST be > 0.
- If you cannot identify a future event because the event is already in the past relative to the publication date, REJECT the item and DO NOT include it in your output.

Examples to REJECT (retroactive recaps — outcome already occurred at publication date):
  "Player X was drafted #257 by the Broncos" (article published after draft day) → REJECT
  "Team Z hired Coach Q" (article published after hire announced) → REJECT
  "Kaytron Allen was selected by Washington Commanders with 187th pick" (post-draft article) → REJECT

Examples to ACCEPT (forward-looking predictions — outcome had not yet occurred):
  "I think Player X will be drafted in round 1" (article pre-draft) → ACCEPT, prediction_horizon_days: 7
  "Fernando Mendoza will be drafted #1 overall by the Las Vegas Raiders" (pre-draft mock) → ACCEPT, prediction_horizon_days: 14

Examples of good extractions:
  "Fernando Mendoza will be drafted #1 overall by the Las Vegas Raiders" (draft_pick, target_player: Fernando Mendoza) → stance: neutral, prediction_horizon_days: 14
  "Arvell Reese will be drafted #3 overall by the Arizona Cardinals" (draft_pick, target_player: Arvell Reese) → stance: neutral, prediction_horizon_days: 7
  "The Raiders will win the AFC West in 2026" (game_outcome, target_player: null) → stance: bullish, prediction_horizon_days: 180
  "There will be at least 4 picks for the Jets in the first round of the 2026 draft" (draft_pick, target_player: null, target_franchise: NYJ) → stance: neutral, prediction_horizon_days: 30
  "Patrick Mahomes will throw 40+ touchdowns in 2026" (player_performance, target_player: Patrick Mahomes) → stance: bullish, prediction_horizon_days: 210
  "The Bears will make the playoffs in 2026" (game_outcome, target_player: null) → stance: bullish, prediction_horizon_days: 200
  "No quarterback other than Mendoza will go in Round 1" (draft_pick, target_player: null) → stance: neutral, prediction_horizon_days: 5
  "Davante Adams will sign with the Dallas Cowboys" (fa_signing, target_player: Davante Adams) → stance: neutral, prediction_horizon_days: 30
  "Aaron Rodgers will sign with the Miami Dolphins" (fa_signing, target_player: Aaron Rodgers) → stance: neutral, prediction_horizon_days: 30
  "Saquon Barkley will win Offensive Player of the Year" (award_prediction, target_player: Saquon Barkley) → stance: bullish, prediction_horizon_days: 200
  "Josh Allen will win MVP this season" (award_prediction, target_player: Josh Allen) → stance: bullish, prediction_horizon_days: 200
  "The Bills will win 12 or more games" (game_outcome, target_player: null) → stance: bullish, prediction_horizon_days: 200

Stance rules:
- bullish: prediction is positive/optimistic about the subject
- bearish: prediction is negative/pessimistic about the subject
- neutral: no clear directional bias (draft picks, trades, FA signings, purely factual future events)

Special handling for DRAFT PICKS:
- For draft_pick claims, ALWAYS extract the draft year (e.g., 2025, 2026 draft)
- Place the draft year in the season_year field
- Examples:
  "Will be picked in the 2025 draft" → season_year: 2025
  "2026 first round pick" → season_year: 2026
  "will go top 10 in the next draft" → season_year: [current year + 1]

Rules — what NOT to extract:
- RETROACTIVE RECAPS: any statement whose outcome had already occurred when the article was published (past tense: "was drafted", "was traded", "was hired", "was signed", "was selected", "was picked")
- HEDGED statements: "wouldn't surprise me if", "I could see", "most likely", "might", "probably"
- VAGUE claims that can't be verified: "will be good", "will make plays", "will be a factor"
- TAUTOLOGIES: "the deal will eventually be released", "they will bring in players"
- HISTORICAL FACTS or ALREADY-RESOLVED events
- OPINIONS without testable outcomes: "he's the best QB in the league"
- ADMINISTRATIVE details: payment structures, meeting schedules, procedural items
- Claims about events from PAST SEASONS that are already concluded

For the "target_player" field: use the player's FULL NAME exactly as written in the article. If the prediction is about a team or the league with no specific player, set target_player to null.
For the "claim_category" field:
  - "draft_pick" — draft position/team predictions (including mock drafts)
  - "game_outcome" — win/loss/playoff/season win total predictions
  - "player_performance" — specific stat thresholds (touchdowns, yards, etc.)
  - "award_prediction" — named NFL awards: MVP, OPOY, DPOY, Offensive/Defensive ROY, CPOY, Walter Payton Man of the Year
  - "fa_signing" — free agency: player signs with or joins a specific team
  - "trade" — player traded to a specific team
  - "contract" — contract extension/restructure predictions (NOT signing predictions — use fa_signing)
  - "injury" — injury status or return timeline predictions
For the "prediction_horizon_days" field: estimated days from publication date to event resolution. Must be > 0 for valid predictions.

If the article contains no concrete, falsifiable predictions with clear stances, return an empty list.

SOURCE: {source_name}
TITLE: {title}
TEXT:
{text}"""

# 8-char SHA-256 prefix of the prompt template — changes whenever the prompt changes.
# Used to track which prompt version produced each prediction.
PROMPT_VERSION = hashlib.sha256(EXTRACTION_PROMPT.encode("utf-8")).hexdigest()[:8]


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


def extract_assertions(
    content_hash: str,
    text: str,
    title: str = "",
    author: str = "",
    source_name: str = "",
    sport: str = "NFL",
    published_date: str = "",
    provider: Optional[LLMProvider] = None,
    allow_historical: bool = False,
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
        # Hard temporal filter: reject predictions about past seasons/drafts.
        # Bypassed with allow_historical=True for backfill ingestion of
        # already-completed seasons (2020–2024) where outcomes ARE known.
        current_year = datetime.now().year
        filtered = []
        for p in valid:
            sy = p.get("season_year")
            if (
                not allow_historical
                and sy is not None
                and isinstance(sy, (int, float))
                and int(sy) < current_year
            ):
                logger.info(
                    f"Temporal filter: rejected stale claim (season_year={sy}): "
                    f"{p.get('extracted_claim', '')[:60]}"
                )
                continue
            # prediction_horizon_days is required to enforce forward-looking assertions.
            # Reject missing, non-numeric, or non-positive values so retroactive recaps
            # cannot pass through when providers omit the field.
            phd = p.get("prediction_horizon_days")
            if phd is None or not isinstance(phd, (int, float)):
                logger.info(
                    "Temporal filter: rejected claim with missing/invalid "
                    f"prediction_horizon_days ({phd!r}): "
                    f"{p.get('extracted_claim', '')[:60]}"
                )
                continue
            if phd <= 0:
                logger.info(
                    f"Temporal filter: rejected retroactive recap "
                    f"(prediction_horizon_days={phd}): "
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
    allow_historical: bool = False,
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

    config = load_llm_config()
    if provider is None and not dry_run:
        if provider_name:
            config.setdefault("extraction", {})["provider"] = provider_name
        provider = get_provider_with_fallback("extraction", config)

    _pname = getattr(provider, "provider_name", None) if provider else None
    provider_type = (
        _pname
        if isinstance(_pname, str)
        else (
            type(provider).__name__.replace("Provider", "").lower()
            if provider
            else "dry-run"
        )
    )

    summary = {
        "total_processed": 0,
        "predictions_extracted": 0,
        "predictions_ingested": 0,
        "errors": 0,
        "skipped_no_predictions": 0,
        "extracted_zero_predictions": 0,  # items that parsed OK but LLM found nothing
        "filtered_out": 0,
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
        # In-memory guard: track hashes that yielded zero predictions this run.
        # Prevents recent items from repeatedly burning LLM calls when the model
        # consistently finds nothing. Within a single run, skip items we already
        # attempted and got zero predictions from.
        # TODO: replace with a persistent retry counter (e.g. extraction_attempts
        # table with content_hash + attempts + last_attempted_at) to guard across runs.
        seen_zero_pred_this_run: set[str] = set()

        for _, row in media_df.iterrows():
            content_hash = row["content_hash"]
            summary["total_processed"] += 1

            if dry_run:
                logger.info(
                    f"DRY RUN: would extract from {content_hash[:16]}… "
                    f"({row.get('title', 'untitled')[:50]})"
                )
                continue

            # Skip if this hash already yielded zero predictions earlier this run
            if content_hash in seen_zero_pred_this_run:
                logger.debug(
                    f"Skipping {content_hash[:16]}… (already attempted with zero predictions this run)"
                )
                summary["skipped_no_predictions"] += 1
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
                allow_historical=allow_historical,
            )

            if result.error:
                logger.warning(
                    f"Extraction error for {content_hash[:16]}…: {result.error}"
                )
                summary["errors"] += 1
                processed_hashes.append(content_hash)
                continue

            if not result.predictions:
                summary["skipped_no_predictions"] += 1
                summary["extracted_zero_predictions"] += 1
                # Do NOT mark as processed — zero-prediction items are re-queued
                # on the next run so they get another extraction attempt.
                # Track in-memory to prevent re-attempt within this run (starvation guard).
                seen_zero_pred_this_run.add(content_hash)
                title = row.get("title")
                title_str = str(title) if pd.notna(title) else "untitled"
                logger.info(
                    f"Zero predictions from {content_hash[:16]}… "
                    f"({title_str[:60]}) — not marking processed"
                )
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
                        season_year=pred.get("draft_year") or pred.get("season_year"),
                        target_player_id=None,
                        target_player_name=player_name,
                        target_team=pred.get("target_team"),
                        stance=stance,
                        sport=str(row.get("sport", sport)),
                        prompt_version=PROMPT_VERSION,
                        llm_provider=provider_type,
                        llm_model=getattr(provider, "model", None),
                    )
                )

            processed_hashes.append(content_hash)

            # Rate limiting — delay read from llm_config.yaml extraction.rate_limit_seconds
            rate_limit = config.get("extraction", {}).get("rate_limit_seconds", 1.0)
            if rate_limit > 0:
                time.sleep(rate_limit)

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
    parser.add_argument(
        "--allow-historical",
        action="store_true",
        help=(
            "Bypass the temporal filter that drops past-season predictions. "
            "Use for historical backfill (2020-2024 content) where outcomes are known."
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
            allow_historical=args.allow_historical,
        )
        print(json.dumps(result, indent=2))
