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

  - **v1.1 addition — Google Search grounding fallback** (#1129 read-path
    audit finding: `silver_v2_claims.resolution` stayed at 0 rows even after
    Slice 2 shipped). Root cause: `raw_utterance` is ingested
    punditry/predictions text, not outcome reporting — an entity/keyword
    ILIKE scan for "did the predicted outcome happen" essentially never
    matches, so `retrieve_evidence_snippets()` legitimately returns `[]` for
    nearly every real due claim and the v1 judge defers 100% of the time.
    But the outcomes themselves (draft picks, signings, game results) are
    public record. `GroundedLLMJudgeResolutionMethod` composes
    `LLMJudgeResolutionMethod` (tries local evidence first — free, no
    network) and falls back to a Google-Search-grounded Gemini call (the
    `google-genai` SDK's `tools=[types.Tool(google_search=...)]`, called
    directly — see `_default_grounded_search`) only when local evidence is
    absent/insufficient. Same conservative contract as v1: UNCERTAIN, a
    malformed/empty response, or confidence below threshold all defer.
    Additionally, a grounded verdict with zero search citations also defers
    — a confident-sounding verdict backed by no retrieved web evidence is
    the model answering from parametric memory, which grounding exists to
    replace, not merely supplement.

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
from datetime import datetime, timezone
from typing import Any, Callable, Optional

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
# Grounded (Google Search) resolution_method registration — v1.1 addition
# ---------------------------------------------------------------------------

GROUNDED_LLM_JUDGE_METHOD_ID = "llm_judge_gemini_grounded"
GROUNDED_LLM_JUDGE_METHOD_DOMAIN = "general"
GROUNDED_LLM_JUDGE_METHOD_NAME = (
    "LLM Judge (Gemini Google Search grounding, local-evidence fallback) — v1.1"
)
GROUNDED_LLM_JUDGE_METHOD_ADAPTER_PATH = (
    "pipeline.src.resolvers.llm_judge_silver:GroundedLLMJudgeResolutionMethod"
)
GROUNDED_LLM_JUDGE_METHOD_DATA_SOURCE = "llm.gemini.grounded"


def ensure_grounded_llm_judge_resolution_method(db: Any) -> bool:
    """Idempotently register the llm_judge_gemini_grounded resolution_method
    row. Thin wrapper over Slice-1's ensure_resolution_method, mirroring
    ensure_llm_judge_resolution_method above."""
    return ensure_resolution_method(
        db,
        resolution_method_id=GROUNDED_LLM_JUDGE_METHOD_ID,
        domain=GROUNDED_LLM_JUDGE_METHOD_DOMAIN,
        name=GROUNDED_LLM_JUDGE_METHOD_NAME,
        adapter_path=GROUNDED_LLM_JUDGE_METHOD_ADAPTER_PATH,
        data_source=GROUNDED_LLM_JUDGE_METHOD_DATA_SOURCE,
    )


# Overridable for local/manual runs (e.g. a grounding-capable preview model).
# Deliberately NOT read from llm_config.yaml — see module docstring.
#
# "gemini-flash-latest", not "gemini-2.5-flash": verified against a real
# GEMINI_API_KEY during PR development that "gemini-2.5-flash" 404s ("This
# model ... is no longer available to new users") for at least some API
# keys/projects, while "gemini-flash-latest" is accepted (confirmed via
# client.models.list() and a real generate_content call that got as far as
# a 429 quota response rather than a 404 model-not-found — i.e. the request
# was valid, only throttled). "-latest" aliases move over time by design;
# override via RESOLUTION_GROUNDED_MODEL if Google retires this one too.
DEFAULT_GROUNDED_MODEL = os.environ.get(
    "RESOLUTION_GROUNDED_MODEL", "gemini-flash-latest"
)

# Independently overridable from CONFIDENCE_THRESHOLD (web search grounding
# is a different evidence source with different noise characteristics), but
# defaults to the same value so operators get one fewer knob to think about
# until real-run data suggests otherwise.
GROUNDED_CONFIDENCE_THRESHOLD = float(
    os.environ.get(
        "LLM_JUDGE_SILVER_GROUNDED_CONFIDENCE_THRESHOLD", str(CONFIDENCE_THRESHOLD)
    )
)


