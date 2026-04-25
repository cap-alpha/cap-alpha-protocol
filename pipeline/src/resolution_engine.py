"""
Prediction Resolution Engine (Issue #112)

Matches hashed predictions from gold_layer.prediction_ledger against actual NFL
outcomes to automatically score pundit accuracy.

Resolution states: PENDING | CORRECT | INCORRECT | VOID

Scoring:
  - Brier score for probabilistic claims (lower is better; 0 = perfect, 1 = worst)
  - Binary accuracy for yes/no predictions
  - Timeliness weight: predictions made further in advance score higher
"""

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
from google.cloud import bigquery

from src.db_manager import DBManager

logger = logging.getLogger(__name__)

LEDGER_TABLE = "gold_layer.prediction_ledger"
RESOLUTIONS_TABLE = "gold_layer.prediction_resolutions"

# Timeliness weight thresholds (days before outcome)
TIMELINESS_WEIGHTS = [
    (365, 2.0),  # 1+ year out
    (90, 1.5),  # 3+ months out
    (30, 1.25),  # 1+ month out
    (7, 1.1),  # 1+ week out
    (0, 1.0),  # baseline
]


@dataclass
class ResolutionResult:
    prediction_hash: str
    resolution_status: str  # CORRECT | INCORRECT | VOID
    resolver: str  # auto | manual
    brier_score: Optional[float] = None
    binary_correct: Optional[bool] = None
    timeliness_weight: float = 1.0
    weighted_score: Optional[float] = None
    outcome_source: Optional[str] = None
    outcome_reference_id: Optional[str] = None
    outcome_notes: Optional[str] = None


def _compute_timeliness_weight(prediction_ts: datetime, outcome_ts: datetime) -> float:
    """Returns a weight multiplier based on how far in advance the prediction was made."""
    if outcome_ts <= prediction_ts:
        return 1.0
    days_ahead = (outcome_ts - prediction_ts).days
    for threshold, weight in TIMELINESS_WEIGHTS:
        if days_ahead >= threshold:
            return weight
    return 1.0


def _compute_brier_score(predicted_prob: float, outcome: bool) -> float:
    """Brier score: (predicted_prob - actual_outcome)^2. Range [0, 1]."""
    actual = 1.0 if outcome else 0.0
    return (predicted_prob - actual) ** 2


def _compute_weighted_score(
    binary_correct: Optional[bool],
    brier_score: Optional[float],
    timeliness_weight: float,
) -> Optional[float]:
    """Combines accuracy score and timeliness into a single weighted metric."""
    if brier_score is not None:
        # Invert Brier (1 - brier so higher = better) then weight
        return (1.0 - brier_score) * timeliness_weight
    if binary_correct is not None:
        return (1.0 if binary_correct else 0.0) * timeliness_weight
    return None


def record_resolution(result: ResolutionResult, db: Optional[DBManager] = None) -> None:
    """
    Writes or updates a resolution record in gold_layer.prediction_resolutions.
    Uses MERGE to upsert — resolutions can be updated as new evidence arrives.
    """
    close_db = db is None
    if db is None:
        db = DBManager()

    try:
        project_id = os.environ.get("GCP_PROJECT_ID")
        now = datetime.now(timezone.utc).isoformat()

        brier = f"{result.brier_score}" if result.brier_score is not None else "NULL"
        binary = (
            "TRUE"
            if result.binary_correct is True
            else "FALSE" if result.binary_correct is False else "NULL"
        )
        weighted = (
            f"{result.weighted_score}" if result.weighted_score is not None else "NULL"
        )

        def _q(s: Optional[str]) -> str:
            if s is None:
                return "NULL"
            return "'" + s.replace("'", "\\'") + "'"

        merge_sql = f"""
            MERGE `{project_id}.{RESOLUTIONS_TABLE}` T
            USING (SELECT '{result.prediction_hash}' AS prediction_hash) S
            ON T.prediction_hash = S.prediction_hash
            WHEN MATCHED THEN UPDATE SET
                resolution_status     = '{result.resolution_status}',
                resolved_at           = '{now}',
                resolver              = '{result.resolver}',
                brier_score           = {brier},
                binary_correct        = {binary},
                timeliness_weight     = {result.timeliness_weight},
                weighted_score        = {weighted},
                outcome_source        = {_q(result.outcome_source)},
                outcome_reference_id  = {_q(result.outcome_reference_id)},
                outcome_notes         = {_q(result.outcome_notes)},
                updated_at            = '{now}'
            WHEN NOT MATCHED THEN INSERT (
                prediction_hash, resolution_status, resolved_at, resolver,
                brier_score, binary_correct, timeliness_weight, weighted_score,
                outcome_source, outcome_reference_id, outcome_notes,
                created_at, updated_at
            ) VALUES (
                '{result.prediction_hash}', '{result.resolution_status}', '{now}', '{result.resolver}',
                {brier}, {binary}, {result.timeliness_weight}, {weighted},
                {_q(result.outcome_source)}, {_q(result.outcome_reference_id)}, {_q(result.outcome_notes)},
                '{now}', '{now}'
            )
        """
        db.execute(merge_sql)
        logger.info(
            f"Recorded resolution for {result.prediction_hash[:16]}…: "
            f"{result.resolution_status} (resolver={result.resolver})"
        )
    finally:
        if close_db:
            db.close()


