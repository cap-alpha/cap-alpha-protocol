"""
Extraction Quality Eval Harness (Issue #190)

Measures precision and recall of assertion_extractor.py against a
golden dataset of hand-labeled pundit text samples.

Usage:
    # Run against local Ollama (zero cloud cost):
    python scripts/eval_extractor.py

    # Run against a specific provider:
    python scripts/eval_extractor.py --provider ollama --model qwen2.5:32b
    python scripts/eval_extractor.py --provider gemini

    # Run in dry-run mode (print fixtures, no LLM calls):
    python scripts/eval_extractor.py --dry-run

Output: precision, recall, F1 per label class + per-item breakdown.
Target: precision ≥ 0.70 (meaningful claims / total claims extracted).
"""

import argparse
import hashlib
import logging
import sys
from pathlib import Path

import yaml

# Ensure pipeline/src is on the path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.assertion_extractor import ExtractionResult, extract_assertions
from src.llm_provider import LLMProvider, OllamaProvider

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
logger = logging.getLogger(__name__)

FIXTURES_PATH = Path(__file__).parent.parent / "tests/fixtures/extractor_eval.yaml"

# ─────────────────────────────────────────────────────────────────────────────
# Eval data structures
# ─────────────────────────────────────────────────────────────────────────────


class EvalCase:
    def __init__(self, data: dict):
        self.id = data["id"]
        self.label = data["label"]  # "GOOD" or "BAD"
        self.expected_claims = data.get("expected_claims", 0)
        self.notes = data.get("notes", "")
        self.text = data["text"].strip()
        self.author = data.get("author", "")
        self.source = data.get("source", "")
        self.published_date = data.get("published_date", "")

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.text.encode()).hexdigest()[:16]


class EvalResult:
    def __init__(self, case: EvalCase, extraction: ExtractionResult):
        self.case = case
        self.extraction = extraction
        self.num_extracted = len(extraction.predictions)

    @property
    def predicted_has_prediction(self) -> bool:
        return self.num_extracted > 0

    @property
    def actual_has_prediction(self) -> bool:
        return self.case.label == "GOOD"

    @property
    def is_true_positive(self) -> bool:
        return self.predicted_has_prediction and self.actual_has_prediction

    @property
    def is_false_positive(self) -> bool:
        return self.predicted_has_prediction and not self.actual_has_prediction

    @property
    def is_true_negative(self) -> bool:
        return not self.predicted_has_prediction and not self.actual_has_prediction

    @property
    def is_false_negative(self) -> bool:
        return not self.predicted_has_prediction and self.actual_has_prediction

    @property
    def outcome(self) -> str:
        if self.is_true_positive:
            return "TP"
        if self.is_false_positive:
            return "FP"
        if self.is_true_negative:
            return "TN"
        return "FN"


# ─────────────────────────────────────────────────────────────────────────────
# Metrics
# ─────────────────────────────────────────────────────────────────────────────


def compute_metrics(results: list[EvalResult]) -> dict:
    tp = sum(1 for r in results if r.is_true_positive)
    fp = sum(1 for r in results if r.is_false_positive)
    tn = sum(1 for r in results if r.is_true_negative)
    fn = sum(1 for r in results if r.is_false_negative)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )
    accuracy = (tp + tn) / len(results) if results else 0.0

    total_extracted = sum(r.num_extracted for r in results)
    total_good = sum(1 for r in results if r.actual_has_prediction)

    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "accuracy": accuracy,
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "total_cases": len(results),
        "total_good_cases": total_good,
        "total_extracted_predictions": total_extracted,
    }


