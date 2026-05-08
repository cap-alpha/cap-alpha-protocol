"""
Market Timing — Phase 1 (Issue #811)

Computes per-pundit publication lead-time statistics as a proxy for market
timing awareness. Lead time = hours between when a claim was ingested and
when the predicted event was resolved. A pundit who consistently publishes
days before resolution is a faster market signal than one who publishes hours
before.

Pipeline:
  gold_layer.prediction_ledger
    JOIN gold_layer.prediction_resolutions (CORRECT|INCORRECT only, excludes VOID)
      → PERCENTILE_CONT(0.5) OVER (...) per pundit × entity_class × claim_type × sport
        → MERGE INTO gold_layer.pundit_market_timing

Lead-time is intentionally a neutral metric at Phase 1 — we record how far
ahead each pundit tends to publish, not whether that timing correlates with
market prices. Phase 2 will correlate with Vegas lines and trade-deadline
movement.

Usage:
    python -m src.market_timing                  # run full refresh
    python -m src.market_timing --dry-run        # print SQL only, no writes
    python -m src.market_timing --summary        # print current BQ summary

BigQuery SQL conventions (BQ-native only):
  - STRING not VARCHAR
  - FLOAT64, INT64
  - SAFE_CAST not TRY_CAST
  - TIMESTAMP_DIFF(..., HOUR) not DATEDIFF
  - PERCENTILE_CONT is a BQ analytic function
  - MOD() not %
"""

import argparse
import logging
from datetime import datetime, timezone

from src.db_manager import DBManager

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
logger = logging.getLogger(__name__)

LEDGER_TABLE = "gold_layer.prediction_ledger"
RESOLUTIONS_TABLE = "gold_layer.prediction_resolutions"
MARKET_TIMING_TABLE = "gold_layer.pundit_market_timing"

# Claim categories that map directly to entity classes for grouping.
# We derive entity_class from claim_category using a CASE expression in BQ.
ENTITY_CLASS_SQL = """
  CASE claim_category
    WHEN 'trade'              THEN 'player'
    WHEN 'injury'             THEN 'player'
    WHEN 'contract'           THEN 'player'
    WHEN 'draft_pick'         THEN 'draft_pick'
    WHEN 'player_performance' THEN 'player'
    WHEN 'game_outcome'       THEN 'game'
    ELSE 'other'
  END
"""


def _build_merge_sql(project_id: str, computed_at_ts: str) -> str:
    """
    Return the MERGE DML that upserts per-pundit market timing rows.

    The outer query computes median lead hours using PERCENTILE_CONT(0.5) as an
    analytic function over the full window, then collapses to one row per group
    using MIN() (all rows in the partition have identical values).

    Args:
        project_id: GCP project ID.
        computed_at_ts: ISO-8601 UTC string for the batch timestamp.

    Returns:
        BQ-native MERGE SQL string.
    """
    return f"""
MERGE `{project_id}.gold_layer.pundit_market_timing` AS target
USING (
  -- Step 1: join ledger to resolutions, compute raw lead hours
  WITH base AS (
    SELECT
      l.pundit_id,
      {ENTITY_CLASS_SQL}                                         AS entity_class,
      COALESCE(l.claim_category, 'other')                        AS claim_type,
      COALESCE(l.sport, 'NFL')                                   AS sport,
      TIMESTAMP_DIFF(r.resolved_at, l.ingestion_timestamp, HOUR) AS lead_hours
    FROM `{project_id}.{LEDGER_TABLE}` AS l
    INNER JOIN `{project_id}.{RESOLUTIONS_TABLE}` AS r
      ON l.prediction_hash = r.prediction_hash
    WHERE
      r.resolution_status IN ('CORRECT', 'INCORRECT')
      AND r.resolved_at IS NOT NULL
      AND l.ingestion_timestamp IS NOT NULL
      -- Only include non-negative lead times (claim ingested before resolution)
      AND TIMESTAMP_DIFF(r.resolved_at, l.ingestion_timestamp, HOUR) >= 0
  ),

  -- Step 2: compute per-group median using PERCENTILE_CONT analytic function
  with_median AS (
    SELECT
      pundit_id,
      entity_class,
      claim_type,
      sport,
      PERCENTILE_CONT(lead_hours, 0.5)
        OVER (PARTITION BY pundit_id, entity_class, claim_type, sport) AS median_lead_hours,
      COUNT(*) OVER (PARTITION BY pundit_id, entity_class, claim_type, sport) AS sample_size
    FROM base
  ),

  -- Step 3: collapse to one row per group
  aggregated AS (
    SELECT
      pundit_id,
      entity_class,
      claim_type,
      sport,
      MIN(median_lead_hours) AS median_lead_hours,
      MIN(sample_size)       AS sample_size
    FROM with_median
    GROUP BY pundit_id, entity_class, claim_type, sport
  )

  SELECT
    pundit_id,
    entity_class,
    claim_type,
    sport,
    CAST(median_lead_hours AS FLOAT64)   AS median_lead_hours,
    CAST(sample_size AS INT64)           AS sample_size,
    TIMESTAMP('{computed_at_ts}')        AS computed_at
  FROM aggregated
  WHERE sample_size >= 1
) AS source

ON (
  target.pundit_id    = source.pundit_id
  AND target.entity_class = source.entity_class
  AND target.claim_type   = source.claim_type
  AND target.sport        = source.sport
  AND DATE(target.computed_at) = DATE(source.computed_at)
)

WHEN MATCHED THEN
  UPDATE SET
    median_lead_hours = source.median_lead_hours,
    sample_size       = source.sample_size,
    computed_at       = source.computed_at

WHEN NOT MATCHED THEN
  INSERT (
    pundit_id,
    entity_class,
    claim_type,
    sport,
    median_lead_hours,
    sample_size,
    computed_at
  )
  VALUES (
    source.pundit_id,
    source.entity_class,
    source.claim_type,
    source.sport,
    source.median_lead_hours,
    source.sample_size,
    source.computed_at
  );
"""


