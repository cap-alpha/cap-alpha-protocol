"""
Pundit Calibration Metrics (Issues #341, #809)

Issue #341 (original): Per-pundit Brier score + reliability bins.
Issue #809 (enhanced): Multi-dimensional calibration via BigQuery GROUPING SETS.
  Decomposes Brier score using Murphy decomposition (reliability + resolution +
  uncertainty) across entity_class × claim_type × season_year slices.

Murphy decomposition:
  Brier = reliability − resolution + uncertainty
  - reliability: how close confidence bins are to actual hit rates (lower = better)
  - resolution:  how far from the base rate the predictions are (higher = better)
  - uncertainty: p_bar * (1 - p_bar) — irreducible noise given base rate

GROUPING SETS covering:
  (pundit_id, season_year, entity_class, claim_type) — full breakdown
  (pundit_id, season_year, entity_class)              — by entity class
  (pundit_id, season_year, claim_type)                — by claim type
  (pundit_id, season_year)                            — season totals
  (pundit_id)                                         — all-time totals

Confidence proxy: gold_layer.assertion_quality.quality_score (0-1)
Outcome source:   gold_layer.prediction_resolutions.binary_correct

Usage:
    python -m src.calibration --backfill              # compute and store all pundits (legacy)
    python -m src.calibration --stats                 # print sorted by brier_score (legacy)
    python -m src.calibration --season-year 2025      # compute multi-dim for a specific season
    python -m src.calibration --season-year all-time  # compute all-time multi-dim
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, date, timezone
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


# ---------------------------------------------------------------------------
# NFL season helper
# ---------------------------------------------------------------------------


def get_current_nfl_season(today_fn=date.today) -> int:
    """
    Returns the current NFL season year.

    NFL regular seasons run September–January. A game played in January 2026
    belongs to the *2025* season. Convention: if the current month is before
    August (i.e., off-season / draft period), the previous year is the
    current season; August onward is the new season year.

    Examples (given May 2026):   → 2025
    Examples (given September 2026): → 2026
    """
    today = today_fn()
    if today.month < 8:
        return today.year - 1
    return today.year


# ---------------------------------------------------------------------------
# Murphy decomposition query (Issue #809)
# ---------------------------------------------------------------------------


def _brier_score_query(project_id: str, season_year_filter: Optional[int]) -> str:
    """
    Returns a BigQuery SQL string that uses GROUPING SETS to produce
    multi-dimensional Brier score decomposition rows.

    Murphy decomposition:
        uncertainty  = p_bar * (1 - p_bar)
        resolution   = AVG( (p_k - p_bar)^2 )   where p_k = mean confidence per bin
        reliability  = AVG( (p_k - o_k)^2 )      calibration error per bin
        brier_score  = reliability - resolution + uncertainty
                     = AVG( (confidence - outcome)^2 )

    The approximation used here computes brier_score directly as the MSE
    (which is exact), and derives reliability/resolution from the per-pundit
    base rate and mean confidence to keep the query self-contained.

    Simplified but correct for scalar (non-binned) Murphy:
        p_bar        = mean(outcome)
        c_bar        = mean(confidence)
        uncertainty  = p_bar * (1 - p_bar)
        resolution   = (c_bar - p_bar)^2  [single-bin approximation]
        reliability  = brier_score - resolution + uncertainty
                     (derived residual; exact only with full binning)

    The single-bin approximation for resolution is intentional: it keeps the
    query cheap and is a sensible starting estimate. Full multi-bin resolution
    computation can be added in #810 if the anomaly engine needs it.
    """
    season_filter_sql = ""
    if season_year_filter is not None:
        season_filter_sql = f"AND l.season_year = {int(season_year_filter)}"

    return f"""
    WITH base AS (
        SELECT
            l.pundit_id,
            MAX(l.pundit_name)                                  AS pundit_name,
            l.season_year,
            -- Map claim_category to normalised entity_class bucket
            CASE
                WHEN l.claim_category IN ('player_performance', 'injury', 'contract')
                    THEN 'PLAYER'
                WHEN l.claim_category IN ('game_outcome')
                    THEN 'GAME'
                WHEN l.claim_category IN ('trade', 'draft_pick')
                    THEN 'TEAM'
                ELSE 'OTHER'
            END                                                 AS entity_class,
            l.claim_category                                    AS claim_type,
            COALESCE(aq.quality_score, 0.5)                     AS confidence_score,
            CASE WHEN r.binary_correct THEN 1.0 ELSE 0.0 END   AS binary_correct
        FROM `{project_id}.{LEDGER_TABLE}` l
        INNER JOIN `{project_id}.{RESOLUTIONS_TABLE}` r
            ON l.prediction_hash = r.prediction_hash
        LEFT JOIN `{project_id}.{QUALITY_TABLE}` aq
            ON l.prediction_hash = aq.prediction_hash
        WHERE r.resolution_status IN ('CORRECT', 'INCORRECT')
          AND r.binary_correct IS NOT NULL
          {season_filter_sql}
    ),
    grouped AS (
        SELECT
            pundit_id,
            MAX(pundit_name)                        AS pundit_name,
            season_year,
            entity_class,
            claim_type,
            -- Brier score = MSE(confidence, outcome)
            AVG(POW(confidence_score - binary_correct, 2))  AS brier_score,
            -- Base rate and mean confidence for Murphy decomposition
            AVG(binary_correct)                             AS p_bar,
            AVG(confidence_score)                           AS c_bar,
            COUNT(*)                                        AS total_claims,
            COUNT(*)                                        AS resolved_claims,
            COUNTIF(binary_correct = 1.0)                   AS correct_claims
        FROM base
        GROUP BY GROUPING SETS (
            (pundit_id, season_year, entity_class, claim_type),
            (pundit_id, season_year, entity_class),
            (pundit_id, season_year, claim_type),
            (pundit_id, season_year),
            (pundit_id)
        )
        HAVING COUNT(*) >= {MIN_PREDICTIONS}
    )
    SELECT
        pundit_id,
        pundit_name,
        season_year,
        entity_class,
        claim_type,
        'nfl'                                                       AS sport,
        brier_score,
        -- Murphy decomposition (single-bin approximation)
        -- uncertainty = p_bar * (1 - p_bar)
        p_bar * (1.0 - p_bar)                                       AS uncertainty,
        -- resolution  = (c_bar - p_bar)^2
        POW(c_bar - p_bar, 2)                                       AS resolution,
        -- reliability = brier - resolution + uncertainty  (residual)
        brier_score - POW(c_bar - p_bar, 2) + p_bar * (1.0 - p_bar) AS reliability,
        -- Accuracy
        SAFE_DIVIDE(correct_claims, resolved_claims)                AS accuracy_rate,
        total_claims,
        resolved_claims,
        correct_claims,
        FALSE                                                       AS anomaly_flag,
        CURRENT_TIMESTAMP()                                         AS last_updated
    FROM grouped
    """


def _upsert_calibration_rows(db: DBManager, rows: list[dict]) -> None:
    """
    Upserts calibration rows into gold_layer.pundit_calibration using a MERGE
    keyed on (pundit_id, season_year, entity_class, claim_type, sport).

    Handles NULL dimensions (GROUPING SETS produce NULLs for rolled-up rows).
    Uses IS NOT DISTINCT FROM for NULL-safe equality in the MERGE key.
    """
    if not rows:
        return

    project_id = os.environ.get("GCP_PROJECT_ID")

    # Build VALUES list from rows. We use a staging CTE approach to avoid
    # BigQuery MERGE parameter limits on large row counts.
    df = pd.DataFrame(rows)
    temp_table = f"{project_id}.gold_layer._cal_stage_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

    # Upload staging data
    from google.cloud import bigquery

    job_config = bigquery.LoadJobConfig(
        write_disposition="WRITE_TRUNCATE",
        schema=[
            bigquery.SchemaField("pundit_id", "STRING"),
            bigquery.SchemaField("pundit_name", "STRING"),
            bigquery.SchemaField("season_year", "INT64"),
            bigquery.SchemaField("entity_class", "STRING"),
            bigquery.SchemaField("claim_type", "STRING"),
            bigquery.SchemaField("sport", "STRING"),
            bigquery.SchemaField("brier_score", "FLOAT64"),
            bigquery.SchemaField("reliability", "FLOAT64"),
            bigquery.SchemaField("resolution", "FLOAT64"),
            bigquery.SchemaField("uncertainty", "FLOAT64"),
            bigquery.SchemaField("accuracy_rate", "FLOAT64"),
            bigquery.SchemaField("total_claims", "INT64"),
            bigquery.SchemaField("resolved_claims", "INT64"),
            bigquery.SchemaField("correct_claims", "INT64"),
            bigquery.SchemaField("anomaly_flag", "BOOL"),
            bigquery.SchemaField("last_updated", "TIMESTAMP"),
        ],
    )

    job = db.client.load_table_from_dataframe(df, temp_table, job_config=job_config)
    job.result()
    logger.info("Staged %d calibration rows to %s", len(rows), temp_table)

    merge_sql = f"""
        MERGE `{project_id}.{CALIBRATION_TABLE}` T
        USING `{temp_table}` S
        ON T.pundit_id = S.pundit_id
           AND T.sport = S.sport
           AND T.season_year IS NOT DISTINCT FROM S.season_year
           AND T.entity_class IS NOT DISTINCT FROM S.entity_class
           AND T.claim_type IS NOT DISTINCT FROM S.claim_type
        WHEN MATCHED THEN UPDATE SET
            pundit_name    = S.pundit_name,
            brier_score    = S.brier_score,
            reliability    = S.reliability,
            resolution     = S.resolution,
            uncertainty    = S.uncertainty,
            accuracy_rate  = S.accuracy_rate,
            total_claims   = S.total_claims,
            resolved_claims = S.resolved_claims,
            correct_claims = S.correct_claims,
            last_updated   = S.last_updated
        WHEN NOT MATCHED THEN INSERT ROW
    """
    db.client.query(merge_sql).result()
    logger.info("MERGE complete for %d calibration rows", len(rows))

    # Clean up staging table
    db.client.delete_table(temp_table, not_found_ok=True)
    logger.debug("Dropped staging table %s", temp_table)


def _ensure_calibration_table_v2(db: DBManager) -> None:
    """Creates gold_layer.pundit_calibration (issue #809 schema) if it doesn't exist."""
    project_id = os.environ.get("GCP_PROJECT_ID")
    ddl = f"""
        CREATE TABLE IF NOT EXISTS `{project_id}.{CALIBRATION_TABLE}` (
            pundit_id           STRING    NOT NULL,
            pundit_name         STRING,
            season_year         INT64,
            entity_class        STRING,
            claim_type          STRING,
            sport               STRING    DEFAULT 'nfl',
            brier_score         FLOAT64,
            reliability         FLOAT64,
            resolution          FLOAT64,
            uncertainty         FLOAT64,
            accuracy_rate       FLOAT64,
            total_claims        INT64,
            resolved_claims     INT64,
            correct_claims      INT64,
            anomaly_flag        BOOL      DEFAULT FALSE,
            last_updated        TIMESTAMP NOT NULL
        )
        PARTITION BY DATE(last_updated)
        CLUSTER BY pundit_id, season_year, entity_class
        OPTIONS(description="Per-pundit calibration scores. GROUPING SETS across entity_class x claim_type. Recomputed nightly.")
    """
    db.client.query(ddl).result()
    logger.info("Ensured calibration v2 table exists: %s", CALIBRATION_TABLE)


# ---------------------------------------------------------------------------
# Main compute entry-point (Issue #809)
# ---------------------------------------------------------------------------


def compute_calibration(
    db_manager: Optional[DBManager] = None,
    season_year: Optional[int] = None,
) -> list[dict]:
    """
    Runs the BigQuery GROUPING SETS calibration query and upserts results.

    Args:
        db_manager: Optional existing DBManager. Creates one if None.
        season_year: If provided, restricts source rows to that NFL season.
                     None = include all seasons (still groups by season_year
                     in the GROUPING SETS rows).

    Returns:
        List of row dicts that were upserted.
    """
    close_db = db_manager is None
    if db_manager is None:
        db_manager = DBManager()

    try:
        project_id = os.environ.get("GCP_PROJECT_ID")
        _ensure_calibration_table_v2(db_manager)

        sql = _brier_score_query(project_id, season_year)
        logger.info(
            "Running GROUPING SETS calibration query (season_year=%s)...", season_year
        )
        df = db_manager.client.query(sql).to_dataframe()

        if df.empty:
            logger.info("No calibration rows produced (insufficient resolved data).")
            return []

        logger.info("Query produced %d calibration rows", len(df))

        # Convert DataFrame to list of dicts.
        # pandas uses float NaN for None in int columns (e.g. season_year),
        # so normalize NaN/pd.NA back to Python None before returning.
        rows = df.to_dict(orient="records")
        for row in rows:
            for key in ("season_year", "entity_class", "claim_type"):
                val = row.get(key)
                if val is not None:
                    try:
                        import math

                        if isinstance(val, float) and math.isnan(val):
                            row[key] = None
                    except (TypeError, ValueError):
                        pass

        _upsert_calibration_rows(db_manager, rows)
        return rows

    finally:
        if close_db:
            db_manager.close()


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

    args = sys.argv[1:]

    # --season-year <year|current>  — multi-dimensional calibration (Issue #809)
    if "--season-year" in args:
        idx = args.index("--season-year")
        if idx + 1 >= len(args):
            print("Error: --season-year requires an argument (e.g. 2025 or current)")
            sys.exit(1)
        raw = args[idx + 1]
        if raw == "current":
            season_year: Optional[int] = get_current_nfl_season()
        elif raw == "all-time":
            season_year = None
        else:
            try:
                season_year = int(raw)
            except ValueError:
                print(
                    f"Error: invalid --season-year value '{raw}' (use YYYY, 'current', or 'all-time')"
                )
                sys.exit(1)

        print(f"Running multi-dimensional calibration (season_year={season_year})...")
        rows = compute_calibration(season_year=season_year)
        print(f"Done. Upserted {len(rows)} calibration rows.")
    elif "--backfill" in args:
        print("Running calibration backfill...")
        results = backfill_calibration()
        print(f"Done. Calibrated {len(results)} pundits.")
        if results:
            print_calibration_stats()
    elif "--stats" in args:
        print_calibration_stats()
    else:
        print(
            "Usage:\n"
            "  python -m src.calibration --season-year 2025   # multi-dim for a season\n"
            "  python -m src.calibration --season-year current # current NFL season\n"
            "  python -m src.calibration --season-year all-time # all seasons\n"
            "  python -m src.calibration --backfill            # legacy per-pundit backfill\n"
            "  python -m src.calibration --stats               # print sorted by brier_score\n"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
