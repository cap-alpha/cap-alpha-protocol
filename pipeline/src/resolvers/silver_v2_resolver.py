"""
silver_v2 resolver — deterministic write/selection plumbing (Issue #1129 Slice 1)

Plan: https://github.com/cap-alpha/cap-alpha-protocol/issues/1129#issuecomment-5098662266
("Resolver cutover — implementation plan", Slice 1 — Foundation).

`silver_v2_claims.resolution` has 0 rows today. That is the blocker for the
whole product's accuracy ranking (see the read-path cutover audit on #1129):
no leaderboard/correct-incorrect/Brier score can be computed from silver_v2
until claims actually get resolutions. This module is the foundation that
lets a resolution method (Slice 2: an LLM judge; later slices: rule-based
adapters) plug in and write real, chained resolutions.

Provides:
  - select_due_claims()  — find claims whose resolution window has closed,
                            are not already resolved, and aren't scheduled
                            for a later check.
  - write_resolution()   — idempotent, hash-chained insert into
                            silver_v2_claims.resolution + a matching
                            silver_v2_claims.claim_state_history row.
  - ResolutionMethod      — the pluggable seam. A Protocol so Slice 2's LLM
                            judge (and later rule-based adapters) can drop in
                            without touching this module.
  - NoopResolutionMethod  — the only method registered in this slice. Always
                            defers (returns None = "no verdict yet"). Exists
                            so run_resolution_pass() has something to execute
                            end-to-end without any LLM/evidence dependency.
  - run_resolution_pass() — orchestration: select due claims, run a method
                            over them, write verdicts.

Hash chaining: this_hash is computed via `cryptographic_ledger.compute_chain_hash`
(imported, not reinvented) — see `_canonical_content_hash` docstring below for
the two-step design (canonicalize content locally, chain-link via the shared
helper). prev_hash is the claim's own this_hash for a claim's first
resolution, or the prior resolution's this_hash if one somehow already exists
(defensive; Slice 1's idempotency guard means a claim only ever gets one
resolution written here, but this keeps the chain correct if a future
revision slice legitimately writes a second resolution for the same claim —
the resolution table schema explicitly allows that: "Multiple resolutions
per claim are allowed when outcome changes").

Explicitly OUT OF SCOPE for this module (see the Slice 1 plan comment):
  - Any LLM call, news/evidence retrieval, or news-matching funnel (Slice 2 /
    #1133). NoopResolutionMethod always returns None.
  - Changes to the existing gold-layer resolvers (`resolve_daily.py`,
    `resolvers/llm_judge.py`, `resolution_engine.py`, `accountability_engine`).
    This module writes ONLY to silver_v2_claims.* and never touches
    gold_layer.*.
  - Wiring into any scheduled workflow/pipeline. Nothing here is called from
    run_daily.py or any GitHub Actions workflow yet — that's a follow-up once
    a real ResolutionMethod exists.
  - API changes.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional, Protocol

import pandas as pd
from google.cloud import bigquery

from src.cryptographic_ledger import compute_chain_hash

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Table references (bare dataset.table, no project/backtick qualification —
# matches promote_claims.py's convention so the same query text runs
# unchanged against BigQuery (default-dataset resolution finds the project
# from the query's own job) and against a DuckDB test double).
# ---------------------------------------------------------------------------

CLAIM_TABLE = "silver_v2_claims.claim"
RESOLUTION_TABLE = "silver_v2_claims.resolution"
STATE_HISTORY_TABLE = "silver_v2_claims.claim_state_history"
RESOLUTION_METHOD_TABLE = "silver_v2_claims.resolution_method"
RAW_UTTERANCE_TABLE = "silver_v2_claims.raw_utterance"
CLAIM_ENTITY_LINK_TABLE = "silver_v2_claims.claim_entity_link"
ENTITY_CURRENT_VIEW = "silver_v2_core.entity_current"

# entity_current is an EAV snapshot (silver_v2_core.entity_attribute_event,
# `valid_to IS NULL`), not a flat name column. `legal_name` is the attr this
# module reads for display purposes only (claim/speaker context handed to a
# ResolutionMethod) — it is best-effort and LEFT JOINed, so a missing name
# never blocks due-selection.
ENTITY_NAME_ATTR = "legal_name"

# outcome (silver_v2_claims.resolution.outcome) -> claim_state_history.state
# outcome vocabulary per migration 016: true|false|partial|unresolvable|vacuous
# state vocabulary per migration 028: PENDING|VOID|CORRECT|INCORRECT|PARTIAL|UNVERIFIABLE
_OUTCOME_TO_STATE: dict[str, str] = {
    "true": "CORRECT",
    "false": "INCORRECT",
    "partial": "PARTIAL",
    "unresolvable": "UNVERIFIABLE",
    "vacuous": "VOID",
}

# The only resolution_method registered by this slice — a deliberate no-op so
# run_resolution_pass() is exercisable end-to-end without any LLM dependency.
NOOP_METHOD_ID = "manual_noop"
NOOP_METHOD_DOMAIN = "general"
NOOP_METHOD_NAME = "Manual / No-Op (Slice 1 placeholder)"
NOOP_METHOD_ADAPTER_PATH = (
    "pipeline.src.resolvers.silver_v2_resolver:NoopResolutionMethod"
)
NOOP_METHOD_DATA_SOURCE = "manual"


# ---------------------------------------------------------------------------
# now-handling
# ---------------------------------------------------------------------------


def _resolve_now(now: Optional[datetime]) -> datetime:
    """
    Normalise the caller-injected `now` to tz-aware UTC, or wall-clock UTC
    when not provided.

    Requiring tz-awareness (rather than silently assuming UTC on a naive
    datetime) is deliberate: TIMESTAMP columns here are true UTC instants,
    and a naive datetime compared against them is a common source of
    off-by-however-many-hours bugs. Fail loudly instead.
    """
    if now is None:
        return datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError(
            "silver_v2_resolver: `now` must be timezone-aware (UTC) when provided"
        )
    return now.astimezone(timezone.utc)


# ---------------------------------------------------------------------------
# Due-claim selection
# ---------------------------------------------------------------------------


def select_due_claims(
    db: Any, limit: int = 50, now: Optional[datetime] = None
) -> list[dict]:
    """
    Return up to `limit` claims that are due for a resolution check.

    Due = resolution_window_end < now
          AND (next_check_at IS NULL OR next_check_at <= now)
          AND claim_id has no row in silver_v2_claims.resolution

    `now` defaults to the database's own CURRENT_TIMESTAMP() when not
    provided (avoids clock skew between the caller's process and the
    warehouse); pass an explicit tz-aware `now` for deterministic tests.

    Each returned dict carries the claim's core fields plus best-effort
    enrichment for a resolution method to read: `claim_text` (from
    raw_utterance), `speaker_name`, and `subject_entity_names` (comma-joined
    subject entity names via claim_entity_link -> entity_current). All three
    enrichment fields are LEFT JOINed and may be None/NULL — sparse entity
    data must never block due-selection.

    GROUP BY is on claim_id alone with every other selected claim column
    wrapped in ANY_VALUE(): BigQuery does not allow the JSON-typed
    `predicate_args` column in GROUP BY/ORDER BY/DISTINCT, and ANY_VALUE()
    sidesteps that while also being the semantically correct choice for
    columns that are 1:1 with claim_id (the only real fan-out here is via
    claim_entity_link, which STRING_AGG collapses).
    """
    query_parameters: list = [
        bigquery.ScalarQueryParameter("limit_val", "INT64", int(limit))
    ]

    if now is not None:
        now_dt = _resolve_now(now)
        now_expr = "@now"
        query_parameters.append(
            bigquery.ScalarQueryParameter("now", "TIMESTAMP", now_dt)
        )
    else:
        now_expr = "CURRENT_TIMESTAMP()"

    query = f"""
        SELECT
            c.claim_id                                   AS claim_id,
            ANY_VALUE(c.utterance_id)                     AS utterance_id,
            ANY_VALUE(c.speaker_entity_id)                AS speaker_entity_id,
            ANY_VALUE(c.domain)                            AS domain,
            ANY_VALUE(c.predicate)                         AS predicate,
            ANY_VALUE(c.predicate_args)                    AS predicate_args,
            ANY_VALUE(c.resolution_window_start)           AS resolution_window_start,
            ANY_VALUE(c.resolution_window_end)             AS resolution_window_end,
            ANY_VALUE(c.resolution_method_id)              AS resolution_method_id,
            ANY_VALUE(c.this_hash)                         AS this_hash,
            ANY_VALUE(c.priority_score)                    AS priority_score,
            ANY_VALUE(c.next_check_at)                     AS next_check_at,
            ANY_VALUE(c.attempt)                           AS attempt,
            ANY_VALUE(u.text)                              AS claim_text,
            ANY_VALUE(speaker.value)                       AS speaker_name,
            STRING_AGG(subj.value, ', ')                   AS subject_entity_names
        FROM {CLAIM_TABLE} c
        LEFT JOIN {RAW_UTTERANCE_TABLE} u
            ON u.utterance_id = c.utterance_id
        LEFT JOIN {ENTITY_CURRENT_VIEW} speaker
            ON speaker.entity_id = c.speaker_entity_id
           AND speaker.attr = '{ENTITY_NAME_ATTR}'
        LEFT JOIN {CLAIM_ENTITY_LINK_TABLE} link
            ON link.claim_id = c.claim_id
        LEFT JOIN {ENTITY_CURRENT_VIEW} subj
            ON subj.entity_id = link.entity_id
           AND subj.attr = '{ENTITY_NAME_ATTR}'
        WHERE c.resolution_window_end < {now_expr}
          AND (c.next_check_at IS NULL OR c.next_check_at <= {now_expr})
          AND NOT EXISTS (
              SELECT 1 FROM {RESOLUTION_TABLE} res WHERE res.claim_id = c.claim_id
          )
        GROUP BY c.claim_id
        ORDER BY priority_score DESC NULLS LAST, resolution_window_end ASC
        LIMIT @limit_val
    """
    df = db.fetch_df(query, query_parameters=query_parameters)
    if df.empty:
        return []
    return df.to_dict(orient="records")


# ---------------------------------------------------------------------------
# Hash chaining (imports cryptographic_ledger.compute_chain_hash — the
# chain-LINK step is not reinvented here; only the domain-specific
# canonicalization of a resolution's content fields is local, mirroring
# promote_claims._compute_this_hash's canonicalization approach so silver_v2
# hashing stays consistent in spirit across claim and resolution rows.)
# ---------------------------------------------------------------------------


def _normalise_hash_value(value: Any) -> Any:
    """Recursively normalise a value for canonical-JSON hashing: tz-aware
    ISO-8601 for datetimes, sorted keys for dicts, recurse into lists."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, dict):
        return {k: _normalise_hash_value(v) for k, v in sorted(value.items())}
    if isinstance(value, list):
        return [_normalise_hash_value(v) for v in value]
    return value