def compute_market_timing(
    db: DBManager,
    *,
    dry_run: bool = False,
    computed_at: datetime | None = None,
) -> int:
    """
    Compute per-pundit lead-time aggregates and MERGE into pundit_market_timing.

    Args:
        db: Initialized DBManager (BigQuery).
        dry_run: If True, log the SQL but do not execute it.
        computed_at: Override the batch timestamp (default: now UTC).

    Returns:
        Number of rows affected (0 in dry_run mode).
    """
    if computed_at is None:
        computed_at = datetime.now(timezone.utc)

    computed_at_ts = computed_at.strftime("%Y-%m-%dT%H:%M:%S")
    project_id = db.project_id

    logger.info(
        f"[market_timing] computing lead-time aggregates "
        f"(project={project_id}, computed_at={computed_at_ts}, dry_run={dry_run})"
    )

    sql = _build_merge_sql(project_id=project_id, computed_at_ts=computed_at_ts)

    if dry_run:
        logger.info(f"[market_timing] DRY RUN — SQL:\n{sql}")
        return 0

    result = db.execute(sql)
    # BigQuery DML returns affected rows via job statistics
    try:
        job = result.job
        rows_affected = (
            job.num_dml_affected_rows if job.num_dml_affected_rows is not None else 0
        )
    except AttributeError:
        rows_affected = 0

    logger.info(f"[market_timing] MERGE complete — {rows_affected} rows affected")
    return rows_affected


def get_market_timing_summary(db: DBManager) -> None:
    """Print a summary of current pundit_market_timing rows to stdout."""
    project_id = db.project_id
    sql = f"""
    SELECT
      sport,
      claim_type,
      COUNT(DISTINCT pundit_id)          AS pundit_count,
      ROUND(AVG(median_lead_hours), 1)   AS avg_median_lead_hours,
      SUM(sample_size)                   AS total_predictions,
      MAX(DATE(computed_at))             AS last_computed
    FROM `{project_id}.{MARKET_TIMING_TABLE}`
    GROUP BY sport, claim_type
    ORDER BY sport, avg_median_lead_hours DESC
    """
    df = db.fetch_df(sql)
    if df.empty:
        logger.info("[market_timing] No rows in pundit_market_timing yet.")
        return
    print("\n=== Pundit Market Timing Summary ===")
    print(df.to_string(index=False))
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compute per-pundit market lead-time aggregates (Issue #811)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the MERGE SQL but do not execute it.",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print current pundit_market_timing summary and exit.",
    )
    args = parser.parse_args()

    db = DBManager()

    if args.summary:
        get_market_timing_summary(db)
        return

    compute_market_timing(db, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