# ---------------------------------------------------------------------------
# Grounded web-search fallback (#1129 read-path audit).
#
# Calls `google-genai` directly rather than through `src.llm_provider`.
# `llm_provider.py` / `llm_config.yaml` are protected extraction paths (see
# CLAUDE.md "Extraction-touching PR rules": editing them requires a real
# LLM smoke test + CODEOWNERS review). Grounded resolution is a
# resolution-only concern with a different call shape (a `tools=` config,
# no JSON-schema response enforcement, citation-shaped output) that does not
# belong in the shared extraction abstraction — so this module talks to
# google-genai directly, mirroring `llm_provider.GeminiProvider`'s own
# `from google import genai` / `GEMINI_API_KEY` construction pattern so
# credential handling stays consistent across the codebase without editing
# the protected file.
# ---------------------------------------------------------------------------


@dataclass
class GroundedSearchResult:
    """Return shape of a grounded (Google Search) Gemini call: the model's
    raw text response plus best-effort extracted citations."""

    text: Optional[str]
    citations: list[dict] = field(default_factory=list)


# A grounded-search callable's signature: prompt in, GroundedSearchResult
# out. Constructor-injectable on GroundedLLMJudgeResolutionMethod so tests
# never construct a real google-genai client.
GroundedSearchFn = Callable[[str], GroundedSearchResult]


def _extract_citations(response: Any) -> list[dict]:
    """
    Best-effort extraction of {"uri", "title"} citations from a google-genai
    grounded generate_content response's
    candidates[].grounding_metadata.grounding_chunks[].web.

    Returns [] (never raises) if the response has no grounding metadata —
    e.g. the model answered without needing to search, an SDK response-shape
    change, or a test double. Absence of citations is meaningful to the
    caller (GroundedLLMJudgeResolutionMethod.resolve() treats zero citations
    as "unverifiable" and defers even on an otherwise-confident verdict), so
    this must return a reliable [], never raise disguised as one.
    """
    citations: list[dict] = []
    try:
        for candidate in getattr(response, "candidates", None) or []:
            metadata = getattr(candidate, "grounding_metadata", None)
            if metadata is None:
                continue
            for chunk in getattr(metadata, "grounding_chunks", None) or []:
                web = getattr(chunk, "web", None)
                if web is None:
                    continue
                uri = getattr(web, "uri", None)
                title = getattr(web, "title", None)
                if uri or title:
                    citations.append({"uri": uri, "title": title})
    except Exception:
        logger.debug(
            "_extract_citations: failed to parse grounding metadata from "
            "response — treating as no citations",
            exc_info=True,
        )
        return []
    return citations


def _default_grounded_search(
    prompt: str, model: str = DEFAULT_GROUNDED_MODEL
) -> GroundedSearchResult:
    """
    Real Gemini call with the Google Search grounding tool enabled.

    Raises EnvironmentError if GEMINI_API_KEY is unset, and propagates any
    google-genai exception — GroundedLLMJudgeResolutionMethod.resolve()
    catches both and defers rather than crashing a resolution pass. Never
    called at class-construction time (see
    GroundedLLMJudgeResolutionMethod._get_search_fn) so instantiating the
    method never requires credentials.
    """
    from google import genai
    from google.genai import types

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "GEMINI_API_KEY not set — required for grounded (Google Search) "
            "resolution. Set it with: export GEMINI_API_KEY=<your-key>"
        )
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())]
        ),
    )
    return GroundedSearchResult(
        text=getattr(response, "text", None),
        citations=_extract_citations(response),
    )


GROUNDED_JUDGE_PROMPT_TEMPLATE = """You are an evidence-based prediction adjudicator with access to live web search. Search the web to determine whether a claim's predicted outcome has actually occurred. These are public-record sports events — draft picks, contract signings, trades, game results, awards — so authoritative reporting should exist if the outcome has happened.

Claim (asserted by {speaker} on {asserted_at}): "{claim_text}"
Subject(s): {subjects}

Search for the most recent, authoritative reporting on this claim's subject and predicted outcome. Then decide:
- Return "TRUE" only if you find clear, credible search results showing the predicted outcome occurred.
- Return "FALSE" only if you find clear, credible search results showing a contradicting outcome occurred (the predicted outcome demonstrably did NOT happen).
- Return "VOID" if search results show the claim is now moot/unresolvable for reasons unrelated to whether the prediction was right (e.g. the subject retired, the event was cancelled).
- Return "UNCERTAIN" if search results are insufficient, ambiguous, contradictory, or you cannot find authoritative coverage either way. Be conservative — prefer UNCERTAIN over guessing from general knowledge.

Respond with a JSON object only, no other text:
{{
  "verdict": "TRUE" | "FALSE" | "VOID" | "UNCERTAIN",
  "confidence": <float 0.0-1.0>,
  "reasoning": "<one or two sentences citing what your search found>"
}}"""