def resolve_manual(
    prediction_hash: str,
    correct: bool,
    outcome_notes: str,
    outcome_source: str = "manual",
    prediction_ts: Optional[datetime] = None,
    outcome_ts: Optional[datetime] = None,
    db: Optional[DBManager] = None,
) -> ResolutionResult:
    """
    Manually resolve a prediction as CORRECT or INCORRECT.
    Used for edge cases where auto-resolution cannot determine the outcome.
    """
    status = "CORRECT" if correct else "INCORRECT"
    weight = 1.0
    if prediction_ts and outcome_ts:
        weight = _compute_timeliness_weight(prediction_ts, outcome_ts)

    result = ResolutionResult(
        prediction_hash=prediction_hash,
        resolution_status=status,
        resolver="manual",
        binary_correct=correct,
        timeliness_weight=weight,
        weighted_score=_compute_weighted_score(correct, None, weight),
        outcome_source=outcome_source,
        outcome_notes=outcome_notes,
    )
    record_resolution(result, db=db)
    return result


def resolve_binary(
    prediction_hash: str,
    correct: bool,
    outcome_source: str,
    outcome_reference_id: Optional[str] = None,
    outcome_notes: Optional[str] = None,
    prediction_ts: Optional[datetime] = None,
    outcome_ts: Optional[datetime] = None,
    db: Optional[DBManager] = None,
) -> ResolutionResult:
    """Auto-resolve a yes/no prediction as CORRECT or INCORRECT."""
    weight = 1.0
    if prediction_ts and outcome_ts:
        weight = _compute_timeliness_weight(prediction_ts, outcome_ts)

    result = ResolutionResult(
        prediction_hash=prediction_hash,
        resolution_status="CORRECT" if correct else "INCORRECT",
        resolver="auto",
        binary_correct=correct,
        timeliness_weight=weight,
        weighted_score=_compute_weighted_score(correct, None, weight),
        outcome_source=outcome_source,
        outcome_reference_id=outcome_reference_id,
        outcome_notes=outcome_notes,
    )
    record_resolution(result, db=db)
    return result


def resolve_probabilistic(
    prediction_hash: str,
    predicted_prob: float,
    actual_outcome: bool,
    outcome_source: str,
    outcome_reference_id: Optional[str] = None,
    outcome_notes: Optional[str] = None,
    prediction_ts: Optional[datetime] = None,
    outcome_ts: Optional[datetime] = None,
    db: Optional[DBManager] = None,
) -> ResolutionResult:
    """Auto-resolve a probabilistic prediction using Brier score."""
    brier = _compute_brier_score(predicted_prob, actual_outcome)
    weight = 1.0
    if prediction_ts and outcome_ts:
        weight = _compute_timeliness_weight(prediction_ts, outcome_ts)

    status = "CORRECT" if actual_outcome else "INCORRECT"
    result = ResolutionResult(
        prediction_hash=prediction_hash,
        resolution_status=status,
        resolver="auto",
        brier_score=brier,
        timeliness_weight=weight,
        weighted_score=_compute_weighted_score(None, brier, weight),
        outcome_source=outcome_source,
        outcome_reference_id=outcome_reference_id,
        outcome_notes=outcome_notes,
    )
    record_resolution(result, db=db)
    return result


