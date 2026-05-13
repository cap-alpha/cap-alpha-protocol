"""
promote_claims.py — promote qualifying raw_utterances to silver_v2_claims.claim

Promotion criteria (per migration 016):
  speech_act_type IN ('assertion', 'conditional', 'recall')
  AND testability_score >= 0.6

Idempotent: claim_id is a UUIDv5 derived from utterance_id, so repeated runs
produce the same claim_id and the skip-if-exists guard prevents duplicates.

Usage:
    from src.promote_claims import promote_utterances_to_claims
    n = promote_utterances_to_claims()          # promote all qualifying
    n = promote_utterances_to_claims(["uid1"])  # promote specific utterance IDs
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import pandas as pd

from src.db_manager import get_db_manager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# speech_act_type values that qualify for promotion
_QUALIFYING_SPEECH_ACTS = frozenset(["assertion", "conditional", "recall"])

# Minimum testability_score threshold
_TESTABILITY_THRESHOLD = 0.6

# UUID v5 namespace for deterministic claim_id generation
_CLAIM_NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # URL namespace

# Fallback resolution method ID when no domain-specific one is found
_FALLBACK_RESOLUTION_METHOD_ID = "nfl_game_outcome_scores"

# Predicate pattern table: list of (compiled_regex, predicate_slug)
_PREDICATE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bwill\s+(win|take|capture|clinch)\b", re.I), "will_win"),
    (re.compile(r"\bwill\s+(lose|fall|drop)\b", re.I), "will_lose"),
    (re.compile(r"\bwill\s+retire\b", re.I), "will_retire"),
    (re.compile(r"\bwill\s+sign\b", re.I), "will_sign"),
    (re.compile(r"\bwill\s+be\s+drafted\b", re.I), "will_be_drafted"),
    (re.compile(r"\bwill\s+be\s+traded\b", re.I), "will_be_traded"),
    (re.compile(r"\bwill\s+be\s+cut\b", re.I), "will_be_cut"),
    (re.compile(r"\bwill\s+be\s+released\b", re.I), "will_be_cut"),
    (re.compile(r"\bwill\s+exceed\b", re.I), "will_exceed"),
    (re.compile(r"\bwill\s+(?:be\s+)?below\b", re.I), "will_be_below"),
    (re.compile(r"\bwill\s+(?:be\s+)?above\b", re.I), "will_exceed"),
    (re.compile(r"\bwill\s+make\b", re.I), "will_occur"),
    (re.compile(r"\bwill\s+not\s+run\b", re.I), "will_not_occur"),
    (re.compile(r"\bwill\s+not\b", re.I), "will_not_occur"),
    (re.compile(r"\bwill\s+be\s+(?:the|a|an)\b", re.I), "will_occur"),
    (re.compile(r"\bwill\b", re.I), "will_occur"),  # catch-all for any remaining "will"
]

# Domain → preferred resolution_method_id prefix mapping
_DOMAIN_RESOLUTION_PREFIXES: dict[str, list[str]] = {
    "sports.nfl": ["nfl_", "sports_nfl_"],
    "sports": ["nfl_", "sports_"],
    "politics.us": ["us_politics_", "politics_"],
    "politics": ["politics_"],
    "finance": ["finance_", "market_"],
    "tech": ["tech_", "market_"],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _derive_claim_id(utterance_id: str) -> str:
    """Return a deterministic UUIDv5 claim_id from an utterance_id."""
    return str(uuid.uuid5(_CLAIM_NS, utterance_id))


def _infer_predicate(text: str) -> str:
    """
    Derive a normalized predicate slug from the utterance text.

    Applies the pattern table in order and returns the first match.
    Falls back to 'will_occur' if no pattern matches.
    """
    for pattern, slug in _PREDICATE_PATTERNS:
        if pattern.search(text):
            return slug
    return "will_occur"


def _extract_subject_entity_ids(target_entity_raw) -> list[str]:
    """
    Extract entity IDs from the target_entity JSON value.

    target_entity may be stored as a Python dict, a JSON string, or None.
    Returns a list of entity_id strings extracted from the JSON.
    """
    if target_entity_raw is None:
        return []

    try:
        if isinstance(target_entity_raw, str):
            if not target_entity_raw.strip():
                return []
            data = json.loads(target_entity_raw)
        elif isinstance(target_entity_raw, dict):
            data = target_entity_raw
        else:
            return []

        ids = []
        # Single entity: {"entity_id": "..."}
        if isinstance(data, dict):
            eid = data.get("entity_id")
            if eid:
                ids.append(str(eid))
            # Sometimes nested: {"entities": [{"entity_id": "..."}, ...]}
            nested = data.get("entities", [])
            if isinstance(nested, list):
                for item in nested:
                    if isinstance(item, dict) and item.get("entity_id"):
                        ids.append(str(item["entity_id"]))
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and item.get("entity_id"):
                    ids.append(str(item["entity_id"]))

        return ids
    except (json.JSONDecodeError, TypeError, AttributeError):
        return []


def _infer_claim_subject_type(target_entity_raw) -> str:
    """
    Return 'entity' if target_entity JSON contains an entity_id, else 'aggregate'.
    """
    ids = _extract_subject_entity_ids(target_entity_raw)
    return "entity" if ids else "aggregate"


def _compute_this_hash(row: dict) -> str:
    """
    Compute SHA-256 of the canonical JSON of a claim row (sorted keys, ISO timestamps).

    Only hashes the content fields (not created_at or this_hash itself).
    """
    payload = {
        k: v for k, v in sorted(row.items()) if k not in ("this_hash", "created_at")
    }

    # Normalise timestamps to ISO-8601 strings so the hash is reproducible
    def _normalise(val):
        # Guard against pandas NaT (which passes isinstance(_, datetime) checks)
        try:
            import pandas as _pd

            if val is _pd.NaT:
                return None
        except Exception:
            pass
        if isinstance(val, datetime):
            if getattr(val, "tzinfo", None) is None:
                val = val.replace(tzinfo=timezone.utc)
            return val.astimezone(timezone.utc).isoformat()
        if isinstance(val, list):
            return [_normalise(v) for v in val]
        if isinstance(val, dict):
            return {k2: _normalise(v2) for k2, v2 in sorted(val.items())}
        return val

    normalised = {k: _normalise(v) for k, v in payload.items()}
    canonical = json.dumps(normalised, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _pick_resolution_method_id(domain: str, available_methods: dict[str, str]) -> str:
    """
    Pick the best resolution_method_id for the given domain.

    available_methods: {resolution_method_id → domain}

    Priority: domain-prefix match > parent-domain-prefix match > fallback.
    """
    # Build domain-to-prefix preference list
    prefixes = _DOMAIN_RESOLUTION_PREFIXES.get(domain, [])
    # Also try parent domains (e.g. "sports.nfl" → try "sports" too)
    parts = domain.split(".")
    while len(parts) > 1:
        parts.pop()
        parent = ".".join(parts)
        prefixes.extend(_DOMAIN_RESOLUTION_PREFIXES.get(parent, []))

    for prefix in prefixes:
        for method_id in available_methods:
            if method_id.startswith(prefix):
                return method_id

    # If any method exists for the exact domain, use that
    for method_id, method_domain in available_methods.items():
        if method_domain == domain:
            return method_id

    # Last resort: return the fallback if present, else first available, else hardcoded constant
    if _FALLBACK_RESOLUTION_METHOD_ID in available_methods:
        return _FALLBACK_RESOLUTION_METHOD_ID
    if available_methods:
        return next(iter(available_methods))
    return _FALLBACK_RESOLUTION_METHOD_ID


def _build_claim_rows(
    utterances_df: pd.DataFrame,
    existing_claim_ids: set[str],
    available_methods: dict[str, str],
) -> list[dict]:
    """
    Build claim row dicts for all qualifying utterances not already promoted.

    Returns only rows whose claim_id is not in existing_claim_ids.
    """
    now = datetime.now(timezone.utc)
    rows: list[dict] = []

    for _, utt in utterances_df.iterrows():
        utterance_id = str(utt["utterance_id"])
        claim_id = _derive_claim_id(utterance_id)

        if claim_id in existing_claim_ids:
            continue

        uttered_at = utt["uttered_at"]
        # Convert pandas Timestamp or NaT-safe path
        if uttered_at is pd.NaT or (
            isinstance(uttered_at, float) and pd.isna(uttered_at)
        ):
            # Should not happen (uttered_at is NOT NULL), but guard defensively
            uttered_at = datetime.now(timezone.utc)
        if isinstance(uttered_at, str):
            uttered_at = datetime.fromisoformat(uttered_at)
        # tz-localise tz-naive timestamps (pandas returns naive UTC for DuckDB TIMESTAMP cols)
        if hasattr(uttered_at, "tzinfo") and uttered_at.tzinfo is None:
            if hasattr(uttered_at, "tz_localize"):
                # pandas Timestamp
                uttered_at = uttered_at.tz_localize("UTC").to_pydatetime()
            else:
                uttered_at = uttered_at.replace(tzinfo=timezone.utc)

        # resolution_window_end: COALESCE(resolution_horizon, uttered_at + 365 days)
        resolution_horizon = utt.get("resolution_horizon")
        # Guard against pandas NaT (passes 'is not None' check)
        _rh_is_null = (
            resolution_horizon is None
            or resolution_horizon is pd.NaT
            or (isinstance(resolution_horizon, float) and pd.isna(resolution_horizon))
        )
        if not _rh_is_null:
            if isinstance(resolution_horizon, str):
                resolution_horizon = datetime.fromisoformat(resolution_horizon)
            if (
                hasattr(resolution_horizon, "tz_localize")
                and resolution_horizon.tzinfo is None
            ):
                resolution_horizon = resolution_horizon.tz_localize(
                    "UTC"
                ).to_pydatetime()
            elif (
                isinstance(resolution_horizon, datetime)
                and resolution_horizon.tzinfo is None
            ):
                resolution_horizon = resolution_horizon.replace(tzinfo=timezone.utc)
            window_end = resolution_horizon
        else:
            window_end = uttered_at + timedelta(days=365)

        domain = str(utt["domain"])
        text = str(utt["text"])
        target_entity_raw = utt.get("target_entity")

        subject_entity_ids = _extract_subject_entity_ids(target_entity_raw)
        claim_subject_type = "entity" if subject_entity_ids else "aggregate"
        predicate = _infer_predicate(text)
        predicate_args = json.dumps({"raw_text": text})
        resolution_method_id = _pick_resolution_method_id(domain, available_methods)

        row = {
            "claim_id": claim_id,
            "utterance_id": utterance_id,
            "speaker_entity_id": str(utt["speaker_entity_id"]),
            "domain": domain,
            "claim_subject_type": claim_subject_type,
            "subject_entity_ids": subject_entity_ids,
            "subject_metric": None,
            "predicate": predicate,
            "predicate_args": predicate_args,
            "resolution_window_start": uttered_at,
            "resolution_window_end": window_end,
            "resolution_method_id": resolution_method_id,
            "asserted_at": uttered_at,
            "ledger_locked_at": now,
            "prior_claim_id": None,
            "prev_hash": "",
            "created_at": now,
        }

        # Compute this_hash after all other fields are populated
        row["this_hash"] = _compute_this_hash(row)
        rows.append(row)

    return rows


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def promote_utterances_to_claims(
    utterance_ids: Optional[List[str]] = None,
    db=None,
) -> int:
    """
    Promote qualifying raw_utterance rows to silver_v2_claims.claim.

    Args:
        utterance_ids: Optional list of specific utterance_ids to promote.
                       If None, all qualifying utterances are candidates.
        db: Optional DB manager (injected for testing). If None, uses get_db_manager().

    Returns:
        Count of newly inserted claim rows.
    """
    if db is None:
        db = get_db_manager()

    # 1. Fetch qualifying utterances
    if utterance_ids is not None:
        # Filter to only the provided IDs, still applying qualifying criteria
        placeholders = ", ".join(f"'{uid}'" for uid in utterance_ids)
        utterance_filter = (
            f"AND utterance_id IN ({placeholders})" if placeholders else "AND 1=0"
        )
    else:
        utterance_filter = ""

    utterance_query = f"""
        SELECT
            utterance_id,
            speaker_entity_id,
            uttered_at,
            text,
            speech_act_type,
            testability_score,
            resolution_horizon,
            domain,
            target_entity
        FROM silver_v2_claims.raw_utterance
        WHERE speech_act_type IN ('assertion', 'conditional', 'recall')
          AND testability_score >= {_TESTABILITY_THRESHOLD}
          {utterance_filter}
    """

    logger.info("Fetching qualifying utterances...")
    utterances_df = db.fetch_df(utterance_query)
    logger.info("Found %d qualifying utterances", len(utterances_df))

    if utterances_df.empty:
        logger.info("No qualifying utterances to promote.")
        return 0

    # 2. Fetch existing claim_ids to enable idempotency check
    existing_query = "SELECT claim_id FROM silver_v2_claims.claim"
    existing_df = db.fetch_df(existing_query)
    existing_claim_ids: set[str] = (
        set(existing_df["claim_id"].tolist()) if not existing_df.empty else set()
    )
    logger.info("Existing claim rows: %d", len(existing_claim_ids))

    # 3. Fetch available resolution methods
    methods_query = (
        "SELECT resolution_method_id, domain FROM silver_v2_claims.resolution_method"
    )
    methods_df = db.fetch_df(methods_query)
    available_methods: dict[str, str] = {}
    if not methods_df.empty:
        available_methods = dict(
            zip(methods_df["resolution_method_id"], methods_df["domain"])
        )
    logger.info("Available resolution methods: %d", len(available_methods))

    # 4. Build new claim rows (skip already-existing claim_ids)
    new_rows = _build_claim_rows(utterances_df, existing_claim_ids, available_methods)
    logger.info(
        "New claims to write: %d (skipping %d already promoted)",
        len(new_rows),
        len(utterances_df) - len(new_rows),
    )

    if not new_rows:
        logger.info("All qualifying utterances already promoted.")
        return 0

    # 5. Insert all rows via single executemany via append_dataframe_to_table
    claims_df = pd.DataFrame(new_rows)

    # Ensure correct dtypes for TIMESTAMP columns
    for ts_col in (
        "resolution_window_start",
        "resolution_window_end",
        "asserted_at",
        "ledger_locked_at",
        "created_at",
    ):
        if ts_col in claims_df.columns:
            claims_df[ts_col] = pd.to_datetime(claims_df[ts_col], utc=True)

    db.append_dataframe_to_table(claims_df, "silver_v2_claims.claim")
    logger.info("Inserted %d new claim rows into silver_v2_claims.claim", len(new_rows))

    return len(new_rows)