def _build_grounded_prompt(claim: dict, asserted_at: Optional[datetime] = None) -> str:
    speaker = claim.get("speaker_name") or "an unknown speaker"
    subjects = claim.get("subject_entity_names") or "unspecified"
    claim_text = (claim.get("claim_text") or "").replace('"', '\\"')
    asserted_at_str = (
        asserted_at.isoformat() if asserted_at is not None else "an unknown date"
    )
    return GROUNDED_JUDGE_PROMPT_TEMPLATE.format(
        speaker=speaker,
        subjects=subjects,
        claim_text=claim_text,
        asserted_at=asserted_at_str,
    )


# ---------------------------------------------------------------------------
# ResolutionMethod implementation — grounded fallback
# ---------------------------------------------------------------------------


@dataclass
class GroundedLLMJudgeResolutionMethod:
    """
    v1.1 (#1129 read-path audit) ResolutionMethod: tries Slice-2's local
    raw_utterance evidence first (via a composed LLMJudgeResolutionMethod,
    free — no network if evidence is simply absent), then falls back to a
    Google-Search-grounded Gemini call when local evidence is absent or
    insufficient (i.e. the local judge deferred).

    This grounded fallback is expected to be the path that actually resolves
    claims in practice: local raw_utterance evidence is entity/keyword-
    matched punditry, not outcome reporting, so it is empty for nearly every
    public-record claim (draft picks, signings, game results). Composing
    rather than duplicating LLMJudgeResolutionMethod means a claim with
    genuine local evidence still resolves for free without touching the web
    search API/quota.

    Conforms to ResolutionMethod: resolve(claim) -> (outcome, confidence,
    evidence, notes) | None. Conservative by the same contract as v1:
    UNCERTAIN, a malformed/empty grounded response, or a verdict below
    `confidence_threshold` all defer. Additionally, a grounded verdict with
    zero search citations also defers — see module docstring.

    `local_method` and `grounded_search_fn` are constructor-injectable so
    tests exercise resolve() without ever touching google-genai / network.
    """

    db: Any
    method_id: str = GROUNDED_LLM_JUDGE_METHOD_ID
    local_method: Optional[LLMJudgeResolutionMethod] = None
    grounded_model: str = DEFAULT_GROUNDED_MODEL
    confidence_threshold: float = GROUNDED_CONFIDENCE_THRESHOLD
    grounded_search_fn: Optional[GroundedSearchFn] = None
    _resolved_local: Optional[LLMJudgeResolutionMethod] = field(
        default=None, init=False, repr=False, compare=False
    )

    def _get_local_method(self) -> LLMJudgeResolutionMethod:
        # Lazily constructed for the same reason LLMJudgeResolutionMethod
        # lazily constructs its provider: instantiating this class must
        # never touch GEMINI_API_KEY / network before resolve() needs it.
        if self.local_method is not None:
            return self.local_method
        if self._resolved_local is None:
            self._resolved_local = LLMJudgeResolutionMethod(db=self.db)
        return self._resolved_local

    def _get_search_fn(self) -> GroundedSearchFn:
        if self.grounded_search_fn is not None:
            return self.grounded_search_fn
        model = self.grounded_model
        return lambda prompt: _default_grounded_search(prompt, model=model)

    def resolve(self, claim: dict) -> Optional[tuple[str, float, dict, Optional[str]]]:
        claim_id = claim.get("claim_id")
        claim_text = (claim.get("claim_text") or "").strip()
        if not claim_text:
            logger.debug(
                "GroundedLLMJudgeResolutionMethod: claim_id=%s has no "
                "claim_text — deferring",
                claim_id,
            )
            return None

        local_result = self._get_local_method().resolve(claim)
        if local_result is not None:
            outcome, confidence, evidence, notes = local_result
            evidence = dict(evidence, resolution_path="local_evidence")
            logger.info(
                "GroundedLLMJudgeResolutionMethod: claim_id=%s resolved from "
                "local raw_utterance evidence — grounded search skipped",
                claim_id,
            )
            return outcome, confidence, evidence, notes

        logger.info(
            "GroundedLLMJudgeResolutionMethod: claim_id=%s — no local "
            "evidence, falling back to Google Search grounding",
            claim_id,
        )

        asserted_at = _fetch_claim_asserted_at(self.db, claim_id)
        prompt = _build_grounded_prompt(claim, asserted_at)

        try:
            result = self._get_search_fn()(prompt)
        except Exception as exc:
            logger.warning(
                "GroundedLLMJudgeResolutionMethod: grounded search failed "
                "for claim_id=%s: %s",
                claim_id,
                exc,
            )
            return None

        parsed = _parse_llm_response(result.text)
        if parsed is None:
            logger.warning(
                "GroundedLLMJudgeResolutionMethod: malformed/empty grounded "
                "response for claim_id=%s: %r",
                claim_id,
                (result.text or "")[:200],
            )
            return None

        verdict = parsed["verdict"]
        confidence = parsed["confidence"]
        reasoning = parsed["reasoning"]

        outcome = _VERDICT_TO_OUTCOME.get(verdict)
        if outcome is None:
            logger.info(
                "GroundedLLMJudgeResolutionMethod: claim_id=%s verdict=%s — deferring",
                claim_id,
                verdict,
            )
            return None

        if confidence < self.confidence_threshold:
            logger.info(
                "GroundedLLMJudgeResolutionMethod: claim_id=%s verdict=%s "
                "confidence=%.2f < threshold=%.2f — deferring",
                claim_id,
                verdict,
                confidence,
                self.confidence_threshold,
            )
            return None

        if not result.citations:
            logger.info(
                "GroundedLLMJudgeResolutionMethod: claim_id=%s verdict=%s "
                "has no grounding citations — deferring (unverifiable, not "
                "just unconfident)",
                claim_id,
                verdict,
            )
            return None

        evidence = {
            "method": self.method_id,
            "resolution_path": "web_search_grounded",
            "provider_model": self.grounded_model,
            "llm_verdict": verdict,
            "llm_reasoning": reasoning,
            "citations": result.citations,
        }
        notes = (
            f"llm_judge_silver (grounded) verdict={verdict} conf={confidence:.2f}; "
            f"{reasoning}"
        )[:500]
        return outcome, confidence, evidence, notes


