"""
NLP Assertion Extraction Pipeline (Issue #79, #178, #555 Phase C)

Converts unstructured pundit media text (from raw_pundit_media) into structured
prediction vectors and feeds them into the cryptographic ledger.

Pipeline flow (Phase C):
  raw_pundit_media (bronze)
    → LLM extraction (speech_act_type + testability_score inline)
    → raw_utterance (silver_v2_claims) — ALL utterances written here
    → prediction_ledger (gold) — only testable assertions/conditionals/recalls

Uses a pluggable LLM provider (Gemini, Claude, OpenAI, or Ollama local).
Provider is selected via pipeline/config/llm_config.yaml.

Environment:
    TESTABILITY_THRESHOLD  — float 0.0–1.0, default 0.6. Utterances with
                             testability_score >= threshold AND speech_act_type
                             in (assertion, conditional, recall) are promoted to
                             prediction_ledger. Set to 0.0 for backward-compat
                             mode (everything promoted).

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
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

import pandas as pd
import yaml
from google.api_core.exceptions import NotFound
from google.cloud.bigquery import QueryJobConfig, ScalarQueryParameter
from src.cryptographic_ledger import PunditPrediction, ingest_batch
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

# ---------------------------------------------------------------------------
# Phase C — speech-act + testability constants
# ---------------------------------------------------------------------------

# Table name for the silver_v2_claims.raw_utterance write (Phase C)
RAW_UTTERANCE_DATASET = "silver_v2_claims"
RAW_UTTERANCE_TABLE = "raw_utterance"

# speech_act_types that are promoted to prediction_ledger when
# testability_score >= TESTABILITY_THRESHOLD.
PROMOTABLE_SPEECH_ACTS = frozenset({"assertion", "conditional", "recall"})

# All valid speech_act_type values (used for validation).
VALID_SPEECH_ACT_TYPES = frozenset(
    {
        "assertion",
        "conditional",
        "recall",
        "rhetorical_question",
        "hedge",
        "commentary",
        "opinion",
        "analogy",
        "joke",
    }
)

# Default testability threshold.  Override via env var TESTABILITY_THRESHOLD.
_DEFAULT_TESTABILITY_THRESHOLD = 0.6


def get_testability_threshold() -> float:
    """Return the runtime testability threshold from env (default 0.6)."""
    raw = os.environ.get("TESTABILITY_THRESHOLD", "")
    if raw.strip():
        try:
            val = float(raw.strip())
            if 0.0 <= val <= 1.0:
                return val
            logger.warning(
                f"TESTABILITY_THRESHOLD={val!r} out of range [0,1]; using default {_DEFAULT_TESTABILITY_THRESHOLD}"
            )
        except ValueError:
            logger.warning(
                f"TESTABILITY_THRESHOLD={raw!r} is not a float; using default {_DEFAULT_TESTABILITY_THRESHOLD}"
            )
    return _DEFAULT_TESTABILITY_THRESHOLD


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

EXTRACTION_PROMPT = """You are a {sport} speech-act extraction system. Analyze the content below and extract ALL speech acts — including rhetorical questions, hedges, and opinions — not just testable predictions.

PUBLISHED: {published_date}

For EACH utterance, classify it and score its testability. Return a JSON array where each element has:
{{
  "text": "verbatim quote or close paraphrase",
  "speech_act_type": "assertion|conditional|recall|rhetorical_question|hedge|commentary|opinion|analogy|joke",
  "testability_subscores": {{
    "subject_specificity": 0.0,
    "predicate_falsifiability": 0.0,
    "threshold_concreteness": 0.0,
    "resolution_horizon_defined": 0.0,
    "evidence_accessibility": 0.0
  }},
  "testability_score": 0.0,
  "resolution_horizon": "ISO8601 datetime or null",
  "predicate": "will_win|will_be_below|will_retire|will_sign|will_miss_playoffs|...",
  "subject": "entity name string",
  "predicate_args": {{}},
  "extracted_claim": "concise testable statement for ledger (or empty string if not testable)",
  "claim_category": "player_performance|game_outcome|trade|draft_pick|injury|contract|award_prediction|fa_signing",
  "stance": "bullish|bearish|neutral",
  "season_year": null,
  "target_player": null,
  "target_team": null,
  "confidence_note": "how explicit/confident the prediction is",
  "prediction_horizon_days": -1
}}

