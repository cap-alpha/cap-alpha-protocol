"""
LLM Judge Resolver (Issue #616)

Final fallback resolution pass: uses an LLM to judge claims that the rule-based
resolvers VOID'd as unparseable. Only writes a resolution when the LLM returns
confidence >= CONFIDENCE_THRESHOLD (default 0.6). Low-confidence judgements are
left PENDING so a future rule-based resolver or human review can handle them.

Usage:
    from src.resolvers.llm_judge import run_llm_judge_pass

    summary = run_llm_judge_pass(db, max_resolutions=25, dry_run=False)

The pass is wired into resolve_all() as the last step — see resolve_daily.py.
"""

import logging
import os
from dataclasses import dataclass
from typing import Optional

from src.db_manager import DBManager
from src.llm_provider import get_provider
from src.resolution_engine import ResolutionResult, record_resolution

logger = logging.getLogger(__name__)

# Predictions with these void reasons are eligible for LLM judge retry.
# NOTE (#1131): #686 (ff5e7ab9, 2026-05-05) collapsed every void call site in
# resolve_daily.py onto VoidReason.UNPARSEABLE_CLAIM ("unparseable_claim"). That
# value was absent here, so the judge's candidate pool silently froze to the
# pre-2026-05-05 backlog. The legacy strings are kept so that historical backlog
# stays eligible.
UNPARSEABLE_NOTES = (
    "unparseable_claim",  # current VoidReason.UNPARSEABLE_CLAIM value (#686)
    "unparseable_draft_claim",
    "unparseable_game_claim",
    "unparseable_stat_claim",
    "unrecognised_award_type",
    "no_predicted_player",
    "no_player_name",
    "unparseable_fa_team",
)

# Claims we resolve only when the LLM is THIS confident.
CONFIDENCE_THRESHOLD = float(os.environ.get("LLM_JUDGE_CONFIDENCE_THRESHOLD", "0.6"))

# Safety cap per run — prevents unbounded spend.
DEFAULT_MAX_RESOLUTIONS = int(os.environ.get("MAX_LLM_RESOLUTIONS_PER_RUN", "25"))

JUDGE_PROMPT_TEMPLATE = """You are a professional sports prediction judge. Your job is to decide whether a sports prediction turned out to be CORRECT, INCORRECT, or UNRESOLVABLE based on real-world outcomes.

Prediction: "{claim}"

Carefully consider:
- If you can determine with reasonable confidence whether this prediction came true, return CORRECT or INCORRECT.
- If the claim is ambiguous, hypothetical, unverifiable from public sources, or you lack sufficient knowledge to judge it, return UNRESOLVABLE.
- Be conservative: only return CORRECT or INCORRECT when you are genuinely confident.

Respond with a JSON object only, no other text:
{{
  "verdict": "CORRECT" | "INCORRECT" | "UNRESOLVABLE",
  "confidence": <float 0.0-1.0>,
  "justification": "<one or two sentences explaining the judgment>"
}}"""


@dataclass
class JudgeResult:
    verdict: str  # CORRECT | INCORRECT | UNRESOLVABLE
    confidence: float
    justification: str


def judge_claim(claim_text: str, provider=None) -> Optional[JudgeResult]:
    """
    Ask the LLM to judge a single claim.

    Returns a JudgeResult or None if the LLM call fails or returns
    unparseable output.
    """
    import json

    if provider is None:
        provider = get_provider(role="extraction")

    prompt = JUDGE_PROMPT_TEMPLATE.format(claim=claim_text.replace('"', '\\"'))

    try:
        raw = provider.classify(prompt)
    except Exception as exc:
        logger.warning(
            f"llm_judge: LLM call failed for claim '{claim_text[:60]}': {exc}"
        )
        return None

    # classify() returns the model's raw text; parse it as JSON.
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(ln for ln in lines if not ln.strip().startswith("```")).strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Try to find the JSON object within a longer response
        import re

        match = re.search(r"\{[^{}]+\}", raw, re.DOTALL)
        if not match:
            logger.warning(f"llm_judge: could not parse JSON from: {raw[:200]}")
            return None
        try:
            data = json.loads(match.group())
        except json.JSONDecodeError:
            logger.warning(f"llm_judge: nested JSON parse failed: {raw[:200]}")
            return None

    verdict = str(data.get("verdict", "UNRESOLVABLE")).upper()
    if verdict not in ("CORRECT", "INCORRECT", "UNRESOLVABLE"):
        verdict = "UNRESOLVABLE"

    try:
        confidence = float(data.get("confidence", 0.0))
        confidence = max(0.0, min(1.0, confidence))
    except (TypeError, ValueError):
        confidence = 0.0

    justification = str(data.get("justification", ""))[:500]

    return JudgeResult(
        verdict=verdict, confidence=confidence, justification=justification
    )


