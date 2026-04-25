"""
Unit tests for the extraction eval harness (Issue #190).

Tests the eval harness logic (metrics, fixture loading) and
assertion_extractor filtering behaviour using a mock LLM provider.
No actual LLM calls are made.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.assertion_extractor import ExtractionResult, extract_assertions
from src.llm_provider import LLMProvider

# Fixtures file on disk
FIXTURES_PATH = Path(__file__).parent / "fixtures/extractor_eval.yaml"


# ---------------------------------------------------------------------------
# Minimal mock provider
# ---------------------------------------------------------------------------


def _make_provider(predictions: list[dict]) -> LLMProvider:
    """Return a mock LLMProvider that always returns the given predictions."""
    provider = MagicMock(spec=LLMProvider)
    provider.extract_predictions.return_value = predictions
    return provider


# ---------------------------------------------------------------------------
# Import eval harness helpers
# ---------------------------------------------------------------------------


def _load_harness():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "eval_extractor",
        Path(__file__).parent.parent / "scripts/eval_extractor.py",
    )
    mod = importlib.util.load_from_spec(spec)  # type: ignore[attr-defined]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


# ---------------------------------------------------------------------------
# Fixtures file
# ---------------------------------------------------------------------------


class TestFixturesFile:
    def test_fixtures_file_exists(self):
        assert FIXTURES_PATH.exists(), f"Fixtures file not found: {FIXTURES_PATH}"

    def test_fixtures_count(self):
        import yaml

        with open(FIXTURES_PATH) as f:
            data = yaml.safe_load(f)
        assert len(data) >= 15, "Need at least 15 eval cases"

    def test_fixtures_have_required_fields(self):
        import yaml

        with open(FIXTURES_PATH) as f:
            data = yaml.safe_load(f)
        for item in data:
            assert "id" in item
            assert "label" in item, f"Missing 'label' in {item.get('id')}"
            assert item["label"] in ("GOOD", "BAD"), f"Invalid label in {item.get('id')}"
            assert "text" in item

    def test_balanced_labels(self):
        import yaml

        with open(FIXTURES_PATH) as f:
            data = yaml.safe_load(f)
        good = sum(1 for d in data if d["label"] == "GOOD")
        bad = sum(1 for d in data if d["label"] == "BAD")
        # Should be roughly balanced (within 60/40 split)
        total = good + bad
        assert good / total >= 0.3, f"Too few GOOD cases: {good}/{total}"
        assert bad / total >= 0.3, f"Too few BAD cases: {bad}/{total}"


# ---------------------------------------------------------------------------
# extract_assertions with mock provider
# ---------------------------------------------------------------------------


class TestExtractAssertionsWithMock:
    def test_good_prediction_is_extracted(self):
        pred = {
            "extracted_claim": "Mahomes will throw for 4000+ yards",
            "pundit_name": "Adam Schefter",
            "claim_category": "player_performance",
            "season_year": 2027,
        }
        provider = _make_provider([pred])
        result = extract_assertions(
            content_hash="abc123",
            text="Mahomes will throw for 4000+ yards this season.",
            published_date="2026-04-01",
            provider=provider,
        )
        assert result.error is None
        assert len(result.predictions) == 1
        assert result.predictions[0]["extracted_claim"] == pred["extracted_claim"]

    def test_empty_claim_is_filtered(self):
        provider = _make_provider([{"extracted_claim": "", "pundit_name": "X"}])
        result = extract_assertions(
            content_hash="abc124", text="Some text", provider=provider
        )
        assert result.predictions == []

    def test_temporal_filter_rejects_past_season(self):
        pred = {
            "extracted_claim": "Chiefs win Super Bowl",
            "season_year": 2020,  # past season
        }
        provider = _make_provider([pred])
        result = extract_assertions(
            content_hash="abc125",
            text="Chiefs win Super Bowl",
            published_date="2026-01-01",
            provider=provider,
        )
        assert result.predictions == [], "Past-season prediction should be filtered"

    def test_current_year_prediction_is_kept(self):
        from datetime import datetime

        current_year = datetime.now().year
        pred = {
            "extracted_claim": "Bears take Caleb #1",
            "season_year": current_year,
        }
        provider = _make_provider([pred])
        result = extract_assertions(
            content_hash="abc126",
            text="Bears take Caleb Williams #1 overall.",
            provider=provider,
        )
        assert len(result.predictions) == 1

    def test_deduplication_within_article(self):
        preds = [
            {"extracted_claim": "Mahomes will throw for 4000 yards this season", "season_year": 2027},
            {"extracted_claim": "Mahomes will throw 4000 yards in 2026-27", "season_year": 2027},  # near-dup
            {"extracted_claim": "Chiefs will win the AFC West", "season_year": 2027},
        ]
        provider = _make_provider(preds)
        result = extract_assertions(
            content_hash="abc127",
            text="...",
            published_date="2026-04-01",
            provider=provider,
        )
        # Near-duplicate claims should be collapsed
        assert len(result.predictions) <= 2

    def test_provider_exception_returns_empty_result(self):
        provider = MagicMock(spec=LLMProvider)
        provider.extract_predictions.side_effect = RuntimeError("API down")
        result = extract_assertions(
            content_hash="abc128", text="Some text", provider=provider
        )
        assert result.predictions == []
        assert result.error is not None


# ---------------------------------------------------------------------------
# Eval harness metrics
# ---------------------------------------------------------------------------


class TestEvalHarnessMetrics:
    """Tests for compute_metrics() using synthetic EvalResult objects."""

    def _make_result(self, label: str, num_extracted: int):
        """Helper to create a minimal EvalResult-like object."""
        case = MagicMock()
        case.label = label
        extraction = ExtractionResult(
            content_hash="x",
            predictions=[{"extracted_claim": f"claim_{i}"} for i in range(num_extracted)],
        )

        class _R:
            def __init__(self, c, e):
                self.case = c
                self.extraction = e
                self.num_extracted = len(e.predictions)

            @property
            def predicted_has_prediction(self):
                return self.num_extracted > 0

            @property
            def actual_has_prediction(self):
                return self.case.label == "GOOD"

            @property
            def is_true_positive(self):
                return self.predicted_has_prediction and self.actual_has_prediction

            @property
            def is_false_positive(self):
                return self.predicted_has_prediction and not self.actual_has_prediction

            @property
            def is_true_negative(self):
                return not self.predicted_has_prediction and not self.actual_has_prediction

            @property
            def is_false_negative(self):
                return not self.predicted_has_prediction and self.actual_has_prediction

        return _R(case, extraction)

    def test_perfect_precision(self):
        from scripts.eval_extractor import compute_metrics

        results = [
            self._make_result("GOOD", 1),
            self._make_result("BAD", 0),
            self._make_result("GOOD", 2),
        ]
        m = compute_metrics(results)
        assert m["precision"] == 1.0
        assert m["recall"] == 1.0

    def test_zero_precision_when_all_false_positive(self):
        from scripts.eval_extractor import compute_metrics

        results = [self._make_result("BAD", 1), self._make_result("BAD", 2)]
        m = compute_metrics(results)
        assert m["precision"] == 0.0

    def test_f1_harmonic_mean(self):
        from scripts.eval_extractor import compute_metrics

        results = [
            self._make_result("GOOD", 1),  # TP
            self._make_result("BAD", 0),   # TN
            self._make_result("BAD", 1),   # FP
            self._make_result("GOOD", 0),  # FN
        ]
        m = compute_metrics(results)
        assert m["tp"] == 1
        assert m["fp"] == 1
        assert m["tn"] == 1
        assert m["fn"] == 1
        assert abs(m["precision"] - 0.5) < 0.01
        assert abs(m["recall"] - 0.5) < 0.01


# ---------------------------------------------------------------------------
# Fixtures loading via EvalCase
# ---------------------------------------------------------------------------


class TestEvalCaseLoading:
    def test_load_fixtures(self):
        import yaml

        from scripts.eval_extractor import EvalCase

        with open(FIXTURES_PATH) as f:
            data = yaml.safe_load(f)
        cases = [EvalCase(d) for d in data]
        assert len(cases) >= 15

    def test_content_hash_is_deterministic(self):
        from scripts.eval_extractor import EvalCase

        case_data = {
            "id": "t001",
            "label": "GOOD",
            "text": "Mahomes will win MVP.",
            "expected_claims": 1,
        }
        c1 = EvalCase(case_data)
        c2 = EvalCase(case_data)
        assert c1.content_hash == c2.content_hash
