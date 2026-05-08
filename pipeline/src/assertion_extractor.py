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
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

import pandas as pd
import yaml
from google.api_core.exceptions import NotFound
from google.cloud import bigquery as _bigquery
from google.cloud.bigquery import QueryJobConfig, ScalarQueryParameter
from src.cryptographic_ledger import (
    PunditPrediction,
    compute_prediction_hash,
    ingest_batch,
)
from src.db_manager import DBManager
from src.llm_provider import (
    LLMProvider,
    get_provider,
    get_provider_with_fallback,
    load_llm_config,
)
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
logger = logging.getLogger(__name__)

RAW_MEDIA_TABLE = "raw_pundit_media"
PROCESSED_TABLE = "processed_media_hashes"
DEDUP_LOG_TABLE = "gold_layer.claim_dedup_log"
LEDGER_TABLE = "gold_layer.prediction_ledger"

# ---------------------------------------------------------------------------
# Retry / backoff helpers (Issue #550)
# ---------------------------------------------------------------------------

# These error message fragments indicate transient failures that should be
# retried.  Auth errors and schema-validation failures are NOT in this list
# and will fail-fast.
_TRANSIENT_FRAGMENTS = (
    "connection",
    "timeout",
    "timed out",
    "temporarily unavailable",
    "service unavailable",
    "internal server error",
    "bad gateway",
    "gateway timeout",
    "reset by peer",
    "broken pipe",
    "eof occurred",
    "remote end closed",
    "connection refused",
    "network",
    "read timeout",
    "connect timeout",
    "http error 500",
    "http error 502",
    "http error 503",
    "http error 504",
    "status code 500",
    "status code 502",
    "status code 503",
    "status code 504",
)

# These fragments indicate permanent failures — auth, schema, bad requests.
# Do NOT retry these.
_PERMANENT_FRAGMENTS = (
    "401",
    "403",
    "unauthorized",
    "forbidden",
    "api key",
    "authentication",
    "permission denied",
    "invalid api key",
    "quota exceeded",  # hard quota — retrying won't help
    "billing",
)


def _is_transient_llm_error(exc: BaseException) -> bool:
    """
    Return True for transient LLM/network errors that warrant a retry.

    Permanent errors (auth, schema-validation, hard quota) return False
    so tenacity stops retrying immediately via retry_if_exception.
    """
    msg = str(exc).lower()

    # Explicit permanent-error check first (short-circuit)
    for frag in _PERMANENT_FRAGMENTS:
        if frag in msg:
            return False

    # Check for known transient patterns
    for frag in _TRANSIENT_FRAGMENTS:
        if frag in msg:
            return True

    # requests.exceptions live behind a lazy import in llm_provider; check
    # by class name so we don't require requests at module import time.
    cls_name = type(exc).__name__
    transient_classes = {
        "ConnectionError",
        "Timeout",
        "ReadTimeout",
        "ConnectTimeout",
        "ChunkedEncodingError",
        "HTTPError",
        "SSLError",
        "ProxyError",
    }
    if cls_name in transient_classes:
        return True

    return False


# Default tier assigned to sources not found in media_sources.yaml
DEFAULT_PRIORITY_TIER = 2

# Sources with yield_rate below this threshold AND tier==3 get skip_extraction=True
SKIP_EXTRACTION_YIELD_THRESHOLD = 0.05

_SOURCE_CONFIG_CACHE: Optional[dict] = None

# Allowlist pattern for source_id values used in SQL queries.
# Restricts to alphanumeric, underscores, and hyphens — the only characters
# that appear in real source ids (e.g. "espn_nfl", "pat-mcafee-show").
_SOURCE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")


def _validate_source_id(source_id: str) -> str:
    """
    Validate a source_id before it is used in a SQL expression.

    Returns the source_id unchanged if it matches the allowlist pattern.
    Raises ValueError with a descriptive message if it contains unexpected
    characters (e.g. SQL-injection payloads like ``foo' OR '1'='1``).
    """
    if not _SOURCE_ID_PATTERN.match(source_id):
        raise ValueError(
            f"Invalid source_id {source_id!r}: must match [a-zA-Z0-9_-]{{1,128}}. "
            "This value came from user/YAML input and failed the allowlist check."
        )
    return source_id


