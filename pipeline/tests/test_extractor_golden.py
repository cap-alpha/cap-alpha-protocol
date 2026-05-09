"""
Golden fixture regression tests for the assertion extractor (Issue #600).

Runs extraction on 30 hand-labeled transcript snippets and verifies per-fixture:
  (a) speech_act_type of the first utterance matches exactly
  (b) testability_score of the first utterance is within ±0.15 of expected
  (c) total utterance count matches expected

Marked @pytest.mark.integration — runs in the CI smoke-test job, NOT the default
unit gate (which skips integration tests via -m "not integration").

Pass threshold configurable via GOLDEN_PASS_THRESHOLD env var (default 0.80).
  < threshold            → build fail
  [threshold, +0.10)     → warning (build passes but warns)
  >= threshold + 0.10    → clean pass
"""

import json
import os
import sys
import warnings
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.assertion_extractor import extract_assertions
from src.llm_provider import get_provider

FIXTURES_DIR = Path(__file__).parent / "fixtures/extraction_golden"
DEFAULT_THRESHOLD = 0.80
TESTABILITY_TOLERANCE = 0.15
WARNING_BAND = 0.10


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_provider():
    """Get the configured LLM provider, skipping the test if unavailable."""
    try:
        return get_provider("extraction")
    except EnvironmentError as exc:
        pytest.skip(f"LLM provider not configured for integration tests: {exc}")


def _load_fixtures() -> list[dict]:
    """Load all *.txt / *.expected.json pairs from the golden fixtures directory."""
    fixtures = []
    for txt_file in sorted(FIXTURES_DIR.glob("*.txt")):
        json_file = txt_file.with_suffix(".expected.json")
        if not json_file.exists():
            continue
        fixtures.append(
            {
                "name": txt_file.stem,
                "text": txt_file.read_text().strip(),
                "expected": json.loads(json_file.read_text()),
            }
        )
    return fixtures


def _check_fixture(fixture: dict, provider) -> dict:
    """
    Run extraction on one fixture and evaluate against expected labels.

    Returns a dict with keys:
      name    — fixture stem (e.g. "assertion_01")
      passed  — True if all three assertions hold
      reason  — human-readable failure reason (empty on pass)
    """
    expected = fixture["expected"]
    expected_sat: str = expected["speech_act_type"]
    expected_score: float = float(expected.get("testability_score_expected", 0.5))
    expected_count: int = int(expected["claim_count_expected"])

    result = extract_assertions(
        content_hash=fixture["name"],
        text=fixture["text"],
        provider=provider,
        allow_historical=True,
    )

    utterances = result.utterances or []

    # (c) utterance count
    if len(utterances) != expected_count:
        return {
            "name": fixture["name"],
            "passed": False,
            "reason": (f"utterance count={len(utterances)}, expected={expected_count}"),
        }

    # fixtures with claim_count_expected=0 pass if we reach here
    if not utterances:
        return {"name": fixture["name"], "passed": True, "reason": ""}

    primary = utterances[0]

    # (a) speech_act_type exact match on primary utterance
    actual_sat = primary.get("speech_act_type", "")
    if actual_sat != expected_sat:
        return {
            "name": fixture["name"],
            "passed": False,
            "reason": (f"speech_act_type={actual_sat!r}, expected={expected_sat!r}"),
        }

    # (b) testability_score within ±TESTABILITY_TOLERANCE
    actual_score = float(primary.get("testability_score", 0.0))
    if abs(actual_score - expected_score) > TESTABILITY_TOLERANCE:
        return {
            "name": fixture["name"],
            "passed": False,
            "reason": (
                f"testability_score={actual_score:.3f}, expected={expected_score:.3f} "
                f"(±{TESTABILITY_TOLERANCE})"
            ),
        }

    return {"name": fixture["name"], "passed": True, "reason": ""}


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestExtractorGolden:
    """
    Regression suite: 30 labeled transcript fixtures.

    Structural tests run without an LLM (fast, in unit gate).
    test_golden_regression calls the real LLM provider and is integration-only.
    """

    # -- structural tests (no LLM, always fast) --

    def test_fixtures_directory_exists(self):
        assert FIXTURES_DIR.exists(), (
            f"Golden fixtures directory missing: {FIXTURES_DIR}"
        )

    def test_fixture_count(self):
        fixtures = _load_fixtures()
        assert len(fixtures) >= 50, (
            f"Expected >= 50 golden fixtures, got {len(fixtures)}"
        )

    def test_fixture_coverage_per_type(self):
        """At least 5 fixtures per required speech_act_type."""
        fixtures = _load_fixtures()
        type_counts: dict[str, int] = {}
        for f in fixtures:
            sat = f["expected"].get("speech_act_type", "")
            type_counts[sat] = type_counts.get(sat, 0) + 1

        required_types = (
            "assertion",
            "conditional",
            "recall",
            "rhetorical_question",
            "hedge",
        )
        for sat in required_types:
            count = type_counts.get(sat, 0)
            assert count >= 10, (
                f"Need >= 10 fixtures for speech_act_type={sat!r}, got {count}"
            )

    def test_fixture_schema(self):
        """Every expected.json has required fields with valid types."""
        fixtures = _load_fixtures()
        for f in fixtures:
            exp = f["expected"]
            name = f["name"]
            assert "speech_act_type" in exp, f"{name}: missing speech_act_type"
            assert "testability_score_expected" in exp, (
                f"{name}: missing testability_score_expected"
            )
            assert "claim_count_expected" in exp, (
                f"{name}: missing claim_count_expected"
            )
            score = exp["testability_score_expected"]
            assert 0.0 <= float(score) <= 1.0, (
                f"{name}: testability_score_expected={score} out of [0,1]"
            )
            assert int(exp["claim_count_expected"]) >= 0, (
                f"{name}: claim_count_expected must be >= 0"
            )

    # -- live regression test (real LLM, integration gate) --

    def test_golden_regression(self):
        """
        Core regression gate. Calls the configured LLM provider on every fixture.

        Pass rate < GOLDEN_PASS_THRESHOLD  → pytest.fail (build break)
        Pass rate in [threshold, +0.10)    → warnings.warn (build passes with alert)
        Pass rate >= threshold + 0.10      → clean pass
        """
        fixtures = _load_fixtures()
        assert fixtures, "No golden fixtures found — check fixtures/extraction_golden/"

        threshold = float(
            os.environ.get("GOLDEN_PASS_THRESHOLD", str(DEFAULT_THRESHOLD))
        )
        warning_threshold = threshold + WARNING_BAND

        provider = _get_provider()

        results = [_check_fixture(f, provider) for f in fixtures]

        passed = [r for r in results if r["passed"]]
        failed = [r for r in results if not r["passed"]]
        pass_rate = len(passed) / len(results)

        failure_lines = "\n".join(f"  [{r['name']}] {r['reason']}" for r in failed[:10])

        if pass_rate < threshold:
            pytest.fail(
                f"Golden fixture pass rate {pass_rate:.1%} is below threshold "
                f"{threshold:.1%} ({len(passed)}/{len(results)} passed).\n"
                f"Failing fixtures (first 10):\n{failure_lines}"
            )
        elif pass_rate < warning_threshold:
            warnings.warn(
                f"Golden fixture pass rate {pass_rate:.1%} is below warning level "
                f"{warning_threshold:.1%} ({len(passed)}/{len(results)} passed). "
                f"Review failures before shipping.\n{failure_lines}",
                stacklevel=2,
            )