def print_report(results: list[EvalResult], metrics: dict) -> None:
    print("\n" + "=" * 70)
    print("EXTRACTOR EVAL REPORT")
    print("=" * 70)
    print(f"Cases evaluated : {metrics['total_cases']}")
    print(f"  GOOD (should extract) : {metrics['total_good_cases']}")
    print(f"  BAD  (should skip)    : {metrics['total_cases'] - metrics['total_good_cases']}")
    print(f"Total predictions extracted: {metrics['total_extracted_predictions']}")
    print()
    print(f"Precision : {metrics['precision']:.2%}  (target: ≥70%)")
    print(f"Recall    : {metrics['recall']:.2%}")
    print(f"F1        : {metrics['f1']:.2%}")
    print(f"Accuracy  : {metrics['accuracy']:.2%}")
    print(f"  TP={metrics['tp']}  FP={metrics['fp']}  TN={metrics['tn']}  FN={metrics['fn']}")
    print()

    # Per-item breakdown
    print("-" * 70)
    print(f"{'ID':<12} {'Label':<6} {'Outcome':<5} {'Extracted':<10} Notes")
    print("-" * 70)
    for r in results:
        flag = "" if r.outcome in ("TP", "TN") else " ← !"
        print(
            f"{r.case.id:<12} {r.case.label:<6} {r.outcome:<5} "
            f"{r.num_extracted:<10} {r.case.notes[:40]}{flag}"
        )

    print("-" * 70)

    # Highlight failures
    failures = [r for r in results if r.outcome in ("FP", "FN")]
    if failures:
        print(f"\n{len(failures)} FAILURES:")
        for r in failures:
            print(f"\n  [{r.outcome}] {r.case.id} — {r.case.notes}")
            if r.outcome == "FP":
                for p in r.extraction.predictions:
                    print(f"    Extracted: {p.get('extracted_claim', '')[:80]}")
            else:
                print(f"    Text: {r.case.text[:120]}...")

    # Pass/fail verdict
    target_precision = 0.70
    passed = metrics["precision"] >= target_precision
    print(f"\n{'PASS' if passed else 'FAIL'} — precision "
          f"{metrics['precision']:.2%} {'≥' if passed else '<'} {target_precision:.0%} target")
    print("=" * 70)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────


def load_fixtures(path: Path) -> list[EvalCase]:
    with open(path) as f:
        data = yaml.safe_load(f)
    return [EvalCase(d) for d in data]


def build_provider(provider_name: str, model: str) -> LLMProvider:
    if provider_name == "ollama":
        return OllamaProvider(model=model)
    if provider_name == "gemini":
        from src.llm_provider import GeminiProvider
        return GeminiProvider()
    if provider_name == "claude":
        from src.llm_provider import ClaudeProvider
        return ClaudeProvider()
    raise ValueError(f"Unknown provider: {provider_name}")


def run_eval(
    fixtures: list[EvalCase],
    provider: LLMProvider,
    dry_run: bool = False,
) -> list[EvalResult]:
    results = []
    for i, case in enumerate(fixtures, 1):
        logger.info(f"[{i}/{len(fixtures)}] {case.id} ({case.label}) — {case.notes[:50]}")
        if dry_run:
            extraction = ExtractionResult(content_hash=case.content_hash, predictions=[])
        else:
            extraction = extract_assertions(
                content_hash=case.content_hash,
                text=case.text,
                author=case.author,
                source_name=case.source,
                published_date=case.published_date,
                sport="NFL",
                provider=provider,
            )
        results.append(EvalResult(case, extraction))
    return results


def main():
    parser = argparse.ArgumentParser(description="Extraction quality eval harness")
    parser.add_argument(
        "--provider",
        choices=["ollama", "gemini", "claude"],
        default="ollama",
        help="LLM backend to use (default: ollama)",
    )
    parser.add_argument(
        "--model",
        default="qwen2.5:32b",
        help="Model name for Ollama (default: qwen2.5:32b)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print fixtures without making LLM calls",
    )
    parser.add_argument(
        "--fixtures",
        default=str(FIXTURES_PATH),
        help="Path to eval fixtures YAML",
    )
    args = parser.parse_args()

    fixtures = load_fixtures(Path(args.fixtures))
    logger.info(f"Loaded {len(fixtures)} eval cases from {args.fixtures}")

    if args.dry_run:
        logger.info("Dry-run mode: no LLM calls will be made")
        provider = None
    else:
        provider = build_provider(args.provider, args.model)
        logger.info(f"Using provider: {args.provider} / {args.model}")

    results = run_eval(fixtures, provider, dry_run=args.dry_run)
    metrics = compute_metrics(results)
    print_report(results, metrics)

    # Exit 1 if precision below target
    if not args.dry_run and metrics["precision"] < 0.70:
        sys.exit(1)


if __name__ == "__main__":
    main()