def load_source_config() -> dict:
    """
    Load media_sources.yaml and return a dict keyed by source id.
    Returns priority_tier (default 2) and skip_extraction (default False) per source.
    Results are cached in-process.
    """
    global _SOURCE_CONFIG_CACHE
    if _SOURCE_CONFIG_CACHE is not None:
        return _SOURCE_CONFIG_CACHE

    config_path = Path(__file__).parent.parent / "config" / "media_sources.yaml"
    try:
        with open(config_path) as f:
            raw = yaml.safe_load(f)
        sources = raw.get("sources", [])
        _SOURCE_CONFIG_CACHE = {
            s["id"]: {
                "priority_tier": s.get("priority_tier", DEFAULT_PRIORITY_TIER),
                "skip_extraction": s.get("skip_extraction", False),
                "name": s.get("name", s["id"]),
            }
            for s in sources
            if "id" in s
        }
    except Exception as exc:
        logger.warning(f"Could not load media_sources.yaml ({exc}); using defaults")
        _SOURCE_CONFIG_CACHE = {}
    return _SOURCE_CONFIG_CACHE


def get_source_priority_tier(source_id: str) -> int:
    """Return the priority_tier for a given source_id (default: 2)."""
    cfg = load_source_config()
    return cfg.get(source_id, {}).get("priority_tier", DEFAULT_PRIORITY_TIER)


def is_skip_extraction(source_id: str) -> bool:
    """Return True if the source is configured to skip LLM extraction."""
    cfg = load_source_config()
    return cfg.get(source_id, {}).get("skip_extraction", False)


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

PROMPT_VERSION = hashlib.sha256(EXTRACTION_PROMPT.encode("utf-8")).hexdigest()[:8]


@dataclass
class ExtractionResult:
    content_hash: str
    predictions: list[dict]
    error: Optional[str] = None
    raw_response: Optional[str] = None


# ---------------------------------------------------------------------------
# Exact-match claim deduplication (Issue #808 Phase 0)
# ---------------------------------------------------------------------------


def compute_claim_norm_key(
    claim_category: Optional[str],
    target_player_name: Optional[str],
    target_team: Optional[str],
    season_year: Optional[int],
) -> str:
    """
    Compute the exact-match deduplication key for a prediction.

    SHA-256 of LOWER(TRIM(claim_category | target_player_name | target_team | season_year)).
    NULL fields are treated as empty string to produce a deterministic key.
    This is the Phase 0 exact-match gate; Phase 1+ will layer semantic embeddings on top.
    """
    parts = [
        claim_category or "",
        target_player_name or "",
        target_team or "",
        str(season_year) if season_year is not None else "",
    ]
    raw = "|".join(parts).lower().strip()
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def check_claim_is_duplicate(
    norm_key: str,
    db: "DBManager",
) -> Optional[str]:
    """
    Query prediction_ledger for an existing claim with the given norm_key.

    Returns the canonical prediction_hash if a duplicate is found, or None if
    this is a new unique claim.  Uses a LIMIT 1 query so it is O(1) in BigQuery
    with the CLUSTER BY on claim_norm_key (added by migration 015).
    """
    project_id = os.environ.get("GCP_PROJECT_ID")
    if not project_id:
        logger.warning("GCP_PROJECT_ID not set; skipping dedup check")
        return None

    query = f"""
        SELECT prediction_hash
        FROM `{project_id}.{LEDGER_TABLE}`
        WHERE claim_norm_key = @norm_key
        LIMIT 1
    """
    try:
        job_config = QueryJobConfig(
            query_parameters=[ScalarQueryParameter("norm_key", "STRING", norm_key)]
        )
        df = db.fetch_df(query, job_config=job_config)
        if df.empty:
            return None
        return str(df.iloc[0]["prediction_hash"])
    except Exception as exc:
        # Fail-open: if the dedup check errors (e.g. column not yet migrated),
        # treat it as a non-duplicate so ingestion can proceed.
        logger.warning(
            "Dedup check failed (fail-open — treating as non-duplicate): %s", exc
        )
        return None