speech_act_type definitions:
- assertion: declarative claim about a future outcome ("Mahomes will win MVP")
- conditional: claim contingent on a condition ("IF they stay healthy, Eagles win the Super Bowl")
- recall: speaker recalls a past prediction or fact as evidence ("I said three months ago that...")
- rhetorical_question: question used for emphasis, not an assertion ("Can anyone stop this offense?")
- hedge: statement explicitly marked as uncertain ("I think he might...", "wouldn't surprise me if")
- commentary: analysis/explanation without a testable outcome ("This offense runs through the slot")
- opinion: subjective evaluation without falsifiable outcome ("He's the best QB in the league")
- analogy: comparison to illustrate a point, not a direct claim
- joke: humor, sarcasm

testability_score = average of 5 sub-scores (each 0.0–1.0):
- subject_specificity: Is the subject a nameable entity? "The Eagles"=1.0, "young QBs these days"=0.0
- predicate_falsifiability: Can it be scored TRUE/FALSE? "will win the SB"=1.0, "will struggle"=0.4
- threshold_concreteness: "below 3%"=1.0, "low"=0.3, "some"=0.0
- resolution_horizon_defined: "by Q4 2025"=1.0, "soon"=0.3, "eventually"=0.0
- evidence_accessibility: Is there a data source that can answer this? "Eagles wins >= 11"=1.0, "most exciting team"=0.0

Stance rules (for promoted claims):
- bullish: prediction is positive/optimistic about the subject
- bearish: prediction is negative/pessimistic about the subject
- neutral: no clear directional bias (retirement, trade, factual future event)

--- FEW-SHOT EXAMPLES ---

Example 1 — Rhetorical question (NOT promoted to ledger):
Input: "Can anyone stop Patrick Mahomes at this point?"
Output:
{{
  "text": "Can anyone stop Patrick Mahomes at this point?",
  "speech_act_type": "rhetorical_question",
  "testability_subscores": {{"subject_specificity": 1.0, "predicate_falsifiability": 0.1, "threshold_concreteness": 0.0, "resolution_horizon_defined": 0.0, "evidence_accessibility": 0.2}},
  "testability_score": 0.26,
  "resolution_horizon": null,
  "predicate": "",
  "subject": "Patrick Mahomes",
  "predicate_args": {{}},
  "extracted_claim": "",
  "claim_category": "player_performance",
  "stance": "bullish",
  "season_year": null,
  "target_player": "Patrick Mahomes",
  "target_team": "KC",
  "confidence_note": "rhetorical emphasis",
  "prediction_horizon_days": -1
}}

Example 2 — Genuine assertion (PROMOTED to ledger):
Input: "The Eagles will win at least 11 games this season."
Output:
{{
  "text": "The Eagles will win at least 11 games this season.",
  "speech_act_type": "assertion",
  "testability_subscores": {{"subject_specificity": 1.0, "predicate_falsifiability": 1.0, "threshold_concreteness": 1.0, "resolution_horizon_defined": 0.8, "evidence_accessibility": 1.0}},
  "testability_score": 0.96,
  "resolution_horizon": "2025-12-31T23:59:59Z",
  "predicate": "will_win_at_least",
  "subject": "Philadelphia Eagles",
  "predicate_args": {{"threshold": 11, "stat": "wins", "unit": "games"}},
  "extracted_claim": "Eagles will win at least 11 games in the 2025 season",
  "claim_category": "game_outcome",
  "stance": "bullish",
  "season_year": 2025,
  "target_player": null,
  "target_team": "PHI",
  "confidence_note": "explicit numeric threshold",
  "prediction_horizon_days": 150
}}

