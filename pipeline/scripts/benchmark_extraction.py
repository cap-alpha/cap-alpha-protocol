"""
Extraction Benchmark: Local Ollama vs Cloud Gemini (Issue #182)

Runs both extraction pipelines on the same set of articles and measures:
  - Number of predictions extracted
  - JSON parse success rate
  - Total elapsed time
  - Cost estimate (cloud only)

Usage:
    # Compare Ollama (batched) vs Gemini (per-article) on 50 articles:
    python scripts/benchmark_extraction.py --limit 50

    # Dry-run: show article counts without making LLM calls:
    python scripts/benchmark_extraction.py --dry-run

    # Test a single provider:
    python scripts/benchmark_extraction.py --provider ollama --model qwen2.5:32b
    python scripts/benchmark_extraction.py --provider gemini

Output: table of metrics per provider.
"""

import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db_manager import DBManager
from src.llm_provider import get_provider, load_llm_config

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
logger = logging.getLogger(__name__)

# Cloud provider cost estimates (per 1M tokens, approximate)
_COST_PER_1M_INPUT: dict[str, float] = {
    "gemini": 0.35,  # gemini-2.5-flash
    "claude": 3.00,  # claude-sonnet-4-6
    "openai": 5.00,  # gpt-4o
    "ollama": 0.00,  # local, zero cost
}

_AVG_TOKENS_PER_ARTICLE = 500  # rough estimate


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------


def run_single_benchmark(
    provider_name: str,
    model: str,
    articles,
    use_batching: bool = False,
) -> dict:
    """
    Run extraction on the given articles using a single provider and return metrics.

    articles: list of dicts with keys: content_hash, raw_text, title, etc.
    """
    config = load_llm_config()
    config.setdefault("extraction", {})["provider"] = provider_name
    config["extraction"]["model"] = model
    config["batching"] = {"enabled": use_batching, "max_articles_per_batch": 5}

    provider = get_provider("extraction", config)

    total_extracted = 0
    total_errors = 0
    parse_failures = 0
    start = time.monotonic()

    if use_batching:
        from src.team_batcher import (
            annotate_team_mentions,
            batch_articles_by_team,
            build_batched_prompt,
            ArticleRecord,
        )
        from src.assertion_extractor import _deduplicate_claims

        arts = [
            ArticleRecord(
                content_hash=a["content_hash"],
                raw_text=a.get("raw_text", ""),
                title=a.get("title", ""),
                pundit_name=a.get("matched_pundit_name") or a.get("author") or "",
                source_name=a.get("source_id", ""),
                published_date="",
            )
            for a in articles
        ]
        annotate_team_mentions(arts)
        team_batches = batch_articles_by_team(arts, max_per_batch=5)
        total_batches = sum(len(bs) for bs in team_batches.values())
        logger.info(
            f"[{provider_name}/batched] {len(arts)} articles → {total_batches} batches"
        )

        for team, sub_batches in team_batches.items():
            for batch in sub_batches:
                prompt = build_batched_prompt(team, batch)
                try:
                    preds = provider.extract_predictions(prompt)
                    preds = _deduplicate_claims(
                        [p for p in preds if p.get("extracted_claim", "").strip()]
                    )
                    total_extracted += len(preds)
                except Exception as e:
                    logger.warning(f"Error in batch team={team}: {e}")
                    total_errors += 1
    else:
        from src.assertion_extractor import extract_assertions

        for a in articles:
            result = extract_assertions(
                content_hash=a["content_hash"],
                text=a.get("raw_text", ""),
                title=a.get("title", ""),
                author=a.get("author", ""),
                source_name=a.get("source_id", ""),
                published_date="",
                provider=provider,
            )
            if result.error:
                total_errors += 1
            else:
                total_extracted += len(result.predictions)

    elapsed = time.monotonic() - start
    n = len(articles)
    estimated_tokens = n * _AVG_TOKENS_PER_ARTICLE
    cost_per_1m = _COST_PER_1M_INPUT.get(provider_name, 0.0)
    estimated_cost = (estimated_tokens / 1_000_000) * cost_per_1m

    return {
        "provider": provider_name,
        "model": model,
        "batched": use_batching,
        "articles": n,
        "predictions_extracted": total_extracted,
        "avg_per_article": total_extracted / max(n, 1),
        "errors": total_errors,
        "elapsed_s": elapsed,
        "articles_per_min": 60 * n / max(elapsed, 0.001),
        "estimated_cost_usd": estimated_cost,
    }


