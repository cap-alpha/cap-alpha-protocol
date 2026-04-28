"""
Pundit Calibration Metrics (Issue #341)

Measures how well-calibrated each pundit is: when they express high confidence,
do they actually get more right? A perfectly calibrated pundit would be correct
exactly as often as their stated confidence predicts.

Metrics:
  - Brier score: mean squared error between confidence and outcome (lower = better)
  - Reliability bins: per-confidence-tier hit rates for reliability diagrams
  - Overconfidence score: positive = tends to be overconfident, negative = underconfident

Confidence proxy: gold_layer.assertion_quality.quality_score (0-1)
Outcome source:   gold_layer.prediction_resolutions.binary_correct

Usage:
    python -m src.calibration --backfill   # compute and store all pundits
    python -m src.calibration --stats      # print sorted by brier_score
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

from src.db_manager import DBManager

logger = logging.getLogger(__name__)

LEDGER_TABLE = "gold_layer.prediction_ledger"
RESOLUTIONS_TABLE = "gold_layer.prediction_resolutions"
QUALITY_TABLE = "gold_layer.assertion_quality"
CALIBRATION_TABLE = "gold_layer.pundit_calibration"

# Minimum resolved predictions required to compute calibration
MIN_PREDICTIONS = 3


# ---------------------------------------------------------------------------
# Core math
# ---------------------------------------------------------------------------


def compute_brier_score(predictions: list[dict]) -> float:
    """
    Mean squared error between predicted confidence and binary outcome.

    Brier = mean((confidence - outcome)^2)
    Range: [0, 1]. Lower is better; perfect = 0.0, random = 0.25.

    Args:
        predictions: list of dicts with keys:
            - confidence: float in [0, 1] (predicted probability / quality score)
            - outcome: int/bool (1 or True = correct, 0 or False = incorrect)

    Returns:
        float Brier score, or 0.25 (random baseline) if list is empty.
    """
    if not predictions:
        return 0.25

    total = 0.0
    for p in predictions:
        conf = float(p["confidence"])
        outcome = float(p["outcome"])
        total += (conf - outcome) ** 2

    return total / len(predictions)


def compute_reliability_bins(predictions: list[dict], n_bins: int = 5) -> list[dict]:
    """
    Bucket predictions by confidence tier and compute actual hit rate per bucket.

    Used to plot a reliability diagram: if predicted_confidence ~= actual_hit_rate
    across all bins, the pundit is well-calibrated.

    Args:
        predictions: list of dicts with keys:
            - confidence: float in [0, 1]
            - outcome: int/bool
        n_bins: number of equal-width bins (default 5 => [0-0.2), [0.2-0.4), ...)

    Returns:
        list of dicts, one per non-empty bin:
        {
            bin_center: float,          # midpoint of the bin
            predicted_confidence: float, # mean confidence of predictions in bin
            actual_hit_rate: float,     # fraction of correct predictions in bin
            count: int,                 # number of predictions in bin
        }
    """
    if not predictions:
        return []

    bin_width = 1.0 / n_bins
    bins: dict[int, list[dict]] = {i: [] for i in range(n_bins)}

    for p in predictions:
        conf = float(p["confidence"])
        # Clamp to [0, 1] then bucket
        conf = max(0.0, min(1.0, conf))
        bucket = min(int(conf / bin_width), n_bins - 1)
        bins[bucket].append(p)

    result = []
    for i in range(n_bins):
        bucket_preds = bins[i]
        if not bucket_preds:
            continue
        bin_center = (i + 0.5) * bin_width
        mean_conf = sum(float(p["confidence"]) for p in bucket_preds) / len(
            bucket_preds
        )
        hit_rate = sum(float(p["outcome"]) for p in bucket_preds) / len(bucket_preds)
        result.append(
            {
                "bin_center": round(bin_center, 4),
                "predicted_confidence": round(mean_conf, 4),
                "actual_hit_rate": round(hit_rate, 4),
                "count": len(bucket_preds),
            }
        )

    return result


def compute_overconfidence_score(predictions: list[dict]) -> float:
    """
    Mean signed gap: mean(confidence - outcome).

    Positive = pundit is overconfident (claims are more confident than accuracy warrants).
    Negative = pundit is underconfident.
    Zero = perfectly calibrated on average.
    """
    if not predictions:
        return 0.0

    total = sum(float(p["confidence"]) - float(p["outcome"]) for p in predictions)
    return total / len(predictions)


# ---------------------------------------------------------------------------
# Per-pundit aggregation
# ---------------------------------------------------------------------------


def compute_pundit_calibration(pundit_id: str, db: DBManager) -> Optional[dict]:
    """
    Fetches resolved predictions for a pundit, joins confidence scores, and
    computes calibration metrics.

    Confidence proxy: assertion_quality.quality_score (0-1).
    Falls back gracefully if claim_scores table doesn't exist yet.

    Returns dict with:
        - brier_score: float
        - reliability_bins: list
        - overconfidence_score: float
        - n_predictions: int
    or None if the pundit has fewer than MIN_PREDICTIONS resolved predictions.
    """
    project_id = os.environ.get("GCP_PROJECT_ID")

    # Check if gold_layer.claim_scores exists; if not, fall back to assertion_quality
    # We always use assertion_quality.quality_score as the confidence proxy for now.
    query = f"""
        SELECT
            r.prediction_hash,
            COALESCE(aq.quality_score, 0.5) AS confidence,
            CASE WHEN r.binary_correct THEN 1.0 ELSE 0.0 END AS outcome
        FROM `{project_id}.{LEDGER_TABLE}` l
        INNER JOIN `{project_id}.{RESOLUTIONS_TABLE}` r
            ON l.prediction_hash = r.prediction_hash
        LEFT JOIN `{project_id}.{QUALITY_TABLE}` aq
            ON l.prediction_hash = aq.prediction_hash
        WHERE l.pundit_id = @pundit_id
          AND r.resolution_status IN ('CORRECT', 'INCORRECT')
          AND r.binary_correct IS NOT NULL
        ORDER BY l.ingestion_timestamp
    """
    from google.cloud.bigquery import QueryJobConfig, ScalarQueryParameter

    job_config = QueryJobConfig(
        query_parameters=[ScalarQueryParameter("pundit_id", "STRING", pundit_id)]
    )
    job = db.client.query(query, job_config=job_config)
    df = job.to_dataframe()

    if len(df) < MIN_PREDICTIONS:
        return None

    predictions = df[["confidence", "outcome"]].to_dict(orient="records")

    brier = compute_brier_score(predictions)
    bins = compute_reliability_bins(predictions)
    overconf = compute_overconfidence_score(predictions)

    return {
        "brier_score": round(brier, 6),
        "reliability_bins": bins,
        "overconfidence_score": round(overconf, 6),
        "n_predictions": len(predictions),
    }


# ---------------------------------------------------------------------------
# BigQuery table management
# ---------------------------------------------------------------------------


def _ensure_calibration_table(db: DBManager) -> None:
    """Creates gold_layer.pundit_calibration if it doesn't exist."""
    project_id = os.environ.get("GCP_PROJECT_ID")
    ddl = f"""
        CREATE TABLE IF NOT EXISTS `{project_id}.{CALIBRATION_TABLE}` (
            pundit_id         STRING    NOT NULL,
            pundit_name       STRING,
            brier_score       FLOAT64,
            overconfidence_score FLOAT64,
            reliability_bins  STRING,
            n_predictions     INT64,
            computed_at       TIMESTAMP NOT NULL
        )
        OPTIONS (description = 'Per-pundit calibration metrics for reliability diagrams')
    """
    db.client.query(ddl).result()
    logger.info("Ensured calibration table exists: %s", CALIBRATION_TABLE)


