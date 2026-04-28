"""
Pundit Prediction Scoring — Issue #340

Signed combined score formula:

    score = correctness_sign × (1 + λ_n·novelty) × (1 + λ_c·confidence) × stakes

Where:
  - correctness_sign: +1 (CORRECT), 0 (VOID), −1 (INCORRECT)
  - λ_n = 0.5  (novelty boost weight — configurable)
  - λ_c = 0.5  (confidence boost weight — configurable)
  - novelty: 0.0–1.0 (contrarian premium; 0.5 default until novelty module is built)
  - confidence: 0.0–1.0 (quality_score from gold_layer.assertion_quality as proxy)
  - stakes: category weight (draft_pick=1.5, …, fa_signing=0.7)

CLI:
  python -m src.scoring --backfill   # compute and write all scores to BigQuery
  python -m src.scoring --stats      # print pundit aggregate stats + top 5
"""

import argparse
import logging
import os
import statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
from google.cloud import bigquery

from src.db_manager import DBManager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LAMBDA_NOVELTY: float = 0.5
LAMBDA_CONFIDENCE: float = 0.5

# Default novelty until the novelty-detection module is built (Issue #341 TBD)
DEFAULT_NOVELTY: float = 0.5

STAKES_BY_CATEGORY: dict[str, float] = {
    "draft_pick": 1.5,
    "player_performance": 1.0,
    "game_outcome": 1.0,
    "contract": 0.8,
    "trade": 0.8,
    "fa_signing": 0.7,
}
DEFAULT_STAKES: float = 1.0

CLAIM_SCORES_TABLE = "gold_layer.claim_scores"
LEDGER_TABLE = "gold_layer.prediction_ledger"
RESOLUTIONS_TABLE = "gold_layer.prediction_resolutions"
QUALITY_TABLE = "gold_layer.assertion_quality"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class ClaimScore:
    """Scored outcome for a single resolved prediction claim."""

    prediction_hash: str
    pundit_id: str
    pundit_name: str
    correctness_sign: float  # +1.0, 0.0, or -1.0
    novelty: float  # 0.0–1.0
    confidence: float  # 0.0–1.0  (quality_score proxy)
    stakes: float  # 0.5–2.0
    raw_score: float
    computed_at: str  # ISO-8601 UTC


# ---------------------------------------------------------------------------
# Core scoring helpers
# ---------------------------------------------------------------------------


def correctness_sign(resolution_status: str) -> float:
    """Convert resolution status string to ±1 / 0 multiplier."""
    s = resolution_status.upper()
    if s == "CORRECT":
        return 1.0
    if s == "INCORRECT":
        return -1.0
    # VOID or anything else → 0
    return 0.0


def category_stakes(claim_category: Optional[str]) -> float:
    """Return the stakes multiplier for a claim category."""
    if not claim_category:
        return DEFAULT_STAKES
    return STAKES_BY_CATEGORY.get(claim_category.lower(), DEFAULT_STAKES)


def compute_claim_score(
    resolution_status: str,
    claim_category: Optional[str] = None,
    quality_score: float = 0.5,
    novelty: float = DEFAULT_NOVELTY,
    lambda_n: float = LAMBDA_NOVELTY,
    lambda_c: float = LAMBDA_CONFIDENCE,
) -> float:
    """
    Compute the signed combined score for a single resolved prediction.

    score = sign × (1 + λ_n·novelty) × (1 + λ_c·confidence) × stakes

    Args:
        resolution_status: "CORRECT", "INCORRECT", or "VOID"
        claim_category:    Category string (e.g. "draft_pick") for stakes lookup
        quality_score:     0.0–1.0 proxy for prediction confidence (from assertion_quality)
        novelty:           0.0–1.0 contrarian premium (default 0.5 until module exists)
        lambda_n:          Weight for novelty bonus (default LAMBDA_NOVELTY = 0.5)
        lambda_c:          Weight for confidence bonus (default LAMBDA_CONFIDENCE = 0.5)

    Returns:
        Float score in range [-(1+λ_n)(1+λ_c)·max_stakes, +(1+λ_n)(1+λ_c)·max_stakes]
        VOID predictions always return 0.0.
    """
    sign = correctness_sign(resolution_status)
    if sign == 0.0:
        return 0.0

    stakes = category_stakes(claim_category)
    novelty_factor = 1.0 + lambda_n * max(0.0, min(1.0, novelty))
    confidence_factor = 1.0 + lambda_c * max(0.0, min(1.0, quality_score))

    return sign * novelty_factor * confidence_factor * stakes


