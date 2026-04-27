"""Self-healing playbook framework.

Wraps pipeline stages with detect → diagnose → remediate. Each playbook
matches an error signature and applies a specific remediation strategy.
Outcomes are logged to gold_layer.healing_events; novel breakages are
filed as GitHub issues.

Usage:
    from src.healing import Healer, register_default_playbooks

    healer = Healer()
    register_default_playbooks(healer)
    outcome = healer.run("media_ingest", lambda: media_ingest_stage())
"""

from __future__ import annotations

import logging
import re
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional

logger = logging.getLogger(__name__)

HEALING_EVENTS_TABLE = "healing_events"

HEALING_EVENTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS healing_events (
  event_id STRING NOT NULL,
  stage STRING NOT NULL,
  error_signature STRING,
  playbook STRING,
  attempts INT64,
  outcome STRING NOT NULL,
  detail STRING,
  occurred_at TIMESTAMP NOT NULL,
  run_date DATE NOT NULL
)
PARTITION BY run_date
"""


@dataclass
class HealingOutcome:
    stage: str
    outcome: str  # "healed" | "escalated" | "skipped" | "ok"
    playbook: Optional[str] = None
    attempts: int = 0
    error_signature: Optional[str] = None
    detail: Optional[str] = None
    result: object = None


@dataclass
class Playbook:
    """A single remediation strategy."""

    name: str
    matches: Callable[[BaseException], bool]
    remediate: Callable[[BaseException, int], bool]
    max_attempts: int = 3
    backoff_s: float = 5.0


def _signature(exc: BaseException) -> str:
    """Stable error signature for grouping. Strips line numbers / tokens."""
    msg = f"{type(exc).__name__}: {exc}"
    msg = re.sub(r"0x[0-9a-fA-F]+", "0x?", msg)
    msg = re.sub(r"\b\d{3,}\b", "?", msg)
    msg = re.sub(r"https?://\S+", "<url>", msg)
    return msg[:200]


class Healer:
    def __init__(self):
        self.playbooks: list[Playbook] = []
        self._novel_signatures: set[str] = set()

    def register(self, pb: Playbook) -> None:
        self.playbooks.append(pb)

    def run(
        self,
        stage: str,
        fn: Callable[[], object],
        max_total_attempts: int = 5,
    ) -> HealingOutcome:
        attempts = 0
        last_exc: Optional[BaseException] = None
        last_pb: Optional[Playbook] = None

        while attempts < max_total_attempts:
            attempts += 1
            try:
                result = fn()
                if attempts == 1:
                    return HealingOutcome(stage=stage, outcome="ok", result=result)
                return HealingOutcome(
                    stage=stage,
                    outcome="healed",
                    playbook=last_pb.name if last_pb else None,
                    attempts=attempts,
                    error_signature=_signature(last_exc) if last_exc else None,
                    result=result,
                )
            except BaseException as exc:
                last_exc = exc
                pb = next((p for p in self.playbooks if p.matches(exc)), None)
                if pb is None:
                    sig = _signature(exc)
                    logger.error("[%s] no playbook for %s — escalating", stage, sig)
                    self._maybe_file_novel_issue(stage, sig, exc)
                    return HealingOutcome(
                        stage=stage,
                        outcome="escalated",
                        attempts=attempts,
                        error_signature=sig,
                        detail=str(exc)[:500],
                    )
                last_pb = pb
                if attempts > pb.max_attempts:
                    return HealingOutcome(
                        stage=stage,
                        outcome="escalated",
                        playbook=pb.name,
                        attempts=attempts,
                        error_signature=_signature(exc),
                        detail=f"playbook {pb.name} exhausted: {exc}"[:500],
                    )
                logger.warning(
                    "[%s] applying playbook %s (attempt %d/%d)",
                    stage,
                    pb.name,
                    attempts,
                    pb.max_attempts,
                )
                healed = False
                try:
                    healed = pb.remediate(exc, attempts)
                except BaseException as rem_exc:
                    logger.error(
                        "[%s] playbook %s remediation crashed: %s",
                        stage,
                        pb.name,
                        rem_exc,
                    )
                if not healed:
                    time.sleep(pb.backoff_s * (2 ** (attempts - 1)))

        return HealingOutcome(
            stage=stage,
            outcome="escalated",
            playbook=last_pb.name if last_pb else None,
            attempts=attempts,
            error_signature=_signature(last_exc) if last_exc else None,
            detail=f"max total attempts ({max_total_attempts}) exhausted",
        )

    def _maybe_file_novel_issue(
        self, stage: str, signature: str, exc: BaseException
    ) -> None:
        if signature in self._novel_signatures:
            return
        self._novel_signatures.add(signature)
        try:
            title = f"[self-heal] novel breakage in {stage}: {signature[:80]}"
            body = (
                f"Self-healing orchestrator encountered an unmapped error.\n\n"
                f"**Stage:** `{stage}`\n"
                f"**Signature:** `{signature}`\n"
                f"**Error:** ```\n{exc}\n```\n\n"
                f"_Auto-filed by `pipeline/src/healing.py`. "
                f"Add a playbook to remediate, or close if not actionable._"
            )
            subprocess.run(
                [
                    "gh",
                    "issue",
                    "create",
                    "--title",
                    title,
                    "--body",
                    body,
                    "--label",
                    "self-heal,bug",
                ],
                check=False,
                capture_output=True,
                timeout=15,
            )
        except Exception as e:
            logger.warning("failed to file novel-breakage issue: %s", e)


def persist_outcome(db, outcome: HealingOutcome) -> None:
    """Append a healing event row to gold_layer.healing_events."""
    if outcome.outcome == "ok":
        return
    import pandas as pd

    now = datetime.now(timezone.utc)
    df = pd.DataFrame(
        [
            {
                "event_id": uuid.uuid4().hex,
                "stage": outcome.stage,
                "error_signature": outcome.error_signature,
                "playbook": outcome.playbook,
                "attempts": outcome.attempts,
                "outcome": outcome.outcome,
                "detail": outcome.detail,
                "occurred_at": now,
                "run_date": now.date(),
            }
        ]
    )
    try:
        db.append_dataframe_to_table(df, HEALING_EVENTS_TABLE)
    except Exception as e:
        logger.warning("failed to persist healing event: %s", e)


def ensure_healing_table(db) -> None:
    if not db.table_exists(HEALING_EVENTS_TABLE):
        db.execute(HEALING_EVENTS_SCHEMA)


# ---------------------------------------------------------------------------
# Default playbooks
# ---------------------------------------------------------------------------


def _is_transient_http(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return any(
        s in msg
        for s in (
            "503",
            "502",
            "504",
            "429",
            "timeout",
            "timed out",
            "connection reset",
        )
    )


def _is_llm_rate_limit(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return ("rate" in msg and "limit" in msg) or "429" in msg or "quota" in msg


def _is_json_parse(exc: BaseException) -> bool:
    name = type(exc).__name__
    return name in ("JSONDecodeError", "ValidationError") or "json" in str(exc).lower()


def register_default_playbooks(healer: Healer) -> None:
    """Register the baseline set of playbooks. Extend per-stage as needed."""

    healer.register(
        Playbook(
            name="transient_http_retry",
            matches=_is_transient_http,
            remediate=lambda exc, n: False,  # backoff-only
            max_attempts=4,
            backoff_s=10.0,
        )
    )

    healer.register(
        Playbook(
            name="llm_rate_limit_backoff",
            matches=_is_llm_rate_limit,
            remediate=lambda exc, n: False,
            max_attempts=5,
            backoff_s=30.0,
        )
    )

    healer.register(
        Playbook(
            name="json_parse_strict_retry",
            matches=_is_json_parse,
            remediate=lambda exc, n: False,
            max_attempts=2,
            backoff_s=2.0,
        )
    )