Example 3 — Conditional (PROMOTED to ledger):
Input: "If their offensive line stays healthy, the Ravens will reach the AFC Championship."
Output:
{{
  "text": "If their offensive line stays healthy, the Ravens will reach the AFC Championship.",
  "speech_act_type": "conditional",
  "testability_subscores": {{"subject_specificity": 1.0, "predicate_falsifiability": 0.9, "threshold_concreteness": 0.7, "resolution_horizon_defined": 0.8, "evidence_accessibility": 1.0}},
  "testability_score": 0.88,
  "resolution_horizon": "2025-12-31T23:59:59Z",
  "predicate": "will_reach",
  "subject": "Baltimore Ravens",
  "predicate_args": {{"milestone": "AFC Championship", "condition": "offensive line stays healthy"}},
  "extracted_claim": "Ravens will reach the AFC Championship (conditional on OL health)",
  "claim_category": "game_outcome",
  "stance": "bullish",
  "season_year": 2025,
  "target_player": null,
  "target_team": "BAL",
  "confidence_note": "conditional on OL health",
  "prediction_horizon_days": 120
}}

--- END EXAMPLES ---

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
    # Phase C: all extracted utterances (before testability filter)
    utterances: list[dict] = None

    def __post_init__(self):
        if self.utterances is None:
            self.utterances = []


def compute_testability_score(subscores: dict) -> float:
    """
    Compute a testability_score as the mean of the 5 required sub-scores.
    Each sub-score must be 0.0–1.0. If any sub-score is missing, it defaults
    to 0.0 so the average is penalised appropriately.
    """
    keys = [
        "subject_specificity",
        "predicate_falsifiability",
        "threshold_concreteness",
        "resolution_horizon_defined",
        "evidence_accessibility",
    ]
    if not subscores:
        return 0.0
    values = []
    for k in keys:
        raw = subscores.get(k, 0.0)
        try:
            v = float(raw)
        except (TypeError, ValueError):
            v = 0.0
        values.append(max(0.0, min(1.0, v)))
    return round(sum(values) / len(values), 4)


def _is_promotable(utterance: dict, threshold: float) -> bool:
    """
    Return True if an utterance should be promoted to prediction_ledger.
    Conditions:
      - speech_act_type in PROMOTABLE_SPEECH_ACTS (assertion, conditional, recall)
      - testability_score >= threshold
      - extracted_claim is non-empty

    Backward compatibility: if speech_act_type is absent (legacy LLM response format
    without Phase C fields), it defaults to "assertion" so old responses continue to
    be promoted.  Similarly, if testability_score is absent the response predates
    Phase C scoring and is treated as fully testable (score=1.0) to avoid silently
    dropping legitimate legacy predictions.
    """
    sat = utterance.get("speech_act_type") or "assertion"
    # If testability_score is explicitly present (including 0.0), use it.
    # If absent entirely (legacy format), default to 1.0 to maintain backward compat.
    score_raw = utterance.get("testability_score")
    score = 1.0 if score_raw is None else float(score_raw)
    claim = utterance.get("extracted_claim", "")
    return sat in PROMOTABLE_SPEECH_ACTS and score >= threshold and bool(claim.strip())


def _resolve_speaker_entity_id(pundit_id: str, db: Optional["DBManager"] = None) -> str:
    """
    Resolve a pundit_id to a silver_v2_core.entity_id.
    Attempts a BigQuery lookup by external_ids or alias.
    On any failure, returns the placeholder "UNRESOLVED:{pundit_id}".
    """
    if db is None:
        return f"UNRESOLVED:{pundit_id}"
    project_id = os.environ.get("GCP_PROJECT_ID", "")
    if not project_id:
        return f"UNRESOLVED:{pundit_id}"
    try:
        query = f"""
            SELECT entity_id
            FROM `{project_id}.silver_v2_core.entity`
            WHERE JSON_EXTRACT_SCALAR(external_ids, '$.pundit_id') = @pundit_id
               OR entity_id = @pundit_id
            LIMIT 1
        """
        from google.cloud.bigquery import ScalarQueryParameter as SQP

        row = db.fetch_df(
            query,
            query_parameters=[SQP("pundit_id", "STRING", pundit_id)],
        )
        if not row.empty:
            return str(row.iloc[0]["entity_id"])
    except Exception as exc:
        logger.debug(f"Entity lookup failed for pundit_id={pundit_id!r}: {exc}")
    return f"UNRESOLVED:{pundit_id}"


