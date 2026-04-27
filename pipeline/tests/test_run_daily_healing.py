"""Integration test: run_daily.py + Healer wrapping."""

from __future__ import annotations

import pytest

import src.run_daily as rd
from src.healing import Healer, register_default_playbooks


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    import src.healing as H

    monkeypatch.setattr(H.time, "sleep", lambda *_: None)


def _healer():
    h = Healer()
    register_default_playbooks(h)
    return h


def test_stage_succeeds_first_try(monkeypatch):
    seen = {"calls": 0}

    def fake_run_stage(name, cmd, best_effort=False, env=None):
        seen["calls"] += 1
        r = rd.StageResult(stage=name, cmd=cmd)
        r.finish(0)
        return r

    monkeypatch.setattr(rd, "run_stage", fake_run_stage)
    out = rd._run_stage_with_healing("media_ingest", "echo hi", _healer(), False)
    assert out.status == "ok"
    assert seen["calls"] == 1


def test_stage_heals_after_transient_503(monkeypatch):
    seen = {"calls": 0}

    def fake_run_stage(name, cmd, best_effort=False, env=None):
        seen["calls"] += 1
        r = rd.StageResult(stage=name, cmd=cmd)
        if seen["calls"] < 3:
            r.finish(1, "HTTP 503 from upstream")
        else:
            r.finish(0)
        return r

    monkeypatch.setattr(rd, "run_stage", fake_run_stage)
    out = rd._run_stage_with_healing("media_ingest", "fetch", _healer(), False)
    assert out.status == "ok"
    assert seen["calls"] == 3


def test_stage_escalates_novel_failure(monkeypatch):
    """Novel errors get one attempt and the failure surfaces."""
    seen = {"calls": 0}

    def fake_run_stage(name, cmd, best_effort=False, env=None):
        seen["calls"] += 1
        r = rd.StageResult(stage=name, cmd=cmd)
        r.finish(1, "WeirdError: never seen")
        return r

    # Avoid real `gh` shell-out
    import src.healing as H

    H.subprocess.run = lambda *a, **k: None  # type: ignore[assignment]

    monkeypatch.setattr(rd, "run_stage", fake_run_stage)
    out = rd._run_stage_with_healing("media_ingest", "x", _healer(), False)
    # The escalated path falls back through to the final attempt's result
    assert out.status == "error"
    assert seen["calls"] >= 1