def _upsert_calibration_row(
    db: DBManager,
    pundit_id: str,
    pundit_name: str,
    metrics: dict,
) -> None:
    """Upserts a calibration row using MERGE on pundit_id."""
    project_id = os.environ.get("GCP_PROJECT_ID")
    bins_json = json.dumps(metrics["reliability_bins"])
    computed_at = datetime.now(timezone.utc).isoformat()

    merge_sql = f"""
        MERGE `{project_id}.{CALIBRATION_TABLE}` T
        USING (
            SELECT
                @pundit_id       AS pundit_id,
                @pundit_name     AS pundit_name,
                @brier_score     AS brier_score,
                @overconfidence_score AS overconfidence_score,
                @reliability_bins AS reliability_bins,
                @n_predictions   AS n_predictions,
                TIMESTAMP(@computed_at) AS computed_at
        ) S
        ON T.pundit_id = S.pundit_id
        WHEN MATCHED THEN UPDATE SET
            pundit_name          = S.pundit_name,
            brier_score          = S.brier_score,
            overconfidence_score = S.overconfidence_score,
            reliability_bins     = S.reliability_bins,
            n_predictions        = S.n_predictions,
            computed_at          = S.computed_at
        WHEN NOT MATCHED THEN INSERT ROW
    """
    from google.cloud.bigquery import QueryJobConfig, ScalarQueryParameter

    job_config = QueryJobConfig(
        query_parameters=[
            ScalarQueryParameter("pundit_id", "STRING", pundit_id),
            ScalarQueryParameter("pundit_name", "STRING", pundit_name),
            ScalarQueryParameter("brier_score", "FLOAT64", metrics["brier_score"]),
            ScalarQueryParameter(
                "overconfidence_score", "FLOAT64", metrics["overconfidence_score"]
            ),
            ScalarQueryParameter("reliability_bins", "STRING", bins_json),
            ScalarQueryParameter("n_predictions", "INT64", metrics["n_predictions"]),
            ScalarQueryParameter("computed_at", "STRING", computed_at),
        ]
    )
    db.client.query(merge_sql, job_config=job_config).result()


# ---------------------------------------------------------------------------
# Backfill
# ---------------------------------------------------------------------------