def log_duplicate_claim(
    dupe_hash: str,
    canonical_hash: str,
    norm_key: str,
    pundit_id: str,
    db: "DBManager",
) -> None:
    """
    Write a dedup event to gold_layer.claim_dedup_log.

    Called when an incoming claim is suppressed as an exact match of an existing
    ledger entry.  The claim is NOT written to prediction_ledger; only this log
    row is created, preserving a full audit trail.
    """
    project_id = os.environ.get("GCP_PROJECT_ID")
    now = datetime.now(timezone.utc)
    df = pd.DataFrame(
        [
            {
                "dupe_hash": dupe_hash,
                "canonical_hash": canonical_hash,
                "norm_key": norm_key,
                "pundit_id": pundit_id,
                "ingested_at": now,
                "match_type": "exact",
            }
        ]
    )
    try:
        # DEDUP_LOG_TABLE is in the gold_layer dataset; use the BQ client directly
        # (same pattern as cryptographic_ledger._append_to_ledger).
        table_ref = f"{project_id}.{DEDUP_LOG_TABLE}"
        job_config = _bigquery.LoadJobConfig(write_disposition="WRITE_APPEND")
        job = db.client.load_table_from_dataframe(df, table_ref, job_config=job_config)
        job.result()
        logger.info(
            "Dedup: logged duplicate claim dupe_hash=%s canonical_hash=%s pundit_id=%s",
            dupe_hash[:16],
            canonical_hash[:16],
            pundit_id,
        )
    except Exception as exc:
        logger.warning(
            "Dedup: failed to write dedup log row (dupe_hash=%s): %s",
            dupe_hash[:16],
            exc,
        )


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

    Args:
        allow_historical: If True, skip the temporal filter that rejects claims
            about past seasons. Use for historical backfill runs where articles
            are from prior years.
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

    @retry(
        retry=retry_if_exception(_is_transient_llm_error),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def _call_provider() -> list[dict]:
        return provider.extract_predictions(prompt)

    try:
        predictions = _call_provider()
        # Filter empty claims, then deduplicate near-identical ones
        valid = [p for p in predictions if p.get("extracted_claim", "").strip()]
        # Hard temporal filter: reject predictions about past seasons/drafts.
        # Bypassed with allow_historical=True for backfill ingestion of
        # already-completed seasons where outcomes ARE known.
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

    Results are sorted by source priority_tier ASC (tier 1 first), then
    published_at DESC (newest first within each tier), so high-yield sources
    fill the --limit allocation before low-yield ones.

    Sources marked skip_extraction=True in media_sources.yaml are excluded
    entirely to avoid wasting LLM calls.

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

    # Build skip-list from source config
    source_cfg = load_source_config()
    skip_sources = [
        sid for sid, cfg in source_cfg.items() if cfg.get("skip_extraction")
    ]
    # Build priority lookup for in-Python sort (BigQuery doesn't know about YAML config)
    priority_map = {sid: cfg["priority_tier"] for sid, cfg in source_cfg.items()}

    skip_filter = ""
    fallback_skip_filter = ""
    if skip_sources:
        # Validate every source_id from media_sources.yaml before interpolation.
        # This guards against a malicious PR inserting a poisoned id that could
        # break the query or widen the NOT IN filter via SQL injection.
        validated_ids = []
        for sid in skip_sources:
            try:
                validated_ids.append(_validate_source_id(sid))
            except ValueError:
                logger.warning(
                    f"Skipping invalid source_id {sid!r} from media_sources.yaml "
                    "(failed allowlist check — not included in skip filter)"
                )
        if validated_ids:
            skip_ids = ", ".join(f"'{s}'" for s in validated_ids)
            skip_filter = f"\n              AND r.source_id NOT IN ({skip_ids})"
            fallback_skip_filter = f"\n              AND source_id NOT IN ({skip_ids})"

    try:
        # Fetch more rows than needed so we can re-sort by tier in Python
        # (BQ doesn't have the YAML config; fetching 3× limit then trimming is safe)
        fetch_limit = max(limit * 3, 300)
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
              AND LENGTH(r.raw_text) > 50{pundit_filter}{skip_filter}
            ORDER BY r.published_at DESC
            LIMIT {fetch_limit}
        """
        df = db.fetch_df(query)
        return _apply_priority_sort(df, priority_map, limit)
    except NotFound as e:
        logger.warning(f"Could not query processed_media_hashes (may not exist): {e}")
        query = f"""
            SELECT content_hash, source_id, title, raw_text,
                   source_url, author, matched_pundit_id,
                   matched_pundit_name, published_at,
                   COALESCE(sport, 'NFL') AS sport
            FROM `{project_id}.nfl_dead_money.{RAW_MEDIA_TABLE}`
            WHERE raw_text IS NOT NULL
              AND LENGTH(raw_text) > 50{fallback_pundit_filter}{fallback_skip_filter}
            ORDER BY ingested_at DESC
            LIMIT {fetch_limit}
        """
        df = db.fetch_df(query)
        return _apply_priority_sort(df, priority_map, limit)


def _apply_priority_sort(
    df: pd.DataFrame, priority_map: dict, limit: int
) -> pd.DataFrame:
    """
    Sort a media DataFrame by source priority_tier ASC, then published_at DESC.
    Sources not in priority_map get DEFAULT_PRIORITY_TIER.
    Trims to `limit` rows after sorting.
    """
    if df.empty:
        return df
    df = df.copy()
    df["_priority_tier"] = df["source_id"].map(
        lambda sid: priority_map.get(sid, DEFAULT_PRIORITY_TIER)
    )
    df = df.sort_values(
        ["_priority_tier", "published_at"],
        ascending=[True, False],
        na_position="last",
    ).drop(columns=["_priority_tier"])
    return df.head(limit).reset_index(drop=True)


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

    ``source_id`` is validated against an allowlist pattern and passed to BigQuery
    as a bound ``ScalarQueryParameter`` — never interpolated into SQL directly.
    Raises ``ValueError`` for any source_id that fails the allowlist check.
    """
    project_id = os.environ.get("GCP_PROJECT_ID")
    if source_id:
        # Validate before use — raises ValueError on injection payloads.
        _validate_source_id(source_id)

        # Use BigQuery named parameter (@source_id) so the value is never
        # concatenated into SQL text.  This closes the SQLi vector from #553.
        query = f"""
            DELETE FROM `{project_id}.nfl_dead_money.{PROCESSED_TABLE}` p
            WHERE p.content_hash IN (
                SELECT content_hash FROM `{project_id}.nfl_dead_money.{RAW_MEDIA_TABLE}`
                WHERE source_id = @source_id
            )
        """
        job_config = QueryJobConfig(
            query_parameters=[ScalarQueryParameter("source_id", "STRING", source_id)]
        )
        logger.info(f"Clearing processed hashes for source_id={source_id!r}...")
        result = db.execute(query, query_parameters=job_config.query_parameters)
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
        "skipped_low_yield": 0,
        "duplicates_suppressed": 0,
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

        # Compute provider provenance once for all predictions in this run
        provider_type = (
            type(provider).__name__.replace("Provider", "").lower()
            if provider
            else None
        )
        llm_model = getattr(provider, "model", None) if provider else None

        for _, row in media_df.iterrows():
            content_hash = row["content_hash"]
            source_id = str(row.get("source_id", ""))
            summary["total_processed"] += 1

            # Belt-and-suspenders: skip sources marked skip_extraction even if they
            # slipped through the query filter (e.g. config added after last fetch)
            if not dry_run and is_skip_extraction(source_id):
                logger.info(
                    f"Skipping {content_hash[:16]}… — source '{source_id}' has "
                    f"skip_extraction=True (low yield)"
                )
                summary["skipped_low_yield"] += 1
                processed_hashes.append(content_hash)
                continue

            if dry_run:
                tier = get_source_priority_tier(source_id)
                logger.info(
                    f"DRY RUN: would extract from {content_hash[:16]}… "
                    f"[tier={tier}] ({row.get('title', 'untitled')[:50]})"
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
                    f"Extraction error for {content_hash[:16]}…: {result.error} "
                    f"— leaving unprocessed so next run retries"
                )
                summary["errors"] += 1
                # Do NOT mark as processed — leave the hash out of
                # processed_hashes so the next pipeline run will retry
                # this article rather than silently treating it as done.
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

                # --- Phase 0 exact-match dedup gate (Issue #808) ---
                norm_key = compute_claim_norm_key(
                    claim_category=pred.get("claim_category"),
                    target_player_name=player_name,
                    target_team=pred.get("target_team"),
                    season_year=pred.get("season_year"),
                )
                canonical_hash = check_claim_is_duplicate(norm_key, db)
                if canonical_hash is not None:
                    # Duplicate found: log it and skip ingestion into the ledger.
                    # We compute a hash for the incoming (suppressed) claim so the
                    # dedup log row is self-contained.
                    incoming = PunditPrediction(
                        pundit_id=str(pundit_id),
                        pundit_name=str(pundit_name),
                        source_url=source_url,
                        raw_assertion_text=str(row.get("raw_text", ""))[:2000],
                        extracted_claim=pred["extracted_claim"],
                        claim_category=pred.get("claim_category"),
                        season_year=pred.get("season_year"),
                        target_player_id=None,
                        target_player_name=player_name,
                        target_team=pred.get("target_team"),
                        stance=stance,
                        sport=str(row.get("sport", sport)),
                        prompt_version=PROMPT_VERSION,
                        llm_provider=provider_type,
                        llm_model=str(llm_model) if llm_model else None,
                        claim_norm_key=norm_key,
                    )
                    dupe_hash = compute_prediction_hash(incoming)
                    log_duplicate_claim(
                        dupe_hash=dupe_hash,
                        canonical_hash=canonical_hash,
                        norm_key=norm_key,
                        pundit_id=str(pundit_id),
                        db=db,
                    )
                    summary["duplicates_suppressed"] = (
                        summary.get("duplicates_suppressed", 0) + 1
                    )
                    logger.info(
                        "Dedup (exact): suppressed claim norm_key=%s…  "
                        "canonical=%s…  pundit=%s",
                        norm_key[:16],
                        canonical_hash[:16],
                        pundit_id,
                    )
                    continue
                # --- end dedup gate ---

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
                        prompt_version=PROMPT_VERSION,
                        llm_provider=provider_type,
                        llm_model=str(llm_model) if llm_model else None,
                        claim_norm_key=norm_key,
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
            f"{summary['duplicates_suppressed']} exact-match duplicates suppressed, "
            f"{summary['skipped_low_yield']} skipped (low-yield source), "
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