def write_raw_utterances(
    utterances: list[dict],
    source_doc_id: str,
    speaker_entity_id: str,
    uttered_at: datetime,
    domain: str,
    db: "DBManager",
) -> int:
    """
    Write all utterances to silver_v2_claims.raw_utterance.
    Returns the number of rows written.

    Each row maps the Phase C LLM output to the migration 016 schema:
      utterance_id, source_doc_id, speaker_entity_id, uttered_at, text,
      speech_act_type, testability_score, resolution_horizon, domain,
      extraction_confidence, created_at
    """
    if not utterances:
        return 0

    now = datetime.now(timezone.utc)
    rows = []
    for u in utterances:
        # Ensure testability_score is the recomputed value if subscores present
        subscores = u.get("testability_subscores") or {}
        if subscores:
            score = compute_testability_score(subscores)
        else:
            raw_score = u.get("testability_score", 0.0)
            try:
                score = float(raw_score)
            except (TypeError, ValueError):
                score = 0.0

        sat = u.get("speech_act_type", "commentary")
        if sat not in VALID_SPEECH_ACT_TYPES:
            sat = "commentary"

        # resolution_horizon: BQ column type is TIMESTAMP (nullable).
        # Keep as string/None here; pd.to_datetime below does the final coercion.
        # Flatten dicts/lists to None — they can't represent a datetime.
        rh = u.get("resolution_horizon")
        if isinstance(rh, (dict, list, bool)):
            rh = None

        rows.append(
            {
                "utterance_id": str(uuid.uuid4()),
                "source_doc_id": source_doc_id,
                "speaker_entity_id": speaker_entity_id,
                "uttered_at": uttered_at,
                "text": str(u.get("text", ""))[:4000],
                "speech_act_type": sat,
                "testability_score": score,
                "resolution_horizon": rh,
                "domain": domain,
                "extraction_confidence": max(
                    0.0, min(1.0, float(u.get("extraction_confidence", score)))
                ),
                "created_at": now,
            }
        )

    # NOT-NULL invariant — fail fast before any BQ I/O (#595)
    _NULL_CHECKED_COLS = (
        "speech_act_type",
        "testability_score",
        "domain",
        "extraction_confidence",
    )
    _null_violations: list[str] = []
    for _row in rows:
        for _col in _NULL_CHECKED_COLS:
            if _row.get(_col) is None:
                _null_violations.append(_col)
    if _null_violations:
        raise ValueError(
            f"write_raw_utterances: NOT NULL invariant violated — "
            f"columns: {sorted(set(_null_violations))}. "
            "Refusing to write batch with NULL metadata."
        )

    df = pd.DataFrame(rows)

    # BQ schema: resolution_horizon is TIMESTAMP (nullable).
    # Convert string/None values to datetime64[ns, UTC] so pyarrow can serialize
    # them as TIMESTAMP.  errors="coerce" turns unparseable strings into NaT
    # (which becomes NULL in BQ).  An "object" dtype column of strings cannot
    # be serialized to TIMESTAMP by pyarrow — this pd.to_datetime call is the
    # fix for the "Array, ListArray, or StructArray" pyarrow error.
    df["resolution_horizon"] = pd.to_datetime(
        df["resolution_horizon"], utc=True, errors="coerce"
    )

    # Use qualified table name: write to silver_v2_claims dataset
    full_table = f"{RAW_UTTERANCE_DATASET}.{RAW_UTTERANCE_TABLE}"
    try:
        # Directly use client with full project.dataset.table reference
        project_id = os.environ.get("GCP_PROJECT_ID", "")
        table_ref = f"{project_id}.{full_table}"
        job_config = __import__(
            "google.cloud.bigquery", fromlist=["LoadJobConfig"]
        ).LoadJobConfig(write_disposition="WRITE_APPEND")
        df_clean = df.copy()
        # Cast remaining object-dtype cols to str for BQ Parquet compatibility.
        # datetime64 columns (uttered_at, created_at, resolution_horizon) are
        # not "object" dtype and are skipped automatically.
        for col in df_clean.columns:
            if df_clean[col].dtype == object:
                df_clean[col] = df_clean[col].astype(str)
        job = db.client.load_table_from_dataframe(
            df_clean, table_ref, job_config=job_config
        )
        job.result()
        logger.info(f"Wrote {len(rows)} raw_utterance rows to {table_ref}")
    except Exception as exc:
        logger.warning(
            f"Failed to write raw_utterances to {full_table}: {exc} — continuing"
        )
        return 0
    return len(rows)