def backfill_calibration(db: Optional[DBManager] = None) -> list[dict]:
    """
    Computes calibration for all pundits with >= MIN_PREDICTIONS resolved
    predictions and writes results to gold_layer.pundit_calibration.

    Returns list of computed rows.
    """
    close_db = db is None
    if db is None:
        db = DBManager()

    try:
        project_id = os.environ.get("GCP_PROJECT_ID")
        _ensure_calibration_table(db)

        # Fetch all pundits with enough resolved predictions
        pundit_query = f"""
            SELECT
                l.pundit_id,
                l.pundit_name,
                COUNTIF(r.resolution_status IN ('CORRECT', 'INCORRECT')
                        AND r.binary_correct IS NOT NULL) AS resolved_count
            FROM `{project_id}.{LEDGER_TABLE}` l
            INNER JOIN `{project_id}.{RESOLUTIONS_TABLE}` r
                ON l.prediction_hash = r.prediction_hash
            GROUP BY l.pundit_id, l.pundit_name
            HAVING resolved_count >= {MIN_PREDICTIONS}
            ORDER BY l.pundit_name
        """
        pundits_df = db.client.query(pundit_query).to_dataframe()

        if pundits_df.empty:
            logger.info("No pundits with enough resolved predictions found.")
            return []

        logger.info("Computing calibration for %d pundits...", len(pundits_df))
        results = []

        for _, row in pundits_df.iterrows():
            pundit_id = row["pundit_id"]
            pundit_name = row["pundit_name"]

            metrics = compute_pundit_calibration(pundit_id, db)
            if metrics is None:
                logger.debug("Skipping %s — insufficient data", pundit_id)
                continue

            _upsert_calibration_row(db, pundit_id, pundit_name, metrics)
            logger.info(
                "Calibrated %s (%s): brier=%.4f overconf=%.4f n=%d",
                pundit_name,
                pundit_id,
                metrics["brier_score"],
                metrics["overconfidence_score"],
                metrics["n_predictions"],
            )
            results.append(
                {
                    "pundit_id": pundit_id,
                    "pundit_name": pundit_name,
                    **metrics,
                }
            )

        logger.info("Backfill complete: %d pundits calibrated.", len(results))
        return results
    finally:
        if close_db:
            db.close()


def print_calibration_stats(db: Optional[DBManager] = None) -> None:
    """Print all pundits sorted by Brier score (ascending = better calibrated)."""
    close_db = db is None
    if db is None:
        db = DBManager()

    try:
        project_id = os.environ.get("GCP_PROJECT_ID")
        query = f"""
            SELECT
                pundit_name,
                pundit_id,
                brier_score,
                overconfidence_score,
                n_predictions,
                computed_at
            FROM `{project_id}.{CALIBRATION_TABLE}`
            ORDER BY brier_score ASC
        """
        df = db.client.query(query).to_dataframe()

        if df.empty:
            print("No calibration data found. Run with --backfill first.")
            return

        print(f"\n{'=' * 80}")
        print(f"  Pundit Calibration Stats  (n={len(df)} pundits)")
        print("  Brier score: lower = better (0.0 = perfect, 0.25 = random baseline)")
        print("  Overconfidence: positive = overconfident, negative = underconfident")
        print(f"{'=' * 80}")
        print(f"  {'Rank':<5} {'Pundit':<30} {'Brier':>8} {'Overconf':>10} {'N':>6}")
        print(f"  {'-' * 65}")

        for rank, (_, row) in enumerate(df.iterrows(), start=1):
            marker = ""
            if rank <= 5:
                marker = " <<< top"
            elif rank > len(df) - 5:
                marker = " --- bottom"
            print(
                f"  {rank:<5} {str(row['pundit_name']):<30} "
                f"{row['brier_score']:>8.4f} {row['overconfidence_score']:>10.4f} "
                f"{int(row['n_predictions']):>6}{marker}"
            )

        print(f"{'=' * 80}\n")

        # Top 5
        top5 = df.head(5)
        print("Top 5 best-calibrated pundits (lowest Brier score):")
        for _, row in top5.iterrows():
            print(
                f"  {row['pundit_name']}: brier={row['brier_score']:.4f}, "
                f"overconf={row['overconfidence_score']:.4f}, n={int(row['n_predictions'])}"
            )

        # Bottom 5
        bottom5 = df.tail(5).iloc[::-1]
        print("\nBottom 5 least-calibrated pundits (highest Brier score):")
        for _, row in bottom5.iterrows():
            print(
                f"  {row['pundit_name']}: brier={row['brier_score']:.4f}, "
                f"overconf={row['overconfidence_score']:.4f}, n={int(row['n_predictions'])}"
            )
        print()

    finally:
        if close_db:
            db.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
    )

    if "--backfill" in sys.argv:
        print("Running calibration backfill...")
        results = backfill_calibration()
        print(f"Done. Calibrated {len(results)} pundits.")
        if results:
            print_calibration_stats()
    elif "--stats" in sys.argv:
        print_calibration_stats()
    else:
        print(
            "Usage:\n"
            "  python -m src.calibration --backfill   # compute and store\n"
            "  python -m src.calibration --stats      # print sorted by brier_score\n"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
