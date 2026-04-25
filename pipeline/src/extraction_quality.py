"""
Extraction Quality Reporter (Issue #247)

CLI for comparing extraction quality across prompt versions and LLM providers/models.
Queries gold_layer.prediction_ledger to produce per-group statistics.

Usage:
    python -m src.extraction_quality --compare-versions
    python -m src.extraction_quality --compare-providers
    python -m src.extraction_quality --compare-models
    python -m src.extraction_quality --compare-versions --compare-providers
"""

import argparse
import logging
import os
from typing import Optional

import pandas as pd

from src.db_manager import DBManager

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
logger = logging.getLogger(__name__)

LEDGER_TABLE = "gold_layer.prediction_ledger"
RESOLUTIONS_TABLE = "gold_layer.prediction_resolutions"


def _fetch_provenance_stats(db: DBManager) -> pd.DataFrame:
    """
    Fetch per-(prompt_version, llm_provider, llm_model) statistics from BQ.

    Returns a DataFrame with columns:
        prompt_version, llm_provider, llm_model,
        total_predictions, resolved, correct, incorrect, pending,
        precision (correct / resolved, NULL if no resolutions)
    """
    project_id = os.environ.get("GCP_PROJECT_ID")
    query = f"""
        SELECT
            COALESCE(l.prompt_version, 'unknown') AS prompt_version,
            COALESCE(l.llm_provider, 'unknown')   AS llm_provider,
            COALESCE(l.llm_model,    'unknown')   AS llm_model,
            COUNT(*)                               AS total_predictions,
            COUNTIF(r.resolution_status = 'CORRECT')   AS correct,
            COUNTIF(r.resolution_status = 'INCORRECT') AS incorrect,
            COUNTIF(r.resolution_status IS NULL
                    OR r.resolution_status = 'PENDING') AS pending,
            COUNTIF(r.resolution_status IN ('CORRECT', 'INCORRECT')) AS resolved,
            SAFE_DIVIDE(
                COUNTIF(r.resolution_status = 'CORRECT'),
                NULLIF(COUNTIF(r.resolution_status IN ('CORRECT', 'INCORRECT')), 0)
            ) AS precision
        FROM `{project_id}.{LEDGER_TABLE}` l
        LEFT JOIN `{project_id}.{RESOLUTIONS_TABLE}` r
            ON l.prediction_hash = r.prediction_hash
        GROUP BY 1, 2, 3
        ORDER BY total_predictions DESC
    """
    return db.fetch_df(query)


def _print_table(df: pd.DataFrame, group_cols: list[str]) -> None:
    """Print a grouped summary table."""
    agg = (
        df.groupby(group_cols, dropna=False)
        .agg(
            total_predictions=("total_predictions", "sum"),
            resolved=("resolved", "sum"),
            correct=("correct", "sum"),
            incorrect=("incorrect", "sum"),
            pending=("pending", "sum"),
        )
        .reset_index()
    )
    agg["precision"] = agg.apply(
        lambda r: f"{r['correct'] / r['resolved']:.1%}" if r["resolved"] > 0 else "—",
        axis=1,
    )

    header = " | ".join(
        [f"{c:<20}" for c in group_cols]
        + ["total", "resolved", "correct", "pending", "precision"]
    )
    print("\n" + header)
    print("-" * len(header))
    for _, row in agg.iterrows():
        parts = [f"{str(row[c]):<20}" for c in group_cols]
        parts += [
            f"{row['total_predictions']:<7}",
            f"{row['resolved']:<9}",
            f"{row['correct']:<8}",
            f"{row['pending']:<8}",
            str(row["precision"]),
        ]
        print(" | ".join(parts))
    print()


def run_report(
    compare_versions: bool = False,
    compare_providers: bool = False,
    compare_models: bool = False,
    db: Optional[DBManager] = None,
) -> None:
    """
    Fetch provenance stats and print comparison tables.
    At least one of compare_* must be True.
    """
    if not any([compare_versions, compare_providers, compare_models]):
        compare_versions = True  # default

    close_db = db is None
    if db is None:
        db = DBManager()

    try:
        df = _fetch_provenance_stats(db)

        if df.empty:
            print("No predictions found in ledger.")
            return

        total = df["total_predictions"].sum()
        resolved = df["resolved"].sum()
        correct = df["correct"].sum()
        print(
            f"\nLedger totals: {total:,} predictions | {resolved:,} resolved | "
            f"{correct:,} correct"
        )

        if compare_versions:
            print("\n=== By Prompt Version ===")
            _print_table(df, ["prompt_version"])

        if compare_providers:
            print("\n=== By LLM Provider ===")
            _print_table(df, ["llm_provider"])

        if compare_models:
            print("\n=== By LLM Model ===")
            _print_table(df, ["llm_model"])

        if compare_versions and compare_providers:
            print("\n=== By Prompt Version × LLM Provider ===")
            _print_table(df, ["prompt_version", "llm_provider"])

    finally:
        if close_db:
            db.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare extraction quality across prompt versions and LLM providers."
    )
    parser.add_argument(
        "--compare-versions",
        action="store_true",
        help="Break down by prompt_version",
    )
    parser.add_argument(
        "--compare-providers",
        action="store_true",
        help="Break down by llm_provider (ollama, gemini, etc.)",
    )
    parser.add_argument(
        "--compare-models",
        action="store_true",
        help="Break down by llm_model (qwen2.5:32b, gemini-2.5-flash, etc.)",
    )
    args = parser.parse_args()

    run_report(
        compare_versions=args.compare_versions,
        compare_providers=args.compare_providers,
        compare_models=args.compare_models,
    )


if __name__ == "__main__":
    main()
