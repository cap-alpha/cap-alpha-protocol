"""Per-source circuit breakers for the ingestion pipeline.

A source (RSS feed, YouTube channel, Wayback host) is tracked through
three states: CLOSED (healthy, fetch normally), OPEN (recently failing,
skip fetches), HALF_OPEN (cooldown elapsed, allow one probe).

State persists to gold_layer.source_health so the daily pipeline picks
up where it left off across runs.

Usage:
    from src.source_health import CircuitBreakerRegistry

    cb = CircuitBreakerRegistry.load_from_bigquery(db)
    if cb.is_open("youtube:UC_dnv-skzAYAvi09cYaIb1Q"):
        skip_source()
    try:
        fetch(...)
        cb.record_success(source_id)
    except Exception as e:
        cb.record_failure(source_id, str(e))
    cb.persist(db)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

SOURCE_HEALTH_TABLE = "source_health"

SOURCE_HEALTH_SCHEMA = """
CREATE TABLE IF NOT EXISTS source_health (
  source_id STRING NOT NULL,
  source_kind STRING NOT NULL,
  state STRING NOT NULL,
  consecutive_failures INT64 NOT NULL,
  total_failures INT64 NOT NULL,
  total_successes INT64 NOT NULL,
  last_failure_at TIMESTAMP,
  last_failure_reason STRING,
  last_success_at TIMESTAMP,
  opened_at TIMESTAMP,
  updated_at TIMESTAMP NOT NULL
)
"""

# Threshold tuning — open after N consecutive failures, retry after cooldown.
DEFAULT_FAILURE_THRESHOLD = 3
DEFAULT_COOLDOWN_MINUTES = 60

STATE_CLOSED = "CLOSED"
STATE_OPEN = "OPEN"
STATE_HALF_OPEN = "HALF_OPEN"


@dataclass
class SourceState:
    source_id: str
    source_kind: str  # "rss" | "youtube" | "wayback" | "rss_pundit"
    state: str = STATE_CLOSED
    consecutive_failures: int = 0
    total_failures: int = 0
    total_successes: int = 0
    last_failure_at: Optional[datetime] = None
    last_failure_reason: Optional[str] = None
    last_success_at: Optional[datetime] = None
    opened_at: Optional[datetime] = None

    def is_open(self, now: Optional[datetime] = None) -> bool:
        """Return True if fetches should currently be skipped."""
        now = now or datetime.now(timezone.utc)
        if self.state == STATE_CLOSED:
            return False
        if self.state == STATE_OPEN and self.opened_at:
            elapsed = now - self.opened_at
            if elapsed >= timedelta(minutes=DEFAULT_COOLDOWN_MINUTES):
                self.state = STATE_HALF_OPEN
                return False
            return True
        return False  # HALF_OPEN allows the probe through

    def record_success(self, now: Optional[datetime] = None) -> None:
        now = now or datetime.now(timezone.utc)
        self.total_successes += 1
        self.consecutive_failures = 0
        self.last_success_at = now
        self.state = STATE_CLOSED
        self.opened_at = None

    def record_failure(
        self,
        reason: str,
        now: Optional[datetime] = None,
        threshold: int = DEFAULT_FAILURE_THRESHOLD,
    ) -> None:
        now = now or datetime.now(timezone.utc)
        self.total_failures += 1
        self.consecutive_failures += 1
        self.last_failure_at = now
        self.last_failure_reason = reason[:500]
        if self.state == STATE_HALF_OPEN:
            self.state = STATE_OPEN
            self.opened_at = now
        elif self.consecutive_failures >= threshold:
            self.state = STATE_OPEN
            self.opened_at = now


class CircuitBreakerRegistry:
    def __init__(self):
        self._sources: dict[str, SourceState] = {}
        self._dirty: set[str] = set()

    def get_or_create(self, source_id: str, source_kind: str) -> SourceState:
        st = self._sources.get(source_id)
        if st is None:
            st = SourceState(source_id=source_id, source_kind=source_kind)
            self._sources[source_id] = st
        return st

    def is_open(self, source_id: str) -> bool:
        st = self._sources.get(source_id)
        if st is None:
            return False
        was_open = st.state == STATE_OPEN
        opened = st.is_open()
        if was_open and not opened:
            self._dirty.add(source_id)
        return opened

    def record_success(self, source_id: str, source_kind: str = "unknown") -> None:
        st = self.get_or_create(source_id, source_kind)
        st.record_success()
        self._dirty.add(source_id)

    def record_failure(
        self, source_id: str, reason: str, source_kind: str = "unknown"
    ) -> None:
        st = self.get_or_create(source_id, source_kind)
        st.record_failure(reason)
        self._dirty.add(source_id)
        if st.state == STATE_OPEN:
            logger.warning(
                "circuit OPEN for %s after %d consecutive failures: %s",
                source_id,
                st.consecutive_failures,
                reason[:120],
            )

    def healthy_count(self) -> int:
        return sum(1 for s in self._sources.values() if s.state == STATE_CLOSED)

    def open_count(self) -> int:
        return sum(1 for s in self._sources.values() if s.state == STATE_OPEN)

    def to_rows(self) -> list[dict]:
        now = datetime.now(timezone.utc)
        rows = []
        for s in self._sources.values():
            rows.append(
                {
                    "source_id": s.source_id,
                    "source_kind": s.source_kind,
                    "state": s.state,
                    "consecutive_failures": s.consecutive_failures,
                    "total_failures": s.total_failures,
                    "total_successes": s.total_successes,
                    "last_failure_at": s.last_failure_at,
                    "last_failure_reason": s.last_failure_reason,
                    "last_success_at": s.last_success_at,
                    "opened_at": s.opened_at,
                    "updated_at": now,
                }
            )
        return rows

    @classmethod
    def load_from_bigquery(cls, db) -> "CircuitBreakerRegistry":
        reg = cls()
        if not db.table_exists(SOURCE_HEALTH_TABLE):
            db.execute(SOURCE_HEALTH_SCHEMA)
            return reg
        try:
            df = db.query_to_dataframe(f"SELECT * FROM {SOURCE_HEALTH_TABLE}")
        except Exception as e:
            logger.warning("could not load source_health: %s", e)
            return reg
        for _, row in df.iterrows():
            st = SourceState(
                source_id=row["source_id"],
                source_kind=row["source_kind"],
                state=row["state"],
                consecutive_failures=int(row.get("consecutive_failures") or 0),
                total_failures=int(row.get("total_failures") or 0),
                total_successes=int(row.get("total_successes") or 0),
                last_failure_at=row.get("last_failure_at"),
                last_failure_reason=row.get("last_failure_reason"),
                last_success_at=row.get("last_success_at"),
                opened_at=row.get("opened_at"),
            )
            reg._sources[st.source_id] = st
        return reg

    def persist(self, db) -> None:
        """Upsert all dirty rows back to BigQuery."""
        if not self._dirty:
            return
        if not db.table_exists(SOURCE_HEALTH_TABLE):
            db.execute(SOURCE_HEALTH_SCHEMA)
        import pandas as pd

        rows = [r for r in self.to_rows() if r["source_id"] in self._dirty]
        if not rows:
            return
        df = pd.DataFrame(rows)
        ids = ",".join(f"'{i}'" for i in self._dirty)
        try:
            db.execute(f"DELETE FROM {SOURCE_HEALTH_TABLE} WHERE source_id IN ({ids})")
            db.append_dataframe_to_table(df, SOURCE_HEALTH_TABLE)
            self._dirty.clear()
        except Exception as e:
            logger.error("failed to persist source_health: %s", e)


def ensure_source_health_table(db) -> None:
    if not db.table_exists(SOURCE_HEALTH_TABLE):
        db.execute(SOURCE_HEALTH_SCHEMA)
