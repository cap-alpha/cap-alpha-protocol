"""
NLP Assertion Extraction Pipeline (Issue #79)

Converts unstructured pundit media text (from raw_pundit_media) into structured
prediction vectors and feeds them into the cryptographic ledger.

Pipeline flow:
  raw_pundit_media (bronze) → Gemini extraction → PunditPrediction → prediction_ledger (gold)

Uses Gemini as the LLM backbone for structured extraction. Falls back gracefully
on API errors — unprocessed rows stay in bronze for the next run.

Usage (inside Docker):
    python -m src.assertion_extractor                  # process all unprocessed
    python -m src.assertion_extractor --limit 50       # process N items
    python -m src.assertion_extractor --dry-run        # preview without writing
"""

import argparse
import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
from google import genai
from google.cloud import bigquery

from src.cryptographic_ledger import PunditPrediction, ingest_batch
from src.db_manager import DBManager

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

EXTRACTION_PROMPT = """You are a {sport} prediction extraction system. Analyze the following media content and extract any testable predictions or assertions the author makes.

For each prediction found, return a JSON array of objects with these fields:
- "extracted_claim": A concise, testable statement (e.g. "Patrick Mahomes will win MVP in 2025")
- "claim_category": One of: player_performance, game_outcome, trade, draft_pick, injury, contract
- "season_year": The {sport} season year the prediction applies to (integer, or null if unclear)
- "target_player": Player name if the prediction is about a specific player (or null)
- "target_team": {sport} team abbreviation if about a specific team (or null)
- "confidence_note": Brief note on how explicit/confident the prediction is (e.g. "strong assertion", "hedged", "speculative")

Rules:
- Only extract TESTABLE predictions that can be verified against future outcomes
- Ignore opinions that aren't predictions (e.g. "Mahomes is the best QB" is not testable)
- Ignore historical statements about past events
- If the text contains NO testable predictions, return an empty array: []
- Be conservative — only extract clear predictions, not vague commentary

SOURCE: {source_name}
AUTHOR: {author}
TITLE: {title}
TEXT:
{text}

Return ONLY a valid JSON array, no other text."""


@dataclass
class ExtractionResult:
    content_hash: str
    predictions: list[dict]
    error: Optional[str] = None
    raw_response: Optional[str] = None


