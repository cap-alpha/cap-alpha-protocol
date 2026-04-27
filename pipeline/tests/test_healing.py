"""Tests for src.healing — playbook framework."""

from __future__ import annotations

import pytest

from src.healing import (
    Healer,
    Playbook,
    _signature,
    register_default_playbooks,
)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    import src.healing as H

    monkeypatch.setattr(H.time, "sleep", lambda *_: None)


@pytest.fixture(autouse=True)
def _no_gh(monkeypatch):
    """Don't actually shell out to gh during tests."""
    import src.healing as H

    monkeypatch.setattr(H.subprocess, "run", lambda *a, **k: None)


def _healer():
    h = Healer()
    register_default_playbooks(h)
    return h


def test_ok_path_no_retry():
    out = _healer().run("stage", lambda: 42)
    assert out.outcome == "ok"
    assert out.result == 42
    assert out.attempts == 0


def test_heals_after_transient_503():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("HTTP 503 from upstream")
        return "recovered"

    out = _healer().run("stage", flaky)
    assert out.outcome == "healed"
    assert out.result == "recovered"
    assert out.playbook == "transient_http_retry"


def test_novel_error_escalates():
    def bomb():
        raise KeyError("never-seen-this")

    out = _healer().run("stage", bomb)
    assert out.outcome == "escalated"
    assert out.playbook is None
    assert "KeyError" in out.error_signature


def test_signature_normalizes_addresses_and_numbers():
    sig1 = _signature(RuntimeError("failed at 0xdeadbeef row 12345"))
    sig2 = _signature(RuntimeError("failed at 0xcafebabe row 67890"))
    assert sig1 == sig2


def test_signature_normalizes_urls():
    sig1 = _signature(RuntimeError("fetch failed for https://a.example/x"))
    sig2 = _signature(RuntimeError("fetch failed for https://b.example/y"))
    assert sig1 == sig2


def test_playbook_exhaustion_escalates():
    h = Healer()
    h.register(
        Playbook(
            name="always_fail",
            matches=lambda exc: True,
            remediate=lambda exc, n: False,
            max_attempts=2,
            backoff_s=0.0,
        )
    )

    def always():
        raise RuntimeError("nope")

    out = h.run("stage", always, max_total_attempts=10)
    assert out.outcome == "escalated"
    assert out.playbook == "always_fail"
    assert out.attempts == 3  # max_attempts=2 means we try twice, then escalate


def test_remediate_returns_true_skips_backoff():
    """If remediate returns True (already fixed), the next attempt should still try."""
    state = {"healed": False}

    def remediate(exc, n):
        state["healed"] = True
        return True

    pb = Playbook(
        name="self_fix",
        matches=lambda exc: True,
        remediate=remediate,
        max_attempts=3,
        backoff_s=0.0,
    )
    h = Healer()
    h.register(pb)

    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        if calls["n"] < 2:
            raise RuntimeError("fix me")
        return "ok"

    out = h.run("stage", fn)
    assert out.outcome == "healed"
    assert state["healed"] is True


def test_first_matching_playbook_wins():
    """Playbooks are matched in registration order."""
    h = Healer()
    fired = []
    h.register(
        Playbook(
            name="first",
            matches=lambda exc: True,
            remediate=lambda exc, n: fired.append("first") or False,
            max_attempts=1,
            backoff_s=0.0,
        )
    )
    h.register(
        Playbook(
            name="second",
            matches=lambda exc: True,
            remediate=lambda exc, n: fired.append("second") or False,
            max_attempts=1,
            backoff_s=0.0,
        )
    )

    def bomb():
        raise RuntimeError("x")

    h.run("stage", bomb)
    assert fired == ["first"]


def test_novel_signature_filed_only_once():
    h = Healer()
    filed = []

    import src.healing as H

    def fake_run(*a, **k):
        filed.append(a[0])

    H.subprocess.run = fake_run  # type: ignore[assignment]

    def bomb():
        raise KeyError("same-novel")

    h.run("stage", bomb)
    h.run("stage", bomb)
    assert len(filed) == 1