# ---------------------------------------------------------------------------
# Aggregate helpers
# ---------------------------------------------------------------------------


def compute_pundit_aggregate(claim_scores: list[float]) -> dict:
    """
    Compute aggregate stats over a list of raw scores for a single pundit.

    Returns dict with keys: mean, std, count, positive_rate.
    """
    n = len(claim_scores)
    if n == 0:
        return {"mean": 0.0, "std": 0.0, "count": 0, "positive_rate": 0.0}

    mean = sum(claim_scores) / n
    std = statistics.pstdev(claim_scores) if n > 1 else 0.0
    positive_rate = sum(1 for s in claim_scores if s > 0) / n

    return {
        "mean": mean,
        "std": std,
        "count": n,
        "positive_rate": positive_rate,
    }


# ---------------------------------------------------------------------------
# BigQuery I/O
# ---------------------------------------------------------------------------


def _full(table: str, project_id: str) -> str:
    return f"`{project_id}.{table}`"


def _ensure_claim_scores_table(db: DBManager, project_id: str) -> None:
    """Create gold_layer.claim_scores if it does not exist."""
    ddl = f"""
        CREATE TABLE IF NOT EXISTS `{project_id}.{CLAIM_SCORES_TABLE}` (
            prediction_hash  STRING    NOT NULL,
            pundit_id        STRING,
            pundit_name      STRING,
            correctness_sign FLOAT64,
            novelty          FLOAT64,
            confidence       FLOAT64,
            stakes           FLOAT64,
            raw_score        FLOAT64,
            computed_at      TIMESTAMP
        )
        PARTITION BY DATE(computed_at)
        OPTIONS (require_partition_filter = FALSE)
    """
    db.execute(ddl)
    logger.info("Ensured table %s exists", CLAIM_SCORES_TABLE)


def fetch_resolved_predictions(db: DBManager, project_id: str) -> pd.DataFrame:
    """
    Join prediction_ledger + prediction_resolutions + assertion_quality to get
    all resolved (CORRECT / INCORRECT / VOID) predictions with quality_score.
    """
    query = f"""
        SELECT
            l.prediction_hash,
            l.pundit_id,
            l.pundit_name,
            l.claim_category,
            r.resolution_status,
            COALESCE(q.quality_score, 0.5) AS quality_score
        FROM {_full(LEDGER_TABLE, project_id)} l
        INNER JOIN {_full(RESOLUTIONS_TABLE, project_id)} r
            ON l.prediction_hash = r.prediction_hash
        LEFT JOIN {_full(QUALITY_TABLE, project_id)} q
            ON l.prediction_hash = q.prediction_hash
        WHERE r.resolution_status IN ('CORRECT', 'INCORRECT', 'VOID')
    """
    return db.fetch_df(query)


def write_claim_scores(scores: list[ClaimScore], db: DBManager, project_id: str) -> int:
    """
    Write ClaimScore records to gold_layer.claim_scores using INSERT OVERWRITE
    (full replace so backfills are idempotent).

    Returns the number of rows written.
    """
    if not scores:
        logger.warning("No scores to write — skipping BigQuery write")
        return 0

    rows = [
        {
            "prediction_hash": s.prediction_hash,
            "pundit_id": s.pundit_id,
            "pundit_name": s.pundit_name,
            "correctness_sign": s.correctness_sign,
            "novelty": s.novelty,
            "confidence": s.confidence,
            "stakes": s.stakes,
            "raw_score": s.raw_score,
            "computed_at": s.computed_at,
        }
        for s in scores
    ]

    df = pd.DataFrame(rows)
    df["computed_at"] = pd.to_datetime(df["computed_at"], utc=True)

    table_ref = f"{project_id}.{CLAIM_SCORES_TABLE}"
    job_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        schema=[
            bigquery.SchemaField("prediction_hash", "STRING"),
            bigquery.SchemaField("pundit_id", "STRING"),
            bigquery.SchemaField("pundit_name", "STRING"),
            bigquery.SchemaField("correctness_sign", "FLOAT64"),
            bigquery.SchemaField("novelty", "FLOAT64"),
            bigquery.SchemaField("confidence", "FLOAT64"),
            bigquery.SchemaField("stakes", "FLOAT64"),
            bigquery.SchemaField("raw_score", "FLOAT64"),
            bigquery.SchemaField("computed_at", "TIMESTAMP"),
        ],
    )
    load_job = db.client.load_table_from_dataframe(df, table_ref, job_config=job_config)
    load_job.result()
    logger.info("Wrote %d claim scores to %s", len(scores), CLAIM_SCORES_TABLE)
    return len(scores)