def print_comparison(results: list[dict]) -> None:
    print("\n" + "=" * 90)
    print("EXTRACTION BENCHMARK RESULTS")
    print("=" * 90)
    header = (
        f"{'Provider':<12} {'Model':<25} {'Mode':<10} "
        f"{'Articles':<10} {'Extracted':<10} {'Avg/Art':<8} "
        f"{'Errors':<8} {'Time(s)':<10} {'Art/min':<10} {'Cost($)':<10}"
    )
    print(header)
    print("-" * 90)
    for r in results:
        mode = "batched" if r["batched"] else "per-art"
        print(
            f"{r['provider']:<12} {r['model']:<25} {mode:<10} "
            f"{r['articles']:<10} {r['predictions_extracted']:<10} "
            f"{r['avg_per_article']:<8.2f} {r['errors']:<8} "
            f"{r['elapsed_s']:<10.1f} {r['articles_per_min']:<10.1f} "
            f"${r['estimated_cost_usd']:<9.4f}"
        )
    print("=" * 90)

    # Highlight winner
    if len(results) > 1:
        best_extraction = max(results, key=lambda r: r["predictions_extracted"])
        fastest = min(results, key=lambda r: r["elapsed_s"])
        cheapest = min(results, key=lambda r: r["estimated_cost_usd"])
        print(
            f"\nBest extraction: {best_extraction['provider']} ({best_extraction['predictions_extracted']} predictions)"
        )
        print(f"Fastest:        {fastest['provider']} ({fastest['elapsed_s']:.1f}s)")
        print(
            f"Cheapest:       {cheapest['provider']} (${cheapest['estimated_cost_usd']:.4f})"
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Extraction quality benchmark")
    parser.add_argument(
        "--limit", type=int, default=50, help="Articles to benchmark on"
    )
    parser.add_argument(
        "--provider",
        choices=["ollama", "gemini", "claude", "all"],
        default="all",
        help="Provider to benchmark (default: all)",
    )
    parser.add_argument("--model", default="", help="Override model name")
    parser.add_argument(
        "--dry-run", action="store_true", help="Show article count, skip LLM"
    )
    args = parser.parse_args()

    with DBManager() as db:
        from src.assertion_extractor import get_unprocessed_media

        media_df = get_unprocessed_media(db, limit=args.limit)
        if media_df.empty:
            logger.error(
                "No articles found in raw_pundit_media. Run media ingestion first."
            )
            sys.exit(1)

        articles = media_df.to_dict("records")
        logger.info(f"Loaded {len(articles)} articles for benchmarking")

        if args.dry_run:
            logger.info(f"Dry-run: would benchmark {len(articles)} articles")
            for a in articles[:3]:
                logger.info(f"  - {a.get('title', '(no title)')[:80]}")
            return

    config = load_llm_config()
    benchmarks = []

    if args.provider in ("ollama", "all"):
        model = args.model or config.get("extraction", {}).get("model", "qwen2.5:32b")
        if config.get("extraction", {}).get("provider") == "ollama":
            model = config["extraction"]["model"]
        # Batched (new approach)
        benchmarks.append(("ollama", model or "qwen2.5:32b", True))

    if args.provider in ("gemini", "all"):
        # Per-article (baseline)
        benchmarks.append(("gemini", "gemini-2.5-flash", False))

    if args.provider == "claude":
        model = args.model or "claude-sonnet-4-6"
        benchmarks.append(("claude", model, False))

    results = []
    for provider_name, model, use_batching in benchmarks:
        logger.info(
            f"\nRunning benchmark: {provider_name}/{model} (batched={use_batching})"
        )
        try:
            result = run_single_benchmark(provider_name, model, articles, use_batching)
            results.append(result)
        except Exception as e:
            logger.error(f"Benchmark failed for {provider_name}: {e}")

    if results:
        print_comparison(results)
    else:
        logger.error("All benchmarks failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