# ---------------------------------------------------------------------------
# Manual entry point — NOT wired into resolve_daily.py or any workflow.
# Usage: python -m src.resolvers.llm_judge_silver --limit 5
#        python -m src.resolvers.llm_judge_silver --grounded --limit 3
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    from src.db_manager import DBManager
    from src.resolvers.silver_v2_resolver import run_resolution_pass

    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(
        description=(
            "Run one manual silver_v2 LLM-judge resolution pass. Not wired "
            "into any scheduled workflow (Issue #1129 Slice 2 / v1.1)."
        )
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Max due claims to check this run (default: 5 — keep small, "
        "Gemini free tier has a daily quota; --grounded search calls may "
        "consume/bill quota differently than a plain classify() call, so "
        "keep this especially small for a first grounded run).",
    )
    parser.add_argument(
        "--grounded",
        action="store_true",
        help="Use GroundedLLMJudgeResolutionMethod (local raw_utterance "
        "evidence first, Google-Search-grounded Gemini fallback) instead of "
        "the local-evidence-only LLMJudgeResolutionMethod. Requires "
        "GEMINI_API_KEY. This is the #1129 read-path-audit fix: local "
        "evidence alone resolves ~0 claims because raw_utterance holds "
        "punditry, not outcome reporting.",
    )
    args = parser.parse_args()

    db = DBManager()
    try:
        if args.grounded:
            ensure_grounded_llm_judge_resolution_method(db)
            method = GroundedLLMJudgeResolutionMethod(db=db)
        else:
            ensure_llm_judge_resolution_method(db)
            method = LLMJudgeResolutionMethod(db=db)
        summary = run_resolution_pass(db, method, limit=args.limit)
        print(json.dumps(summary, indent=2))
    finally:
        db.close()