# ---------------------------------------------------------------------------
# High-level orchestration
# ---------------------------------------------------------------------------


def run_backfill(db: Optional[DBManager] = None) -> list[ClaimScore]:
    """
    Compute scores for all resolved predictions and write to BigQuery.

    Returns list of ClaimScore objects.
    """
    close_db = db is None
    if db is None:
        db = DBManager()

    try:
        project_id = os.environ.get("GCP_PROJECT_ID", "cap-alpha-protocol")
        _ensure_claim_scores_table(db, project_id)

        df = fetch_resolved_predictions(db, project_id)
        if df.empty:
            logger.warning("No resolved predictions found — nothing to score")
            return []

        now = datetime.now(timezone.utc).isoformat()
        scores: list[ClaimScore] = []
        for _, row in df.iterrows():
            sign = correctness_sign(row["resolution_status"])
            conf = float(row.get("quality_score", 0.5))
            novelty = DEFAULT_NOVELTY
            stakes = category_stakes(row.get("claim_category"))
            raw = compute_claim_score(
                resolution_status=row["resolution_status"],
                claim_category=row.get("claim_category"),
                quality_score=conf,
                novelty=novelty,
            )
            scores.append(
                ClaimScore(
                    prediction_hash=row["prediction_hash"],
                    pundit_id=str(row.get("pundit_id", "")),
                    pundit_name=str(row.get("pundit_name", "")),
                    correctness_sign=sign,
                    novelty=novelty,
                    confidence=conf,
                    stakes=stakes,
                    raw_score=raw,
                    computed_at=now,
                )
            )

        write_claim_scores(scores, db, project_id)
        return scores
    finally:
        if close_db:
            db.close()


def get_pundit_stats(
    scores: Optional[list[ClaimScore]] = None,
    db: Optional[DBManager] = None,
) -> pd.DataFrame:
    """
    Return a DataFrame with per-pundit aggregate stats, sorted by composite_score desc.

    If scores is None, fetches from BigQuery claim_scores table.
    """
    if scores is not None:
        df_src = pd.DataFrame(
            [
                {
                    "pundit_id": s.pundit_id,
                    "pundit_name": s.pundit_name,
                    "raw_score": s.raw_score,
                }
                for s in scores
            ]
        )
    else:
        close_db = db is None
        if db is None:
            db = DBManager()
        try:
            project_id = os.environ.get("GCP_PROJECT_ID", "cap-alpha-protocol")
            query = f"""
                SELECT pundit_id, pundit_name, raw_score
                FROM {_full(CLAIM_SCORES_TABLE, project_id)}
            """
            df_src = db.fetch_df(query)
        finally:
            if close_db:
                db.close()

    if df_src.empty:
        return pd.DataFrame(
            columns=[
                "pundit_id",
                "pundit_name",
                "composite_score",
                "std",
                "count",
                "positive_rate",
            ]
        )

    rows = []
    for (pundit_id, pundit_name), grp in df_src.groupby(
        ["pundit_id", "pundit_name"], sort=False
    ):
        agg = compute_pundit_aggregate(grp["raw_score"].tolist())
        rows.append(
            {
                "pundit_id": pundit_id,
                "pundit_name": pundit_name,
                "composite_score": agg["mean"],
                "std": agg["std"],
                "count": agg["count"],
                "positive_rate": agg["positive_rate"],
            }
        )

    result = pd.DataFrame(rows).sort_values("composite_score", ascending=False)
    return result.reset_index(drop=True)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _cli() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Pundit scoring — backfill or stats")
    parser.add_argument(
        "--backfill",
        action="store_true",
        help="Compute and write all claim scores to BigQuery",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Print pundit aggregate stats (top 5 by composite score)",
    )
    args = parser.parse_args()

    if not args.backfill and not args.stats:
        parser.print_help()
        return

    scores: Optional[list[ClaimScore]] = None

    if args.backfill:
        print("Running backfill…")
        scores = run_backfill()
        print(f"Scored {len(scores)} predictions.")

    if args.stats:
        stats_df = get_pundit_stats(scores=scores)
        if stats_df.empty:
            print("No pundit scores found.")
            return

        print("\nTop 5 pundits by composite score:")
        print("-" * 70)
        top5 = stats_df.head(5)
        for _, row in top5.iterrows():
            print(
                f"  {row['pundit_name']:<30} "
                f"composite={row['composite_score']:+.4f}  "
                f"n={int(row['count'])}  "
                f"hit%={row['positive_rate']:.0%}"
            )
        print("-" * 70)


if __name__ == "__main__":
    _cli()
