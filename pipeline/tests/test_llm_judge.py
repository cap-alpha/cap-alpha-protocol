"""
Unit tests for LLM Judge Resolver (Issue #616).
Integration test at the bottom requires GEMINI_API_KEY or OLLAMA and is
skipped unless explicitly enabled via LLM_JUDGE_SMOKE_TEST=1.
"""

import json
import os
import unittest
from unittest.mock import MagicMock, patch

from src.resolvers.llm_judge import (
    DEFAULT_MAX_RESOLUTIONS,
    CONFIDENCE_THRESHOLD,
    JudgeResult,
    UNPARSEABLE_NOTES,
    judge_claim,
    run_llm_judge_pass,
)
from src.resolution_engine import VoidReason


class TestUnparseableNotesVocab(unittest.TestCase):
    """#1131 regression: the judge's candidate filter must include the current
    VoidReason.UNPARSEABLE_CLAIM value. #686 renamed the void value out from
    under UNPARSEABLE_NOTES once already (freezing the pool for ~77 days); pin
    it so that drift can't silently recur."""

    def test_current_unparseable_claim_value_is_eligible(self):
        assert VoidReason.UNPARSEABLE_CLAIM.value in UNPARSEABLE_NOTES

    def test_unparseable_notes_values_are_plain_strings(self):
        # An Enum member (instead of its .value) would never match outcome_notes
        # in the SQL IN clause. VoidReason is a `str, Enum`, so isinstance(...,
        # str) is True for members too — use an identity check on the concrete
        # type so a stray enum member is actually caught (an enum member renders
        # as "VoidReason.X" in the f-string that builds the SQL).
        for note in UNPARSEABLE_NOTES:
            assert type(note) is str


# ---------------------------------------------------------------------------
# judge_claim — unit tests (mocked LLM)
# ---------------------------------------------------------------------------


class TestJudgeClaim(unittest.TestCase):
    def _make_provider(self, response_text: str):
        m = MagicMock()
        m.classify.return_value = response_text
        m.model = "mock-model"
        return m

    def test_correct_verdict(self):
        provider = self._make_provider(
            json.dumps(
                {
                    "verdict": "CORRECT",
                    "confidence": 0.85,
                    "justification": "It happened.",
                }
            )
        )
        result = judge_claim("Mahomes will win Super Bowl MVP", provider=provider)
        assert result is not None
        assert result.verdict == "CORRECT"
        assert result.confidence == 0.85

    def test_incorrect_verdict(self):
        provider = self._make_provider(
            json.dumps(
                {
                    "verdict": "INCORRECT",
                    "confidence": 0.9,
                    "justification": "They lost.",
                }
            )
        )
        result = judge_claim("Eagles will win the Super Bowl", provider=provider)
        assert result is not None
        assert result.verdict == "INCORRECT"

    def test_unresolvable_verdict(self):
        provider = self._make_provider(
            json.dumps(
                {
                    "verdict": "UNRESOLVABLE",
                    "confidence": 0.3,
                    "justification": "Not verifiable.",
                }
            )
        )
        result = judge_claim("This team will dominate", provider=provider)
        assert result is not None
        assert result.verdict == "UNRESOLVABLE"

    def test_unknown_verdict_normalised_to_unresolvable(self):
        provider = self._make_provider(
            json.dumps(
                {"verdict": "MAYBE", "confidence": 0.5, "justification": "Uncertain."}
            )
        )
        result = judge_claim("Some weird claim", provider=provider)
        assert result is not None
        assert result.verdict == "UNRESOLVABLE"

    def test_strips_markdown_fences(self):
        raw = '```json\n{"verdict": "CORRECT", "confidence": 0.7, "justification": "Yes."}\n```'
        provider = self._make_provider(raw)
        result = judge_claim("Bears win NFC North", provider=provider)
        assert result is not None
        assert result.verdict == "CORRECT"

    def test_confidence_clamped_to_0_1(self):
        provider = self._make_provider(
            json.dumps(
                {"verdict": "CORRECT", "confidence": 1.5, "justification": "Over."}
            )
        )
        result = judge_claim("Something", provider=provider)
        assert result is not None
        assert result.confidence == 1.0

    def test_returns_none_on_llm_error(self):
        provider = MagicMock()
        provider.classify.side_effect = Exception("network error")
        provider.model = "mock"
        result = judge_claim("Test claim", provider=provider)
        assert result is None

    def test_returns_none_on_malformed_json(self):
        provider = self._make_provider("sorry, I cannot judge that")
        result = judge_claim("Test claim", provider=provider)
        assert result is None

    def test_justification_truncated_to_500_chars(self):
        long_just = "x" * 1000
        provider = self._make_provider(
            json.dumps(
                {"verdict": "CORRECT", "confidence": 0.8, "justification": long_just}
            )
        )
        result = judge_claim("Claim", provider=provider)
        assert result is not None
        assert len(result.justification) <= 500


# ---------------------------------------------------------------------------
# run_llm_judge_pass — unit tests (mocked DB + LLM)
# ---------------------------------------------------------------------------


