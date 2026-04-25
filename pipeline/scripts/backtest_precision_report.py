"""
2025 NFL Season Backtest Precision Report

Queries the prediction ledger and resolution table to measure extraction and
resolution quality for the 2025 season backtest (issue #245).

Usage:
    python pipeline/scripts/backtest_precision_report.py
    python pipeline/scripts/backtest_precision_report.py --season 2025
    python pipeline/scripts/backtest_precision_report.py --since 2025-01-01

Prerequisites:
    1. Crawl articles:
       python -m src.url_ingestor --config config/backtest_2025_seed_urls.yaml --search
    2. Extract predictions:
       python -m src.assertion_extractor --limit 500
    3. Resolve:
       python -m src.resolve_daily
    4. Run this report.
"""

import argparse
import os
import sys
from datetime import datetime, timezone

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.db_manager import DBManager


_CATEGORY_ORDER = ["draft_pick", "game_outcome", "player_performance", "contract", "other"]


def _run_query(db: DBManager, sql: str) -> pd.DataFrame:
    """Execute a BigQuery SQL string and return a DataFrame."""
    return db.fetch_df(sql)


def fetch_article_counts(db: DBManager, project_id: str, since: str) -> pd.DataFrame:
    """Count ingested articles by source type and ingestion date."""
    return _run_query(
        db,
        f"""
        SELECT
            fetch_source_type,
            source_id,
            DATE(ingested_at) AS ingest_date,
            COUNT(*) AS article_count
        FROM `{project_id}.nfl_dead_money.raw_pundit_media`
        WHERE ingested_at >= TIMESTAMP('{since}')
        GROUP BY 1, 2, 3
        ORDER BY 3 DESC, 4 DESC
        """,
    )


def fetch_prediction_counts(db: DBManager, project_id: str, since: str) -> pd.DataFrame:
    """Count predictions by category and status for articles ingested since `since`."""
    return _run_query(
        db,
        f"""
        SELECT
            claim_category,
            status,
            COUNT(*) AS prediction_count,
            COUNT(DISTINCT pundit_name) AS pundit_count
        FROM `{project_id}.nfl_dead_money.gold_layer.prediction_ledger`
        WHERE ingestion_timestamp >= TIMESTAMP('{since}')
        GROUP BY 1, 2
        ORDER BY 1, 2
        """,
    )


def fetch_resolution_summary(db: DBManager, project_id: str, since: str) -> pd.DataFrame:
    """Summarise resolution outcomes since `since`."""
    return _run_query(
        db,
        f"""
        SELECT
            l.claim_category,
            r.resolution_status,
            r.resolver,
            COUNT(*) AS count
        FROM `{project_id}.nfl_dead_money.gold_layer.prediction_resolutions` r
        JOIN `{project_id}.nfl_dead_money.gold_layer.prediction_ledger` l
            ON r.prediction_hash = l.prediction_hash
        WHERE r.resolved_at >= TIMESTAMP('{since}')
        GROUP BY 1, 2, 3
        ORDER BY 1, 4 DESC
        """,
    )


def fetch_pundit_accuracy(db: DBManager, project_id: str, since: str) -> pd.DataFrame:
    """Per-pundit accuracy for predictions resolved since `since`."""
    return _run_query(
        db,
        f"""
        SELECT
            l.pundit_name,
            l.claim_category,
            COUNT(*) AS total_resolved,
            COUNTIF(r.resolution_status = 'CORRECT') AS correct,
            COUNTIF(r.resolution_status = 'INCORRECT') AS incorrect,
            ROUND(
                SAFE_DIVIDE(
                    COUNTIF(r.resolution_status = 'CORRECT'),
                    COUNTIF(r.resolution_status IN ('CORRECT', 'INCORRECT'))
                ) * 100,
                1
            ) AS accuracy_pct
        FROM `{project_id}.nfl_dead_money.gold_layer.prediction_resolutions` r
        JOIN `{project_id}.nfl_dead_money.gold_layer.prediction_ledger` l
            ON r.prediction_hash = l.prediction_hash
        WHERE r.resolved_at >= TIMESTAMP('{since}')
          AND l.pundit_name IS NOT NULL
        GROUP BY 1, 2
        HAVING total_resolved >= 3
        ORDER BY 6 DESC, 3 DESC
        """,
    )


