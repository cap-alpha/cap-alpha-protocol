"""Tests for src.source_health — circuit breaker registry."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.source_health import (
    DEFAULT_COOLDOWN_MINUTES,
    DEFAULT_FAILURE_THRESHOLD,
    STATE_CLOSED,
    STATE_HALF_OPEN,
    STATE_OPEN,
    CircuitBreakerRegistry,
    SourceState,
)


def test_starts_closed():
    s = SourceState(source_id="rss:foo", source_kind="rss")
    assert s.state == STATE_CLOSED
    assert s.is_open() is False


def test_opens_after_threshold_consecutive_failures():
    s = SourceState(source_id="rss:foo", source_kind="rss")
    for _ in range(DEFAULT_FAILURE_THRESHOLD):
        s.record_failure("HTTP 503")
    assert s.state == STATE_OPEN
    assert s.is_open() is True


def test_success_resets_consecutive_counter_and_closes():
    s = SourceState(source_id="rss:foo", source_kind="rss")
    s.record_failure("nope")
    s.record_failure("nope")
    s.record_success()
    assert s.state == STATE_CLOSED
    assert s.consecutive_failures == 0
    assert s.total_failures == 2
    assert s.total_successes == 1


def test_half_open_after_cooldown():
    s = SourceState(source_id="yt:bar", source_kind="youtube")
    for _ in range(DEFAULT_FAILURE_THRESHOLD):
        s.record_failure("403")
    assert s.state == STATE_OPEN
    # Simulate cooldown elapsed by backdating opened_at
    s.opened_at = datetime.now(timezone.utc) - timedelta(
        minutes=DEFAULT_COOLDOWN_MINUTES + 1
    )
    assert s.is_open() is False
    assert s.state == STATE_HALF_OPEN


def test_half_open_failure_re_opens():
    s = SourceState(
        source_id="yt:bar",
        source_kind="youtube",
        state=STATE_HALF_OPEN,
        consecutive_failures=DEFAULT_FAILURE_THRESHOLD,
    )
    s.record_failure("still 403")
    assert s.state == STATE_OPEN


def test_half_open_success_closes():
    s = SourceState(
        source_id="yt:bar",
        source_kind="youtube",
        state=STATE_HALF_OPEN,
        consecutive_failures=DEFAULT_FAILURE_THRESHOLD,
    )
    s.record_success()
    assert s.state == STATE_CLOSED
    assert s.consecutive_failures == 0


def test_registry_tracks_dirty_rows():
    reg = CircuitBreakerRegistry()
    reg.record_failure("rss:a", "503", "rss")
    reg.record_success("rss:b", "rss")
    rows = reg.to_rows()
    assert len(rows) == 2
    assert {r["source_id"] for r in rows} == {"rss:a", "rss:b"}


def test_registry_is_open_query():
    reg = CircuitBreakerRegistry()
    for _ in range(DEFAULT_FAILURE_THRESHOLD):
        reg.record_failure("rss:dead", "404", "rss")
    assert reg.is_open("rss:dead") is True
    assert reg.is_open("rss:never-seen") is False


def test_registry_counts():
    reg = CircuitBreakerRegistry()
    reg.record_success("a", "rss")
    reg.record_success("b", "rss")
    for _ in range(DEFAULT_FAILURE_THRESHOLD):
        reg.record_failure("c", "boom", "rss")
    assert reg.healthy_count() == 2
    assert reg.open_count() == 1