def _get_unparseable_voided(db: DBManager) -> "list[dict]":
    """
    Fetch VOID'd predictions whose void reason is one of the unparseable_* notes.
    Returns a list of dicts with prediction_hash + extracted_claim.
    """
    project_id = os.environ.get("GCP_PROJECT_ID")
    notes_csv = ", ".join(f"'{n}'" for n in UNPARSEABLE_NOTES)
    query = f"""
        SELECT
            l.prediction_hash,
            l.extracted_claim,
            l.pundit_name,
            r.outcome_notes AS void_reason
        FROM `{project_id}.gold_layer.prediction_ledger` l
        JOIN `{project_id}.gold_layer.prediction_resolutions` r
            ON l.prediction_hash = r.prediction_hash
        WHERE r.resolution_status = 'VOID'
          AND r.outcome_notes IN ({notes_csv})
        ORDER BY l.ingestion_timestamp ASC
    """
    try:
        df = db.fetch_df(query)
        return df.to_dict("records")
    except Exception as exc:
        logger.warning(f"llm_judge: failed to fetch voided predictions: {exc}")
        return []


def run_llm_judge_pass(
    db: Optional[DBManager] = None,
    dry_run: bool = False,
    max_resolutions: int = DEFAULT_MAX_RESOLUTIONS,
    confidence_threshold: float = CONFIDENCE_THRESHOLD,
    provider=None,
) -> dict:
    """
    Run the LLM fallback resolution pass.

    Fetches VOID'd predictions with unparseable reasons, judges each one,
    and writes a resolution for those with confidence >= confidence_threshold.

    Args:
        db: Optional shared DBManager.
        dry_run: Log what would happen without writing.
        max_resolutions: Max claims to resolve per run (cost guard).
        confidence_threshold: Minimum confidence to write a resolution.
        provider: Optional pre-initialised LLM provider.

    Returns:
        Summary dict: checked, resolved, skipped (low confidence), errors.
    """
    close_db = db is None
    if db is None:
        db = DBManager()

    try:
        if provider is None:
            try:
                provider = get_provider(role="extraction")
            except Exception as exc:
                logger.warning(f"llm_judge: could not initialise provider: {exc}")
                return {"checked": 0, "resolved": 0, "skipped": 0, "errors": 1}

        model_name = getattr(provider, "model", "unknown")
        outcome_source = f"llm_judge:{model_name}"

        candidates = _get_unparseable_voided(db)
        logger.info(f"llm_judge: {len(candidates)} unparseable-voided candidates")

        checked = resolved = skipped = errors = 0
        for row in candidates:
            if resolved >= max_resolutions:
                logger.info(
                    f"llm_judge: hit max_resolutions cap ({max_resolutions}), stopping"
                )
                break

            phash = row["prediction_hash"]
            claim = row.get("extracted_claim") or ""
            pundit = row.get("pundit_name", "?")
            void_reason = row.get("void_reason", "?")

            if not claim.strip():
                logger.debug(f"llm_judge: skip {phash[:12]}… — empty claim text")
                skipped += 1
                checked += 1
                continue

            checked += 1
            result = judge_claim(claim, provider=provider)

            if result is None:
                logger.warning(f"llm_judge: LLM error on {phash[:12]}… — skipping")
                errors += 1
                continue

            logger.info(
                f"  llm_judge {phash[:12]}… [{pundit}] "
                f"verdict={result.verdict} conf={result.confidence:.2f} "
                f"(was: {void_reason})"
            )

            if (
                result.verdict == "UNRESOLVABLE"
                or result.confidence < confidence_threshold
            ):
                logger.info(
                    f"    → SKIP (conf={result.confidence:.2f} < {confidence_threshold} "
                    f"or unresolvable)"
                )
                skipped += 1
                continue

            correct = result.verdict == "CORRECT"
            notes = (f"llm_judge conf={result.confidence:.2f}; {result.justification}")[
                :500
            ]

            if dry_run:
                logger.info(
                    f"    → DRY-RUN: would write {'CORRECT' if correct else 'INCORRECT'}"
                )
                resolved += 1
                continue

            resolution = ResolutionResult(
                prediction_hash=phash,
                resolution_status="CORRECT" if correct else "INCORRECT",
                resolver="auto",
                binary_correct=correct,
                outcome_source=outcome_source,
                outcome_notes=notes,
            )
            try:
                record_resolution(resolution, db=db)
                resolved += 1
            except Exception as exc:
                logger.error(
                    f"llm_judge: failed to write resolution for {phash[:12]}…: {exc}"
                )
                errors += 1

        logger.info(
            f"llm_judge: done — checked={checked} resolved={resolved} "
            f"skipped={skipped} errors={errors}"
        )
        return {
            "checked": checked,
            "resolved": resolved,
            "skipped": skipped,
            "errors": errors,
        }

    finally:
        if close_db:
            db.close()