class TestRunLlmJudgePass(unittest.TestCase):
    def _make_db(self, rows):
        db = MagicMock()
        import pandas as pd

        db.fetch_df.return_value = pd.DataFrame(rows)
        return db

    def _make_provider(self, verdict, confidence):
        m = MagicMock()
        m.classify.return_value = json.dumps(
            {"verdict": verdict, "confidence": confidence, "justification": "Test."}
        )
        m.model = "mock-model"
        return m

    def test_resolves_correct_claim(self):
        rows = [
            {
                "prediction_hash": "abc123",
                "extracted_claim": "Mahomes wins MVP",
                "pundit_name": "ESPN",
                "void_reason": "unparseable_draft_claim",
            }
        ]
        db = self._make_db(rows)
        provider = self._make_provider("CORRECT", 0.9)

        with patch("src.resolvers.llm_judge.record_resolution") as mock_record:
            summary = run_llm_judge_pass(db=db, dry_run=False, provider=provider)

        assert summary["resolved"] == 1
        assert summary["errors"] == 0
        mock_record.assert_called_once()
        result_arg = mock_record.call_args[0][0]
        assert result_arg.resolution_status == "CORRECT"
        assert "llm_judge:mock-model" in result_arg.outcome_source

    def test_skips_low_confidence(self):
        rows = [
            {
                "prediction_hash": "def456",
                "extracted_claim": "Some vague claim",
                "pundit_name": "ESPN",
                "void_reason": "unparseable_game_claim",
            }
        ]
        db = self._make_db(rows)
        provider = self._make_provider("CORRECT", 0.3)  # Below threshold

        with patch("src.resolvers.llm_judge.record_resolution") as mock_record:
            summary = run_llm_judge_pass(db=db, dry_run=False, provider=provider)

        assert summary["resolved"] == 0
        assert summary["skipped"] == 1
        mock_record.assert_not_called()

    def test_skips_unresolvable_verdict(self):
        rows = [
            {
                "prediction_hash": "ghi789",
                "extracted_claim": "Ambiguous claim",
                "pundit_name": "ESPN",
                "void_reason": "unparseable_stat_claim",
            }
        ]
        db = self._make_db(rows)
        provider = self._make_provider("UNRESOLVABLE", 0.9)

        with patch("src.resolvers.llm_judge.record_resolution") as mock_record:
            summary = run_llm_judge_pass(db=db, dry_run=False, provider=provider)

        assert summary["resolved"] == 0
        assert summary["skipped"] == 1
        mock_record.assert_not_called()

    def test_respects_max_resolutions_cap(self):
        rows = [
            {
                "prediction_hash": f"hash{i:03d}",
                "extracted_claim": f"Claim {i}",
                "pundit_name": "ESPN",
                "void_reason": "unparseable_draft_claim",
            }
            for i in range(10)
        ]
        db = self._make_db(rows)
        provider = self._make_provider("CORRECT", 0.9)

        with patch("src.resolvers.llm_judge.record_resolution"):
            summary = run_llm_judge_pass(
                db=db, dry_run=False, max_resolutions=3, provider=provider
            )

        assert summary["resolved"] == 3

    def test_dry_run_does_not_write(self):
        rows = [
            {
                "prediction_hash": "dry001",
                "extracted_claim": "Test claim",
                "pundit_name": "ESPN",
                "void_reason": "unparseable_draft_claim",
            }
        ]
        db = self._make_db(rows)
        provider = self._make_provider("CORRECT", 0.95)

        with patch("src.resolvers.llm_judge.record_resolution") as mock_record:
            summary = run_llm_judge_pass(db=db, dry_run=True, provider=provider)

        assert summary["resolved"] == 1
        mock_record.assert_not_called()

    def test_skips_empty_claim_text(self):
        rows = [
            {
                "prediction_hash": "empty001",
                "extracted_claim": "",
                "pundit_name": "ESPN",
                "void_reason": "unparseable_draft_claim",
            }
        ]
        db = self._make_db(rows)
        provider = self._make_provider("CORRECT", 0.9)

        with patch("src.resolvers.llm_judge.record_resolution") as mock_record:
            summary = run_llm_judge_pass(db=db, dry_run=False, provider=provider)

        assert summary["skipped"] == 1
        mock_record.assert_not_called()

    def test_returns_empty_summary_on_no_candidates(self):
        db = self._make_db([])
        provider = self._make_provider("CORRECT", 0.9)
        summary = run_llm_judge_pass(db=db, dry_run=False, provider=provider)
        assert summary == {"checked": 0, "resolved": 0, "skipped": 0, "errors": 0}


# ---------------------------------------------------------------------------
# Integration smoke test (real LLM call) — opt-in only
# ---------------------------------------------------------------------------


@unittest.skipUnless(
    os.environ.get("LLM_JUDGE_SMOKE_TEST") == "1",
    "Set LLM_JUDGE_SMOKE_TEST=1 to run real LLM smoke test",
)
class TestLlmJudgeSmokeTest(unittest.TestCase):
    def test_known_correct_claim_resolves_correctly(self):
        """
        Patrick Mahomes won the 2023 Super Bowl MVP — this is a well-known fact
        any capable LLM should know. Expects CORRECT with confidence >= 0.6.
        """
        result = judge_claim(
            "Patrick Mahomes will win Super Bowl LVII MVP (Super Bowl played Feb 2023)"
        )
        assert result is not None, "LLM returned no result"
        assert result.verdict == "CORRECT", (
            f"Expected CORRECT, got {result.verdict} (conf={result.confidence:.2f}): "
            f"{result.justification}"
        )
        assert result.confidence >= 0.6, (
            f"Confidence {result.confidence:.2f} too low for a known fact"
        )

    def test_known_incorrect_claim_resolves_correctly(self):
        """
        The Detroit Lions did NOT win Super Bowl LVII — they weren't even in it.
        """
        result = judge_claim(
            "The Detroit Lions will win Super Bowl LVII (played Feb 2023)"
        )
        assert result is not None, "LLM returned no result"
        assert result.verdict == "INCORRECT", (
            f"Expected INCORRECT, got {result.verdict} (conf={result.confidence:.2f}): "
            f"{result.justification}"
        )
        assert result.confidence >= 0.6


if __name__ == "__main__":
    unittest.main()
