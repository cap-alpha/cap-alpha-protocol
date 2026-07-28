"""
LLM-judge ResolutionMethod for silver_v2 claims (Issue #1129 Slice 2)

Plan: https://github.com/cap-alpha/cap-alpha-protocol/issues/1129#issuecomment-5098662266
("Resolver cutover — implementation plan", Slice 2 — LLM-judge method).

Plugs into the Slice-1 seam (`pipeline/src/resolvers/silver_v2_resolver.py`):
`LLMJudgeResolutionMethod` implements `ResolutionMethod.resolve(claim) ->
(outcome, confidence, evidence, notes) | None` and is driven end-to-end by
Slice-1's `run_resolution_pass()` / `write_resolution()`. This module does
NOT reimplement due-selection, the writer, or hash chaining — see
silver_v2_resolver.py for that plumbing.

v1 design decisions (locked, per the Slice 2 task brief):

  - **Adjudication model**: Gemini free tier via the project's `llm_provider`
    abstraction (`get_provider`) — the same abstraction
    `assertion_extractor.py` and `resolvers/llm_judge.py` use. Defaults to
    the "gemini-flash" alias (locks `gemini-2.5-flash`) regardless of
    llm_config.yaml's `extraction` role default (currently Ollama) —
    `llm_config.yaml` has no `resolution` role section, so `get_provider`
    would otherwise fall back to the Ollama-configured `extraction` section.
    This is intentional: llm_config.yaml is a protected extraction path (see
    CLAUDE.md "Extraction-touching PR rules") and this module avoids editing
    it. Override the provider for local/manual runs without a GEMINI_API_KEY
    via the RESOLUTION_LLM_PROVIDER env var (e.g. "ollama").

  - **Evidence retrieval (v1, deliberately simple)**: entity/keyword match
    over `silver_v2_claims.raw_utterance` rows that (a) mention one of the
    claim's speaker/subject entity names as a case-insensitive substring and
    (b) were uttered after the claim's `asserted_at`. Top-K by recency. NO
    embeddings/vector store — that funnel is explicitly out of scope here
    (#1133). A claim with no entity names to search on, or with no matching
    evidence at all, defers (returns [] from retrieve_evidence_snippets(),
    which makes resolve() return None) rather than asking the LLM to guess
    blind from claim text alone.

  - **Outcome vocabulary**: the LLM is prompted for TRUE / FALSE / VOID /
    UNCERTAIN. TRUE/FALSE/VOID map onto write_resolution's outcome
    vocabulary (silver_v2_claims.resolution.outcome, migration 016) as
    true/false/vacuous respectively. UNCERTAIN, any unparseable/malformed
    LLM response, or a TRUE/FALSE/VOID verdict below CONFIDENCE_THRESHOLD
    all defer (resolve() returns None) so the claim stays due for a later
    pass — never a forced guess. This mirrors the "no gotcha" editorial
    stance from #1129 and the existing gold-layer `resolvers/llm_judge.py`'s
    confidence-gated design.

Explicitly OUT OF SCOPE for this module (per the Slice 2 task brief):
  - Embeddings / vector store evidence funnel (#1133).
  - Wiring into resolve_daily.py or any scheduled workflow — see the
    `__main__` block below for a manual, one-off invocation instead.
  - Any gold-layer or API change.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import timezone
from typing import Any, Optional

import pandas as pd
from google.cloud import bigquery

from src.llm_provider import LLMProvider, get_provider
from src.resolvers.silver_v2_resolver import (
    CLAIM_TABLE,
    RAW_UTTERANCE_TABLE,
    ensure_resolution_method,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# resolution_method registration
# ---------------------------------------------------------------------------

LLM_JUDGE_METHOD_ID = "llm_judge_gemini"
LLM_JUDGE_METHOD_DOMAIN = "general"
LLM_JUDGE_METHOD_NAME = (
    "LLM Judge (Gemini free tier, entity/keyword evidence) — Slice 2"
)
LLM_JUDGE_METHOD_ADAPTER_PATH = (
    "pipeline.src.resolvers.llm_judge_silver:LLMJudgeResolutionMethod"
)
LLM_JUDGE_METHOD_DATA_SOURCE = "llm.gemini"


def ensure_llm_judge_resolution_method(db: Any) -> bool:
    """Idempotently register the llm_judge_gemini resolution_method row.

    Thin wrapper over Slice-1's ensure_resolution_method — no new
    registration logic here.
    """
    return ensure_resolution_method(
        db,
        resolution_method_id=LLM_JUDGE_METHOD_ID,
        domain=LLM_JUDGE_METHOD_DOMAIN,
        name=LLM_JUDGE_METHOD_NAME,
        adapter_path=LLM_JUDGE_METHOD_ADAPTER_PATH,
        data_source=LLM_JUDGE_METHOD_DATA_SOURCE,
    )


# ---------------------------------------------------------------------------
# Provider selection — Gemini free tier by default (v1 decision)
# ---------------------------------------------------------------------------

# Overridable for local/manual runs without a GEMINI_API_KEY (e.g. "ollama").
# Deliberately NOT read from llm_config.yaml — that file is a protected
# extraction path (CLAUDE.md) and this module avoids editing it.
DEFAULT_RESOLUTION_PROVIDER = os.environ.get("RESOLUTION_LLM_PROVIDER", "gemini-flash")

# Claims resolved only when the LLM is this confident (mirrors
# resolvers/llm_judge.py's CONFIDENCE_THRESHOLD pattern).
CONFIDENCE_THRESHOLD = float(
    os.environ.get("LLM_JUDGE_SILVER_CONFIDENCE_THRESHOLD", "0.6")
)

DEFAULT_TOP_K = int(os.environ.get("RESOLUTION_EVIDENCE_TOP_K", "5"))


def _default_provider() -> LLMProvider:
    return get_provider(
        role="resolution", provider_override=DEFAULT_RESOLUTION_PROVIDER
    )


# ---------------------------------------------------------------------------
# Evidence retrieval (v1: entity/keyword match, no embeddings — see #1133)
# ---------------------------------------------------------------------------

_MIN_KEYWORD_LEN = 3  # skip 1-2 char noise (initials, stray punctuation splits)
_MAX_SNIPPET_TEXT_CHARS = 1000


def _extract_keywords(claim: dict) -> list[str]:
    """
    Build the entity/keyword list to match raw_utterance.text against:
    the claim's speaker_name plus each name in the comma-joined
    subject_entity_names (both come from select_due_claims()'s enrichment
    join), deduped case-insensitively and filtered to non-trivial strings.

    Returns [] if the claim carries no entity context at all (sparse entity
    data — see Slice 1's select_due_claims docstring). Callers must treat []
    as "cannot search, defer" rather than falling back to an unscoped scan
    of raw_utterance.
    """
    names: list[str] = []
    speaker = claim.get("speaker_name")
    if speaker and str(speaker).strip():
        names.append(str(speaker).strip())
    subjects = claim.get("subject_entity_names")
    if subjects and str(subjects).strip():
        names.extend(n.strip() for n in str(subjects).split(",") if n.strip())

    seen: set[str] = set()
    keywords: list[str] = []
    for name in names:
        key = name.lower()
        if key in seen or len(name) < _MIN_KEYWORD_LEN:
            continue
        seen.add(key)
        keywords.append(name)
    return keywords


def _fetch_claim_asserted_at(db: Any, claim_id: str):
    """
    Slice 1's select_due_claims() does not surface `asserted_at` (it wasn't
    needed for due-selection). Evidence retrieval needs it to bound the
    search to news that post-dates the original assertion, so this does one
    small extra lookup against the claim table rather than widening Slice
    1's query / touching that file.

    Returns a tz-aware UTC datetime, or None if the claim row is missing or
    asserted_at is NULL (defensive — should not happen for a claim_id
    returned by select_due_claims, but must never raise).
    """
    row = db.fetch_df(
        f"SELECT asserted_at FROM {CLAIM_TABLE} WHERE claim_id = @claim_id LIMIT 1",
        query_parameters=[
            bigquery.ScalarQueryParameter("claim_id", "STRING", claim_id)
        ],
    )
    if row.empty:
        return None
    value = row.iloc[0]["asserted_at"]
    if value is None or pd.isna(value):
        return None
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize(timezone.utc)
    return ts.to_pydatetime()


def retrieve_evidence_snippets(
    db: Any, claim: dict, top_k: int = DEFAULT_TOP_K
) -> list[dict]:
    """
    v1 evidence retrieval (#1129 Slice 2; superseded by the embeddings/vector
    funnel in #1133): entity/keyword match over raw_utterance rows that
    mention one of the claim's subject/speaker entity names and were uttered
    after the claim's asserted_at. Ordered most-recent-first, capped at
    top_k.

    Returns [] (never raises) when the claim has no entity names to search
    on or asserted_at can't be determined — both are "cannot search" states.
    `LLMJudgeResolutionMethod.resolve()` treats an empty evidence list as a
    reason to defer rather than ask the LLM to guess from claim text alone.
    """
    keywords = _extract_keywords(claim)
    if not keywords:
        logger.debug(
            "retrieve_evidence_snippets: claim_id=%s has no speaker/subject "
            "entity names — nothing to search on",
            claim.get("claim_id"),
        )
        return []

    asserted_at = _fetch_claim_asserted_at(db, claim["claim_id"])
    if asserted_at is None:
        logger.debug(
            "retrieve_evidence_snippets: claim_id=%s has no resolvable "
            "asserted_at — skipping evidence search",
            claim.get("claim_id"),
        )
        return []

    query_parameters: list = [
        bigquery.ScalarQueryParameter("asserted_at", "TIMESTAMP", asserted_at),
        bigquery.ScalarQueryParameter("limit_val", "INT64", int(top_k)),
    ]
    like_clauses = []
    for idx, kw in enumerate(keywords):
        pname = f"kw{idx}"
        like_clauses.append(f"u.text ILIKE @{pname}")
        query_parameters.append(
            bigquery.ScalarQueryParameter(pname, "STRING", f"%{kw}%")
        )

    query = f"""
        SELECT
            u.utterance_id  AS utterance_id,
            u.text          AS text,
            u.uttered_at    AS uttered_at,
            u.source_doc_id AS source_doc_id
        FROM {RAW_UTTERANCE_TABLE} u
        WHERE u.uttered_at > @asserted_at
          AND ({" OR ".join(like_clauses)})
        ORDER BY u.uttered_at DESC
        LIMIT @limit_val
    """
    df = db.fetch_df(query, query_parameters=query_parameters)
    if df.empty:
        return []
    return df.to_dict(orient="records")


def _serialise_snippet(snippet: dict) -> dict:
    """JSON-safe snippet dict: datetime -> ISO8601 string, text truncated."""
    uttered_at = snippet.get("uttered_at")
    if hasattr(uttered_at, "isoformat"):
        uttered_at_str = uttered_at.isoformat()
    else:
        uttered_at_str = str(uttered_at) if uttered_at is not None else None
    text = str(snippet.get("text") or "")[:_MAX_SNIPPET_TEXT_CHARS]
    return {
        "utterance_id": snippet.get("utterance_id"),
        "text": text,
        "uttered_at": uttered_at_str,
        "source_doc_id": snippet.get("source_doc_id"),
    }


# ---------------------------------------------------------------------------
# LLM prompt + response parsing
# ---------------------------------------------------------------------------

JUDGE_PROMPT_TEMPLATE = """You are an evidence-based prediction adjudicator. Decide whether a claim's predicted outcome has occurred, based ONLY on the evidence provided below — do not use outside knowledge.

Claim (asserted by {speaker}): "{claim_text}"
Subject(s): {subjects}

Evidence (recent items mentioning the claim's subject/speaker, retrieved after the claim was made, most recent first):
{evidence_block}

Decide:
- Return "TRUE" only if the evidence clearly shows the predicted outcome occurred.
- Return "FALSE" only if the evidence clearly shows the predicted outcome did NOT occur (a clearly contradicting outcome happened).
- Return "VOID" if the evidence shows the claim is now moot or unresolvable for reasons unrelated to whether the prediction was right (e.g. the subject retired, the event was cancelled).
- Return "UNCERTAIN" if the evidence is insufficient, ambiguous, or does not clearly settle the claim either way. Be conservative — prefer UNCERTAIN over guessing.

Respond with a JSON object only, no other text:
{{
  "verdict": "TRUE" | "FALSE" | "VOID" | "UNCERTAIN",
  "confidence": <float 0.0-1.0>,
  "reasoning": "<one or two sentences citing which evidence item(s) support the verdict>"
}}"""

_VALID_VERDICTS = {"TRUE", "FALSE", "VOID", "UNCERTAIN"}

# LLM verdict -> write_resolution()'s outcome vocabulary (migration 016:
# true|false|partial|unresolvable|vacuous). UNCERTAIN has no outcome mapping
# — it always defers, handled in resolve() before this dict is consulted.
_VERDICT_TO_OUTCOME = {
    "TRUE": "true",
    "FALSE": "false",
    "VOID": "vacuous",
}


def _build_prompt(claim: dict, serialised_snippets: list[dict]) -> str:
    speaker = claim.get("speaker_name") or "an unknown speaker"
    subjects = claim.get("subject_entity_names") or "unspecified"
    claim_text = (claim.get("claim_text") or "").replace('"', '\\"')
    lines = [
        f"{i}. [{s['uttered_at'] or 'unknown time'}] {s['text']}"
        for i, s in enumerate(serialised_snippets, start=1)
    ]
    return JUDGE_PROMPT_TEMPLATE.format(
        speaker=speaker,
        subjects=subjects,
        claim_text=claim_text,
        evidence_block="\n".join(lines),
    )


def _parse_llm_response(raw: Optional[str]) -> Optional[dict]:
    """
    Parse the LLM's JSON response into {verdict, confidence, reasoning}.

    Returns None (never raises) on empty input, non-JSON output, JSON that
    isn't an object, or a verdict outside _VALID_VERDICTS — every one of
    these is a "malformed response" case the caller must treat as a defer,
    not a crash.
    """
    if not raw:
        return None
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(ln for ln in lines if not ln.strip().startswith("```")).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return None
        try:
            data = json.loads(match.group())
        except json.JSONDecodeError:
            return None

    if not isinstance(data, dict):
        return None

    verdict = str(data.get("verdict", "")).strip().upper()
    if verdict not in _VALID_VERDICTS:
        return None

    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    reasoning = str(data.get("reasoning", ""))[:500]

    return {"verdict": verdict, "confidence": confidence, "reasoning": reasoning}


# ---------------------------------------------------------------------------
# ResolutionMethod implementation
# ---------------------------------------------------------------------------


@dataclass
class LLMJudgeResolutionMethod:
    """
    Slice 2 ResolutionMethod: judges claim text + retrieved evidence
    snippets via the Gemini-free-tier LLM provider.

    Conforms to silver_v2_resolver.ResolutionMethod: `resolve(claim)` returns
    (outcome, confidence, evidence, notes) or None. Conservative by design —
    defers (None) on missing claim text, no evidence, a malformed/UNCERTAIN
    LLM response, or confidence below `confidence_threshold`. Never guesses.

    `db` and `provider` are constructor args (not module-level singletons) so
    tests can inject a fake DB / mocked provider without any network access.
    """

    db: Any
    method_id: str = LLM_JUDGE_METHOD_ID
    provider: Optional[LLMProvider] = None
    top_k: int = DEFAULT_TOP_K
    confidence_threshold: float = CONFIDENCE_THRESHOLD
    _resolved_provider: Optional[LLMProvider] = field(
        default=None, init=False, repr=False, compare=False
    )

    def _get_provider(self) -> LLMProvider:
        # Lazily constructed (not in __post_init__) so simply instantiating
        # this class with an explicit `provider=` never touches
        # GEMINI_API_KEY / network, and constructing it without one only
        # requires credentials at first actual resolve() call.
        if self.provider is not None:
            return self.provider
        if self._resolved_provider is None:
            self._resolved_provider = _default_provider()
        return self._resolved_provider

    def resolve(self, claim: dict) -> Optional[tuple[str, float, dict, Optional[str]]]:
        claim_id = claim.get("claim_id")
        claim_text = (claim.get("claim_text") or "").strip()
        if not claim_text:
            logger.debug(
                "LLMJudgeResolutionMethod: claim_id=%s has no claim_text — deferring",
                claim_id,
            )
            return None

        snippets = retrieve_evidence_snippets(self.db, claim, top_k=self.top_k)
        if not snippets:
            logger.info(
                "LLMJudgeResolutionMethod: claim_id=%s — no evidence found, deferring",
                claim_id,
            )
            return None

        serialised = [_serialise_snippet(s) for s in snippets]
        prompt = _build_prompt(claim, serialised)

        try:
            raw = self._get_provider().classify(prompt)
        except Exception as exc:
            logger.warning(
                "LLMJudgeResolutionMethod: LLM call failed for claim_id=%s: %s",
                claim_id,
                exc,
            )
            return None

        parsed = _parse_llm_response(raw)
        if parsed is None:
            logger.warning(
                "LLMJudgeResolutionMethod: malformed LLM response for claim_id=%s: %r",
                claim_id,
                (raw or "")[:200],
            )
            return None

        verdict = parsed["verdict"]
        confidence = parsed["confidence"]
        reasoning = parsed["reasoning"]

        outcome = _VERDICT_TO_OUTCOME.get(verdict)
        if outcome is None:
            # UNCERTAIN (or any future verdict without an outcome mapping).
            logger.info(
                "LLMJudgeResolutionMethod: claim_id=%s verdict=%s — deferring",
                claim_id,
                verdict,
            )
            return None

        if confidence < self.confidence_threshold:
            logger.info(
                "LLMJudgeResolutionMethod: claim_id=%s verdict=%s confidence=%.2f "
                "< threshold=%.2f — deferring",
                claim_id,
                verdict,
                confidence,
                self.confidence_threshold,
            )
            return None

        evidence = {
            "method": self.method_id,
            "provider_model": getattr(self._get_provider(), "model", "unknown"),
            "llm_verdict": verdict,
            "llm_reasoning": reasoning,
            "snippets": serialised,
        }
        notes = (
            f"llm_judge_silver verdict={verdict} conf={confidence:.2f}; {reasoning}"[
                :500
            ]
        )
        return outcome, confidence, evidence, notes


# ---------------------------------------------------------------------------
# Manual entry point — NOT wired into resolve_daily.py or any workflow.
# Usage: python -m src.resolvers.llm_judge_silver --limit 5
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    from src.db_manager import DBManager
    from src.resolvers.silver_v2_resolver import run_resolution_pass

    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(
        description=(
            "Run one manual silver_v2 LLM-judge resolution pass. Not wired "
            "into any scheduled workflow (Issue #1129 Slice 2)."
        )
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Max due claims to check this run (default: 5 — keep small, "
        "Gemini free tier has a daily quota).",
    )
    args = parser.parse_args()

    db = DBManager()
    try:
        ensure_llm_judge_resolution_method(db)
        method = LLMJudgeResolutionMethod(db=db)
        summary = run_resolution_pass(db, method, limit=args.limit)
        print(json.dumps(summary, indent=2))
    finally:
        db.close()