def _get_gemini_client() -> genai.Client:
    """Initialize Gemini client with API key."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY not set")
    return genai.Client(api_key=api_key)


def extract_assertions(
    content_hash: str,
    text: str,
    title: str = "",
    author: str = "",
    source_name: str = "",
    sport: str = "NFL",
    client: Optional[genai.Client] = None,
) -> ExtractionResult:
    """
    Sends media text to Gemini for structured prediction extraction.
    Returns an ExtractionResult with parsed predictions.
    """
    if client is None:
        client = _get_gemini_client()

    prompt = EXTRACTION_PROMPT.format(
        sport=sport,
        source_name=source_name or "Unknown",
        author=author or "Unknown",
        title=title or "Untitled",
        text=text[:4000],  # Truncate to stay within token limits
    )

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
        )

        raw_text = response.text.strip()

        # Strip markdown code fences if present
        if raw_text.startswith("```"):
            lines = raw_text.split("\n")
            # Remove first and last lines (```json and ```)
            raw_text = "\n".join(
                lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
            )

        predictions = json.loads(raw_text)

        if not isinstance(predictions, list):
            return ExtractionResult(
                content_hash=content_hash,
                predictions=[],
                error="Gemini returned non-array JSON",
                raw_response=raw_text,
            )

        # Validate and normalize each prediction
        valid = []
        for pred in predictions:
            claim = pred.get("extracted_claim", "").strip()
            category = pred.get("claim_category", "").strip().lower()
            if not claim:
                continue
            if category not in VALID_CATEGORIES:
                category = "player_performance"  # default fallback

            valid.append(
                {
                    "extracted_claim": claim,
                    "claim_category": category,
                    "season_year": pred.get("season_year"),
                    "target_player": pred.get("target_player"),
                    "target_team": pred.get("target_team"),
                    "confidence_note": pred.get("confidence_note", ""),
                }
            )

        return ExtractionResult(
            content_hash=content_hash,
            predictions=valid,
            raw_response=raw_text,
        )

    except json.JSONDecodeError as e:
        return ExtractionResult(
            content_hash=content_hash,
            predictions=[],
            error=f"JSON parse error: {e}",
            raw_response=raw_text if "raw_text" in dir() else None,
        )
    except Exception as e:
        return ExtractionResult(
            content_hash=content_hash,
            predictions=[],
            error=str(e),
        )


def get_unprocessed_media(db: DBManager, limit: int = 100) -> pd.DataFrame:
    """
    Fetches raw_pundit_media rows that haven't been processed yet.
    Uses a processed_media_hashes tracking table to know what's been done.
    """
    project_id = os.environ.get("GCP_PROJECT_ID")

    # Check if tracking table exists; if not, return all raw media
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
              AND LENGTH(r.raw_text) > 50
            ORDER BY r.ingested_at DESC
            LIMIT {limit}
        """
        return db.fetch_df(query)
    except Exception as e:
        # Tracking table may not exist — fall back to just raw media
        logger.warning(f"Could not query processed_media_hashes (may not exist): {e}")
        query = f"""
            SELECT content_hash, source_id, title, raw_text,
                   source_url, author, matched_pundit_id,
                   matched_pundit_name, published_at,
                   COALESCE(sport, 'NFL') AS sport
            FROM `{project_id}.nfl_dead_money.{RAW_MEDIA_TABLE}`
            WHERE raw_text IS NOT NULL
              AND LENGTH(raw_text) > 50
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


def run_extraction(
    limit: int = 100,
    dry_run: bool = False,
    sport: str = "NFL",
    db: Optional[DBManager] = None,
    gemini_client: Optional[genai.Client] = None,
) -> dict:
    """
    Main extraction entry point.

    1. Fetch unprocessed raw media from BQ
    2. Send each to Gemini for assertion extraction
    3. Convert extracted predictions into PunditPredictions
    4. Ingest into the cryptographic ledger
    5. Mark as processed

    Returns a summary dict for observability.
    """
    close_db = db is None
    if db is None:
        db = DBManager()

    if gemini_client is None and not dry_run:
        gemini_client = _get_gemini_client()

    summary = {
        "total_processed": 0,
        "predictions_extracted": 0,
        "predictions_ingested": 0,
        "errors": 0,
        "skipped_no_predictions": 0,
    }

    try:
        media_df = get_unprocessed_media(db, limit=limit)
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

            result = extract_assertions(
                content_hash=content_hash,
                text=str(row.get("raw_text", "")),
                title=str(row.get("title", "")),
                author=str(row.get("author", "")),
                source_name=str(row.get("source_id", "")),
                sport=str(row.get("sport", sport)),
                client=gemini_client,
            )

            if result.error:
                logger.warning(
                    f"Extraction error for {content_hash[:16]}…: {result.error}"
                )
                summary["errors"] += 1
                # Still mark as processed to avoid infinite retry loops
                # — errors will be logged and can be reprocessed manually
                processed_hashes.append(content_hash)
                continue

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
                all_predictions.append(
                    PunditPrediction(
                        pundit_id=str(pundit_id),
                        pundit_name=str(pundit_name),
                        source_url=source_url,
                        raw_assertion_text=str(row.get("raw_text", ""))[:2000],
                        extracted_claim=pred["extracted_claim"],
                        claim_category=pred["claim_category"],
                        season_year=pred.get("season_year"),
                        target_player_id=pred.get("target_player"),
                        target_team=pred.get("target_team"),
                        sport=str(row.get("sport", sport)),
                    )
                )

            processed_hashes.append(content_hash)

            # Rate limit: Gemini free tier is 15 RPM
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
        description="NLP Assertion Extraction — Gemini-powered"
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
        help="Preview without calling Gemini or writing",
    )
    parser.add_argument(
        "--sport",
        type=str,
        default="NFL",
        help="Sport context for extraction (NFL, MLB, NBA, etc.)",
    )
    args = parser.parse_args()

    result = run_extraction(limit=args.limit, dry_run=args.dry_run, sport=args.sport)
    print(json.dumps(result, indent=2))