def void_prediction(
    prediction_hash: str,
    reason: str,
    db: Optional[DBManager] = None,
) -> ResolutionResult:
    """Mark a prediction as VOID (unresolvable — e.g. player injured before outcome)."""
    result = ResolutionResult(
        prediction_hash=prediction_hash,
        resolution_status="VOID",
        resolver="manual",
        outcome_notes=reason,
    )
    record_resolution(result, db=db)
    return result


def get_pending_predictions(
    sport: Optional[str] = None, db: Optional[DBManager] = None
) -> pd.DataFrame:
    """
    Returns all PENDING predictions from the ledger that don't yet have a resolution.
    Used by automated resolution jobs to find work to do.
    Pass sport='NFL' to filter to a specific sport; omit for all sports.
    """
    close_db = db is None
    if db is None:
        db = DBManager()

    try:
        project_id = os.environ.get("GCP_PROJECT_ID")
        sport_filter = f"AND COALESCE(l.sport, 'NFL') = '{sport}'" if sport else ""
        query = f"""
            SELECT
                l.prediction_hash,
                l.pundit_id,
                l.pundit_name,
                l.extracted_claim,
                l.claim_category,
                l.season_year,
                l.target_player_id,
                l.target_team,
                COALESCE(l.sport, 'NFL') AS sport,
                l.ingestion_timestamp
            FROM `{project_id}.{LEDGER_TABLE}` l
            LEFT JOIN `{project_id}.{RESOLUTIONS_TABLE}` r
                ON l.prediction_hash = r.prediction_hash
            WHERE (r.prediction_hash IS NULL OR r.resolution_status = 'PENDING')
              {sport_filter}
            ORDER BY l.ingestion_timestamp ASC
        """
        return db.fetch_df(query)
    finally:
        if close_db:
            db.close()


def get_pundit_accuracy_summary(
    sport: Optional[str] = None, db: Optional[DBManager] = None
) -> pd.DataFrame:
    """
    Returns per-pundit accuracy metrics from resolved predictions.
    Used by the Scorecard API to power leaderboard and pundit profiles.
    Pass sport='NFL' to filter to a specific sport; omit for cross-sport summary.
    """
    close_db = db is None
    if db is None:
        db = DBManager()

    try:
        project_id = os.environ.get("GCP_PROJECT_ID")
        mv_table = f"`{project_id}.gold_layer.pundit_leaderboard_mv`"

        # Prefer the pre-aggregated materialized view (migration 017) for sub-second latency.
        # Fall back to the base JOIN query if the view does not exist yet.
        sport_filter = f"WHERE sport = '{sport}'" if sport else ""
        mv_query = f"""
            SELECT
                pundit_id,
                pundit_name,
                sport,
                total_predictions,
                resolved_count,
                correct_count,
                accuracy_rate,
                avg_brier_score,
                avg_weighted_score
            FROM {mv_table}
            {sport_filter}
            ORDER BY avg_weighted_score DESC NULLS LAST
        """
        try:
            return db.fetch_df(mv_query)
        except Exception as mv_err:
            logger.warning(
                f"pundit_leaderboard_mv not available ({mv_err}); "
                "falling back to base table JOIN query"
            )

        # Fallback: full JOIN scan
        sport_filter_base = (
            f"WHERE COALESCE(l.sport, 'NFL') = '{sport}'" if sport else ""
        )
        query = f"""
            SELECT
                l.pundit_id,
                l.pundit_name,
                COALESCE(l.sport, 'NFL') AS sport,
                COUNT(*) AS total_predictions,
                COUNTIF(r.resolution_status IN ('CORRECT', 'INCORRECT')) AS resolved_count,
                COUNTIF(r.resolution_status = 'CORRECT') AS correct_count,
                SAFE_DIVIDE(
                    COUNTIF(r.resolution_status = 'CORRECT'),
                    COUNTIF(r.resolution_status IN ('CORRECT', 'INCORRECT'))
                ) AS accuracy_rate,
                AVG(r.brier_score) AS avg_brier_score,
                AVG(r.weighted_score) AS avg_weighted_score
            FROM `{project_id}.{LEDGER_TABLE}` l
            LEFT JOIN `{project_id}.{RESOLUTIONS_TABLE}` r
                ON l.prediction_hash = r.prediction_hash
            {sport_filter_base}
            GROUP BY l.pundit_id, l.pundit_name, sport
            ORDER BY avg_weighted_score DESC NULLS LAST
        """
        return db.fetch_df(query)
    finally:
        if close_db:
            db.close()