def _canonical_content_hash(payload: dict) -> str:
    """
    SHA-256 of the canonical JSON (sorted keys, ISO-normalised timestamps) of
    a resolution's *content* fields. Deliberately excludes prev_hash/this_hash
    — chaining onto the prior hash is a separate step performed by the
    imported `compute_chain_hash`, not folded into this canonicalization.
    """
    normalised = {k: _normalise_hash_value(v) for k, v in sorted(payload.items())}
    canonical = json.dumps(normalised, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _fetch_prev_hash(db: Any, claim_id: str) -> str:
    """
    prev_hash for a new resolution row:
      1. the latest existing resolution's this_hash for claim_id, if one
         somehow already exists (defensive — see module docstring), else
      2. the claim's own this_hash (anchors the resolution chain to the
         immutable claim record being resolved), else
      3. "" (chain root) if the claim row itself can't be found — should not
         happen for a claim_id returned by select_due_claims, but this must
         never raise.
    """
    prior = db.fetch_df(
        f"""
        SELECT this_hash FROM {RESOLUTION_TABLE}
        WHERE claim_id = @claim_id
        ORDER BY resolved_at DESC
        LIMIT 1
        """,
        query_parameters=[
            bigquery.ScalarQueryParameter("claim_id", "STRING", claim_id)
        ],
    )
    if not prior.empty:
        return str(prior.iloc[0]["this_hash"])

    claim_row = db.fetch_df(
        f"SELECT this_hash FROM {CLAIM_TABLE} WHERE claim_id = @claim_id LIMIT 1",
        query_parameters=[
            bigquery.ScalarQueryParameter("claim_id", "STRING", claim_id)
        ],
    )
    if not claim_row.empty:
        return str(claim_row.iloc[0]["this_hash"])

    logger.warning(
        "write_resolution: claim_id=%s not found in silver_v2_claims.claim — "
        "chaining from empty root",
        claim_id,
    )
    return ""


# ---------------------------------------------------------------------------
# claim_state_history
# ---------------------------------------------------------------------------


def _write_state_history(
    db: Any,
    claim_id: str,
    resolution_id: str,
    state: str,
    outcome: str,
    resolved_at: datetime,
    notes: Optional[str],
) -> None:
    """
    SCD-2 append: close any open PENDING row for this claim (best effort —
    promote_claims.py does not currently write an initial PENDING row, so a
    0-row UPDATE here is expected and harmless, not an error), then insert
    the new open row for the resolved state.
    """
    db.execute(
        f"""
        UPDATE {STATE_HISTORY_TABLE}
        SET effective_to = @resolved_at
        WHERE claim_id = @claim_id AND state = 'PENDING' AND effective_to IS NULL
        """,
        query_parameters=[
            bigquery.ScalarQueryParameter("resolved_at", "TIMESTAMP", resolved_at),
            bigquery.ScalarQueryParameter("claim_id", "STRING", claim_id),
        ],
    )

    binary_correct = {"CORRECT": True, "INCORRECT": False}.get(state)

    history_row = {
        "history_id": str(uuid.uuid4()),
        "claim_id": claim_id,
        "state": state,
        "effective_from": resolved_at,
        "effective_to": None,
        # 'ingestion' (not 'asserted_at'/backfill) — this row is written
        # during an ongoing resolution pass, not historical backfill. See
        # migration 028's effective_source column doc.
        "effective_source": "ingestion",
        "resolution_id": resolution_id,
        "brier_score": None,  # Slice 1 does not compute scoring — downstream
        "binary_correct": binary_correct,
        "notes": notes or f"silver_v2_resolver: outcome={outcome}",
        "created_at": resolved_at,
    }
    history_df = pd.DataFrame([history_row])
    for col in ("effective_from", "effective_to", "created_at"):
        history_df[col] = pd.to_datetime(history_df[col], utc=True)
    db.append_dataframe_to_table(history_df, STATE_HISTORY_TABLE)


# ---------------------------------------------------------------------------
# write_resolution
# ---------------------------------------------------------------------------


def write_resolution(
    db: Any,
    claim_id: str,
    outcome: str,
    outcome_confidence: float,
    evidence: dict,
    resolution_method_id: str,
    notes: Optional[str] = None,
    now: Optional[datetime] = None,
) -> bool:
    """
    Insert one silver_v2_claims.resolution row for `claim_id`, plus a
    matching silver_v2_claims.claim_state_history row.

    Idempotent: if a resolution already exists for claim_id, this is a no-op
    that returns False. Never double-inserts, never double-chains.

    Returns True if a resolution was written, False if it was a no-op.
    """
    resolved_at = _resolve_now(now)

    existing = db.fetch_df(
        f"SELECT resolution_id FROM {RESOLUTION_TABLE} WHERE claim_id = @claim_id LIMIT 1",
        query_parameters=[
            bigquery.ScalarQueryParameter("claim_id", "STRING", claim_id)
        ],
    )
    if not existing.empty:
        logger.info(
            "write_resolution: claim_id=%s already has a resolution — no-op (idempotent)",
            claim_id,
        )
        return False

    prev_hash = _fetch_prev_hash(db, claim_id)

    state = _OUTCOME_TO_STATE.get(outcome)
    if state is None:
        logger.warning(
            "write_resolution: unrecognised outcome=%r for claim_id=%s — "
            "mapping to UNVERIFIABLE",
            outcome,
            claim_id,
        )
        state = "UNVERIFIABLE"

    resolution_id = str(uuid.uuid4())

    content_payload = {
        "resolution_id": resolution_id,
        "claim_id": claim_id,
        "resolved_at": resolved_at,
        "outcome": outcome,
        "outcome_confidence": outcome_confidence,
        "evidence": evidence,
        "resolution_method_id": resolution_method_id,
        "notes": notes,
    }
    content_hash = _canonical_content_hash(content_payload)
    this_hash = compute_chain_hash(content_hash, prev_hash)

    resolution_row = {
        "resolution_id": resolution_id,
        "claim_id": claim_id,
        "resolved_at": resolved_at,
        "outcome": outcome,
        "outcome_confidence": float(outcome_confidence),
        "evidence": json.dumps(evidence, sort_keys=True, separators=(",", ":")),
        "resolution_method_id": resolution_method_id,
        "prev_hash": prev_hash,
        "this_hash": this_hash,
        "notes": notes,
    }
    resolution_df = pd.DataFrame([resolution_row])
    resolution_df["resolved_at"] = pd.to_datetime(
        resolution_df["resolved_at"], utc=True
    )
    db.append_dataframe_to_table(resolution_df, RESOLUTION_TABLE)

    _write_state_history(
        db, claim_id, resolution_id, state, outcome, resolved_at, notes
    )

    logger.info(
        "write_resolution: wrote resolution_id=%s for claim_id=%s outcome=%s state=%s",
        resolution_id,
        claim_id,
        outcome,
        state,
    )
    return True


# ---------------------------------------------------------------------------
# Pluggable resolution method seam
# ---------------------------------------------------------------------------


class ResolutionMethod(Protocol):
    """
    The pluggable contract every resolution method implements.

    Slice 2's LLM judge (claim text + entity context -> TRUE/FALSE/VOID +
    evidence) implements this directly; later rule-based domain adapters can
    too. Nothing in this module depends on any concrete implementation beyond
    this shape.
    """

    method_id: str  # must match a silver_v2_claims.resolution_method row

    def resolve(self, claim: dict) -> Optional[tuple[str, float, dict, Optional[str]]]:
        """
        Return (outcome, confidence, evidence, notes) for `claim`
        (a dict shaped like one row from select_due_claims()), or None if
        there is no verdict yet — e.g. still waiting on better evidence.
        None must never be treated as an error; it just means "skip".
        """
        ...


@dataclass(frozen=True)
class NoopResolutionMethod:
    """
    Slice-1 placeholder resolution method. Always defers.

    Exists so run_resolution_pass() can be exercised end-to-end (real due
    claims in, zero resolutions out, no crash) without any LLM or evidence
    dependency. Slice 2 replaces/augments this with a real method
    implementing the same ResolutionMethod protocol.
    """

    method_id: str = NOOP_METHOD_ID

    def resolve(self, claim: dict) -> Optional[tuple[str, float, dict, Optional[str]]]:
        return None


def ensure_resolution_method(
    db: Any,
    resolution_method_id: str,
    domain: str,
    name: str,
    adapter_path: str,
    data_source: str,
    config: Optional[dict] = None,
) -> bool:
    """
    Idempotently register a row in silver_v2_claims.resolution_method.

    BigQuery has no UNIQUE/PK enforcement on this table, so — like
    promote_claims.py's claim_id dedup — idempotency here is caller-side
    check-then-insert rather than a MERGE, keeping this readable and portable
    to the DuckDB test path.

    Returns True if a new row was inserted, False if resolution_method_id
    already existed (no-op).
    """
    existing = db.fetch_df(
        f"""
        SELECT resolution_method_id FROM {RESOLUTION_METHOD_TABLE}
        WHERE resolution_method_id = @method_id
        LIMIT 1
        """,
        query_parameters=[
            bigquery.ScalarQueryParameter("method_id", "STRING", resolution_method_id)
        ],
    )
    if not existing.empty:
        return False

    row = {
        "resolution_method_id": resolution_method_id,
        "domain": domain,
        "name": name,
        "adapter_path": adapter_path,
        "data_source": data_source,
        "config": (
            json.dumps(config, sort_keys=True, separators=(",", ":"))
            if config is not None
            else None
        ),
    }
    db.append_dataframe_to_table(pd.DataFrame([row]), RESOLUTION_METHOD_TABLE)
    return True


def ensure_noop_resolution_method(db: Any) -> bool:
    """Idempotently seed the manual/noop resolution_method row."""
    return ensure_resolution_method(
        db,
        resolution_method_id=NOOP_METHOD_ID,
        domain=NOOP_METHOD_DOMAIN,
        name=NOOP_METHOD_NAME,
        adapter_path=NOOP_METHOD_ADAPTER_PATH,
        data_source=NOOP_METHOD_DATA_SOURCE,
    )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def run_resolution_pass(
    db: Any,
    method: ResolutionMethod,
    limit: int = 50,
    now: Optional[datetime] = None,
) -> dict:
    """
    Select due claims, run `method.resolve()` on each, write any non-None
    verdicts.

    Always returns a dict with checked/resolved/skipped keys (0 when
    nothing happened) — never a partial dict. resolve_all()'s aggregation
    upstream sums summaries with `.get(key, 0)`; a summary missing a key it
    expects is exactly the class of bug that made every scheduled
    `resolve_daily` run crash (llm_judge's summary dict was missing
    'voided'). This orchestration deliberately can't repeat that.
    """
    checked = 0
    resolved = 0
    skipped = 0

    claims = select_due_claims(db, limit=limit, now=now)
    for claim in claims:
        checked += 1
        verdict = method.resolve(claim)
        if verdict is None:
            skipped += 1
            continue

        outcome, confidence, evidence, notes = verdict
        wrote = write_resolution(
            db,
            claim_id=claim["claim_id"],
            outcome=outcome,
            outcome_confidence=confidence,
            evidence=evidence,
            resolution_method_id=method.method_id,
            notes=notes,
            now=now,
        )
        if wrote:
            resolved += 1
        else:
            skipped += 1

    return {"checked": checked, "resolved": resolved, "skipped": skipped}