def _write_extraction_run(
    run_id: str,
    started_at: datetime,
    finished_at: Optional[datetime],
    provider: str,
    model: str,
    prompt_version: Optional[str],
    articles_processed: int,
    utterances_written: int,
    claims_promoted: int,
    suppressed: int,
    errors: int,
    mean_testability_score: Optional[float],
    metadata_completeness_pct: Optional[float],
    db: "DBManager",
) -> None:
    """Write one row to silver_v2_claims.extraction_run for observability / alerting."""
    git_sha = os.environ.get("GITHUB_SHA")
    server_url = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    gh_run_id = os.environ.get("GITHUB_RUN_ID")
    workflow_run_url = (
        f"{server_url}/{repository}/actions/runs/{gh_run_id}"
        if gh_run_id and repository
        else None
    )

    row = {
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": finished_at,
        "provider": provider,
        "model": model,
        "prompt_version": prompt_version,
        "articles_processed": articles_processed,
        "utterances_written": utterances_written,
        "claims_promoted": claims_promoted,
        "suppressed": suppressed,
        "errors": errors,
        "mean_testability_score": mean_testability_score,
        "metadata_completeness_pct": metadata_completeness_pct,
        "git_sha": git_sha,
        "workflow_run_url": workflow_run_url,
    }

    try:
        df = pd.DataFrame([row])
        project_id = os.environ.get("GCP_PROJECT_ID", "")
        table_ref = f"{project_id}.silver_v2_claims.extraction_run"
        job_config = __import__(
            "google.cloud.bigquery", fromlist=["LoadJobConfig"]
        ).LoadJobConfig(write_disposition="WRITE_APPEND")
        df_clean = df.copy()
        for col in df_clean.columns:
            if df_clean[col].dtype == object:
                df_clean[col] = df_clean[col].astype(str)
        job = db.client.load_table_from_dataframe(
            df_clean, table_ref, job_config=job_config
        )
        job.result()
        logger.info(f"Wrote extraction_run row: run_id={run_id}")
    except Exception as exc:
        logger.warning(f"Failed to write extraction_run row (non-fatal): {exc}")


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
        all_utterances = _call_provider()

        # Phase C: recompute testability_score from subscores when available
        # (LLM may drift; we own the formula).
        for u in all_utterances:
            subscores = u.get("testability_subscores") or {}
            if subscores:
                u["testability_score"] = compute_testability_score(subscores)

        threshold = get_testability_threshold()

        # Phase C: separate ALL utterances (for raw_utterance write) from
        # PROMOTED ones (for prediction_ledger).  An utterance is promoted if:
        #   - speech_act_type in (assertion, conditional, recall)
        #   - testability_score >= threshold
        #   - extracted_claim is non-empty
        promoted = [u for u in all_utterances if _is_promotable(u, threshold)]

        suppressed_count = len(all_utterances) - len(promoted)
        if suppressed_count > 0:
            logger.info(
                f"Speech-act filter: {suppressed_count} utterance(s) suppressed "
                f"(rhetorical/hedge/etc. or testability_score < {threshold})"
            )

        # Hard temporal filter on promoted claims: reject past-season claims.
        # Bypassed with allow_historical=True for backfill runs.
        current_year = datetime.now().year
        filtered = []
        for p in promoted:
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

        logger.info(
            f"Extraction: {len(all_utterances)} utterance(s) extracted, "
            f"{len(deduped)} promoted to ledger "
            f"(testability_score >= {threshold}), "
            f"{suppressed_count} suppressed (rhetorical/hedge/etc.)"
        )

        return ExtractionResult(
            content_hash=content_hash,
            predictions=deduped,
            utterances=all_utterances,
        )
    except Exception as e:
        return ExtractionResult(
            content_hash=content_hash,
            predictions=[],
            utterances=[],
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
    Main extraction entry point (Phase C).

    1. Fetch unprocessed raw media from BQ
    2. Send each to LLM for speech-act + testability extraction
    3. Write ALL utterances to silver_v2_claims.raw_utterance (Phase C)
    4. Promote qualifying utterances to PunditPredictions for ledger
    5. Ingest into the cryptographic ledger
    6. Mark as processed

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

    threshold = get_testability_threshold()

    # Extraction run provenance — recorded in extraction_run table via try/finally
    _run_id = str(uuid.uuid4())
    _run_started_at = datetime.now(timezone.utc)
    _run_provider = (
        type(provider).__name__.replace("Provider", "").lower()
        if provider
        else "dry-run"
    )
    _run_model = getattr(provider, "model", "unknown") if provider else "dry-run"
    _run_testability_scores: list[float] = []
    _run_metadata_complete = 0
    _run_metadata_total = 0

    summary = {
        "total_processed": 0,
        "predictions_extracted": 0,
        "predictions_ingested": 0,
        "utterances_written": 0,
        "suppressed": 0,
        "errors": 0,
        "skipped_no_predictions": 0,
        "filtered_out": 0,
        "skipped_low_yield": 0,
        "testability_threshold": threshold,
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

            # Phase C: write ALL utterances to raw_utterance regardless of
            # whether they are promotable — this is the full audit trail.
            pundit_id = row.get("matched_pundit_id") or "unknown"
            pundit_name = row.get("matched_pundit_name") or str(
                row.get("author", "Unknown")
            )
            source_url = str(row.get("source_url", ""))

            if result.utterances:
                uttered_at = (
                    pd.Timestamp(row["published_at"]).to_pydatetime()
                    if pd.notna(row.get("published_at"))
                    else datetime.now(timezone.utc)
                )
                # Resolve speaker entity_id (best-effort; placeholder on miss)
                speaker_entity_id = _resolve_speaker_entity_id(str(pundit_id), db=db)
                article_sport = str(row.get("sport", sport))
                written = write_raw_utterances(
                    utterances=result.utterances,
                    source_doc_id=content_hash,
                    speaker_entity_id=speaker_entity_id,
                    uttered_at=uttered_at,
                    domain=article_sport.lower(),
                    db=db,
                )
                summary["utterances_written"] += written
                suppressed_here = len(result.utterances) - len(result.predictions)
                summary["suppressed"] += max(0, suppressed_here)

                # Accumulate per-run metrics for extraction_run table
                for u in result.utterances:
                    _run_metadata_total += 1
                    ts = u.get("testability_score")
                    ec = u.get("extraction_confidence")
                    sat = u.get("speech_act_type") or ""
                    if ts is not None:
                        try:
                            _run_testability_scores.append(float(ts))
                        except (TypeError, ValueError):
                            pass
                    if bool(sat) and ts is not None and ec is not None:
                        _run_metadata_complete += 1

            if not result.predictions:
                summary["skipped_no_predictions"] += 1
                processed_hashes.append(content_hash)
                continue

            summary["predictions_extracted"] += len(result.predictions)

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
                        prompt_version=PROMPT_VERSION,
                        llm_provider=provider_type,
                        llm_model=str(llm_model) if llm_model else None,
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
            f"{summary['utterances_written']} utterances → raw_utterance, "
            f"{summary['predictions_extracted']} promoted to ledger "
            f"(testability_score >= {threshold}), "
            f"{summary['suppressed']} suppressed (rhetorical/hedge/etc.), "
            f"{summary['predictions_ingested']} ingested, "
            f"{summary['skipped_low_yield']} skipped (low-yield source), "
            f"{summary['errors']} errors"
        )
        return summary
    finally:
        # Write extraction_run row regardless of success/failure (not in dry_run mode)
        if not dry_run:
            _finished_at = datetime.now(timezone.utc)
            _mean_ts = (
                sum(_run_testability_scores) / len(_run_testability_scores)
                if _run_testability_scores
                else None
            )
            _meta_pct = (
                100.0 * _run_metadata_complete / _run_metadata_total
                if _run_metadata_total > 0
                else None
            )
            _write_extraction_run(
                run_id=_run_id,
                started_at=_run_started_at,
                finished_at=_finished_at,
                provider=_run_provider,
                model=_run_model,
                prompt_version=PROMPT_VERSION,
                articles_processed=summary["total_processed"],
                utterances_written=summary["utterances_written"],
                claims_promoted=summary["predictions_ingested"],
                suppressed=summary["suppressed"],
                errors=summary["errors"],
                mean_testability_score=_mean_ts,
                metadata_completeness_pct=_meta_pct,
                db=db,
            )
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