def print_section(title: str, df: pd.DataFrame) -> None:
    if df.empty:
        print(f"\n=== {title} ===\n  (no data)\n")
        return
    print(f"\n=== {title} ===")
    print(df.to_string(index=False))
    print()


def compute_precision_metrics(pred_df: pd.DataFrame, res_df: pd.DataFrame) -> dict:
    """
    Compute headline precision metrics from prediction and resolution DataFrames.

    Returns dict with:
      - total_predictions: all predictions ingested
      - testable: predictions not VOIDED
      - resolved: predictions with a CORRECT or INCORRECT resolution
      - precision_pct: resolved / testable * 100
      - accuracy_pct: CORRECT / (CORRECT + INCORRECT) * 100
    """
    if pred_df.empty:
        return {
            "total_predictions": 0,
            "testable": 0,
            "resolved": 0,
            "precision_pct": 0.0,
            "accuracy_pct": None,
        }

    total = int(pred_df["prediction_count"].sum())
    voided = int(
        pred_df.loc[pred_df["status"] == "VOIDED", "prediction_count"].sum()
    )
    testable = total - voided

    correct = 0
    incorrect = 0
    if not res_df.empty:
        correct = int(
            res_df.loc[res_df["resolution_status"] == "CORRECT", "count"].sum()
        )
        incorrect = int(
            res_df.loc[res_df["resolution_status"] == "INCORRECT", "count"].sum()
        )

    resolved = correct + incorrect
    precision_pct = round(resolved / testable * 100, 1) if testable else 0.0
    accuracy_pct = round(correct / resolved * 100, 1) if resolved else None

    return {
        "total_predictions": total,
        "testable": testable,
        "resolved": resolved,
        "precision_pct": precision_pct,
        "accuracy_pct": accuracy_pct,
    }


def run_report(since: str = "2025-01-01") -> None:
    project_id = os.environ.get("GCP_PROJECT_ID", "cap-alpha-protocol")
    db = DBManager()

    print(f"\n{'='*60}")
    print(f"  2025 NFL SEASON BACKTEST — PRECISION REPORT")
    print(f"  Since: {since}")
    print(f"  Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*60}")

    art_df = fetch_article_counts(db, project_id, since)
    print_section("ARTICLE INGESTION", art_df)
    total_articles = int(art_df["article_count"].sum()) if not art_df.empty else 0
    print(f"  Total articles: {total_articles}")

    pred_df = fetch_prediction_counts(db, project_id, since)
    print_section("PREDICTION EXTRACTION BY CATEGORY", pred_df)

    res_df = fetch_resolution_summary(db, project_id, since)
    print_section("RESOLUTION OUTCOMES BY CATEGORY", res_df)

    metrics = compute_precision_metrics(pred_df, res_df)
    print("=== HEADLINE METRICS ===")
    print(f"  Total predictions extracted : {metrics['total_predictions']}")
    print(f"  Testable (not voided)       : {metrics['testable']}")
    print(f"  Resolved (CORRECT+INCORRECT): {metrics['resolved']}")
    print(f"  Resolution coverage         : {metrics['precision_pct']}%")
    if metrics["accuracy_pct"] is not None:
        print(f"  Accuracy (of resolved)      : {metrics['accuracy_pct']}%")
    else:
        print("  Accuracy (of resolved)      : N/A (no resolutions yet)")

    acc_df = fetch_pundit_accuracy(db, project_id, since)
    print_section("PER-PUNDIT ACCURACY (≥3 resolved)", acc_df)

    db.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="2025 NFL season backtest precision report"
    )
    parser.add_argument(
        "--season",
        type=int,
        default=2025,
        help="NFL season year (default: 2025)",
    )
    parser.add_argument(
        "--since",
        default=None,
        help="Only include data ingested on or after this date (YYYY-MM-DD). "
        "Defaults to Jan 1 of --season.",
    )
    args = parser.parse_args()

    since = args.since or f"{args.season}-01-01"
    run_report(since=since)


if __name__ == "__main__":
    main()
