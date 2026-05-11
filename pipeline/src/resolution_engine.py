"""
Prediction Resolution Engine (Issue #112)

Matches hashed predictions from gold_layer.prediction_ledger against actual NFL
outcomes to automatically score pundit accuracy.

Resolution states: PENDING | CORRECT | INCORRECT | VOID

Scoring:
  - Brier score for probabilistic claims (lower is better; 0 = perfect, 1 = worst)
  - Binary accuracy for yes/no predictions
  - Timeliness weight: predictions made further in advance score higher

Void semantics (Issue #686):
  - VOID predictions are excluded entirely from Brier and accuracy calculations.
  - Rationale: void means the claim became unresolvable through no fault of the
    pundit.  Penalising them (0.5 Brier) or awarding them (any score) both
    distort the leaderboard.  Full exclusion is the cleanest signal.
  - Use VoidReason to attach a structured, domain-specific reason to every void.
  - Retroactive void: if a previously-scored claim must be voided (e.g. an
    overturned election), call void_prediction() with retroactive=True; the
    MERGE in record_resolution will overwrite the existing CORRECT/INCORRECT row,
    nulling out brier_score, binary_correct, and weighted_score.  Downstream
    aggregations (get_pundit_accuracy_summary, scoring.run_backfill) must
    re-run to reflect the change.
"""

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

import pandas as pd
from google.cloud import bigquery

from src.db_manager import DBManager

logger = logging.getLogger(__name__)

LEDGER_TABLE = "gold_layer.prediction_ledger"
RESOLUTIONS_TABLE = "gold_layer.prediction_resolutions"


# ---------------------------------------------------------------------------
# VoidReason — domain-specific trigger catalogue (Issue #686)
# ---------------------------------------------------------------------------


class VoidReason(str, Enum):
    """
    Structured reason for voiding a prediction.

    Using str-Enum so values are JSON-serialisable and can be stored directly
    in the outcome_notes column without extra serialisation.

    Brier score treatment: VOID claims are excluded entirely from all scoring
    aggregations.  They are excluded from accuracy_rate, avg_brier_score, and
    avg_weighted_score.  Rationale: the void event was outside the pundit's
    control, so including them as 0.5 would unfairly penalise high-volume
    pundits in volatile domains (politics, finance) vs. sports-only pundits.

    Dashboard display: voided predictions show a grey "VOID" badge in the
    ledger table with a tooltip containing the human-readable reason string.
    They are excluded from the accuracy rate counter but do appear in the
    "total claims made" count so coverage breadth is not inflated.

    Retroactive void: call void_prediction(retroactive=True) to overwrite an
    existing CORRECT/INCORRECT row.  Downstream aggregations must re-run.
    """

    # ---- NFL ----------------------------------------------------------------
    # Player-level: the subject of the prediction ceased to be relevant
    PLAYER_RETIRED_MID_SEASON = "player_retired_mid_season"
    PLAYER_CAREER_ENDING_INJURY = "player_career_ending_injury"
    PLAYER_SUSPENDED_FULL_SEASON = "player_suspended_full_season"
    # Team/game-level
    GAME_CANCELLED = "game_cancelled"
    RULE_CHANGE_INVALIDATES_CLAIM = "rule_change_invalidates_claim"
    TRADE_MAKES_CLAIM_AMBIGUOUS = "trade_makes_claim_ambiguous"

    # ---- Politics -----------------------------------------------------------
    CANDIDATE_WITHDREW = "candidate_withdrew"
    ELECTION_CANCELLED = "election_cancelled"
    REDISTRICTING_REMOVED_DISTRICT = "redistricting_removed_district"
    TERM_LIMIT_DISQUALIFICATION = "term_limit_disqualification"
    CANDIDATE_DECEASED = "candidate_deceased"

    # ---- Finance / Markets --------------------------------------------------
    COMPANY_DELISTED = "company_delisted"
    COMPANY_ACQUIRED_BEFORE_EVENT = "company_acquired_before_event"
    REGULATORY_INTERVENTION = "regulatory_intervention"
    BANKRUPTCY_BEFORE_EARNINGS = "bankruptcy_before_earnings"

    # ---- Generic / pipeline -side -------------------------------------------
    # These are not domain-specific void triggers; they indicate a pipeline
    # limitation rather than a real-world void event.  Kept here so the full
    # vocabulary lives in one place.
    UNPARSEABLE_CLAIM = "unparseable_claim"
    PAST_RESOLUTION_HORIZON = "past_resolution_horizon"
    UNRESOLVABLE_AMBIGUOUS = "unresolvable_ambiguous"

    @property
    def human_label(self) -> str:
        """Short human-readable label for dashboard tooltips."""
        _labels = {
            "player_retired_mid_season": "Player retired mid-season",
            "player_career_ending_injury": "Career-ending injury",
            "player_suspended_full_season": "Player suspended full season",
            "game_cancelled": "Game cancelled",
            "rule_change_invalidates_claim": "Rule change invalidated claim",
            "trade_makes_claim_ambiguous": "Trade made claim ambiguous",
            "candidate_withdrew": "Candidate withdrew",
            "election_cancelled": "Election cancelled",
            "redistricting_removed_district": "District removed by redistricting",
            "term_limit_disqualification": "Term limit disqualification",
            "candidate_deceased": "Candidate deceased",
            "company_delisted": "Company delisted",
            "company_acquired_before_event": "Company acquired before event",
            "regulatory_intervention": "Regulatory intervention",
            "bankruptcy_before_earnings": "Bankruptcy before earnings",
            "unparseable_claim": "Claim could not be parsed",
            "past_resolution_horizon": "Resolution deadline passed",
            "unresolvable_ambiguous": "Claim too ambiguous to resolve",
        }
        return _labels.get(self.value, self.value.replace("_", " ").title())

    @property
    def is_pipeline_artifact(self) -> bool:
        """True for voids caused by pipeline limitations, not real-world events."""
        return self in {
            VoidReason.UNPARSEABLE_CLAIM,
            VoidReason.PAST_RESOLUTION_HORIZON,
            VoidReason.UNRESOLVABLE_AMBIGUOUS,
        }


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
    Writes or updates a resolution record in gold_layer.prediction_resolutions
    AND syncs the status back to gold_layer.prediction_ledger.resolution_status.

    Uses MERGE to upsert — resolutions can be updated as new evidence arrives.
    The ledger sync ensures prediction_ledger.resolution_status reflects the
    actual outcome so dashboard queries against the ledger are accurate.
    """
    close_db = db is None
    if db is None:
        db = DBManager()

    try:
        project_id = os.environ.get("GCP_PROJECT_ID")
        # Keep now as a timezone-aware datetime so it can be bound as a TIMESTAMP
        # parameter.  Binding ISO strings as STRING to TIMESTAMP columns causes
        # BigQuery type-mismatch errors during the MERGE.
        now = datetime.now(timezone.utc)

        # Numeric/boolean literals are safe to inline because they come from Python
        # dataclass fields (floats and bools), not from external/data-derived strings.
        brier = f"{result.brier_score}" if result.brier_score is not None else "NULL"
        binary = (
            "TRUE"
            if result.binary_correct is True
            else "FALSE"
            if result.binary_correct is False
            else "NULL"
        )
        weighted = (
            f"{result.weighted_score}" if result.weighted_score is not None else "NULL"
        )

        # All string values from external/data-derived sources go through @params.
        merge_sql = f"""
            MERGE `{project_id}.{RESOLUTIONS_TABLE}` T
            USING (SELECT @prediction_hash AS prediction_hash) S
            ON T.prediction_hash = S.prediction_hash
            WHEN MATCHED THEN UPDATE SET
                resolution_status     = @resolution_status,
                resolved_at           = @resolved_at,
                resolver              = @resolver,
                brier_score           = {brier},
                binary_correct        = {binary},
                timeliness_weight     = {result.timeliness_weight},
                weighted_score        = {weighted},
                outcome_source        = @outcome_source,
                outcome_reference_id  = @outcome_reference_id,
                outcome_notes         = @outcome_notes,
                updated_at            = @updated_at
            WHEN NOT MATCHED THEN INSERT (
                prediction_hash, resolution_status, resolved_at, resolver,
                brier_score, binary_correct, timeliness_weight, weighted_score,
                outcome_source, outcome_reference_id, outcome_notes,
                created_at, updated_at
            ) VALUES (
                @prediction_hash, @resolution_status, @resolved_at, @resolver,
                {brier}, {binary}, {result.timeliness_weight}, {weighted},
                @outcome_source, @outcome_reference_id, @outcome_notes,
                @created_at, @created_at
            )
        """
        query_parameters = [
            bigquery.ScalarQueryParameter(
                "prediction_hash", "STRING", result.prediction_hash
            ),
            bigquery.ScalarQueryParameter(
                "resolution_status", "STRING", result.resolution_status
            ),
            bigquery.ScalarQueryParameter("resolved_at", "TIMESTAMP", now),
            bigquery.ScalarQueryParameter("resolver", "STRING", result.resolver),
            bigquery.ScalarQueryParameter(
                "outcome_source", "STRING", result.outcome_source
            ),
            bigquery.ScalarQueryParameter(
                "outcome_reference_id", "STRING", result.outcome_reference_id
            ),
            bigquery.ScalarQueryParameter(
                "outcome_notes", "STRING", result.outcome_notes
            ),
            bigquery.ScalarQueryParameter("updated_at", "TIMESTAMP", now),
            bigquery.ScalarQueryParameter("created_at", "TIMESTAMP", now),
        ]
        db.execute(merge_sql, query_parameters=query_parameters)
        logger.info(
            f"Recorded resolution for {result.prediction_hash[:16]}…: "
            f"{result.resolution_status} (resolver={result.resolver})"
        )

        # Sync resolution_status back to the ledger so dashboard queries that read
        # prediction_ledger.resolution_status directly return accurate counts.
        # VOID maps to 'VOID' in the ledger; CORRECT/INCORRECT map directly.
        ledger_status = result.resolution_status  # CORRECT | INCORRECT | VOID
        ledger_sync_sql = f"""
            UPDATE `{project_id}.{LEDGER_TABLE}`
            SET resolution_status = @resolution_status,
                resolved_at       = @resolved_at,
                resolution_notes  = @resolution_notes
            WHERE prediction_hash = @prediction_hash
        """
        db.execute(
            ledger_sync_sql,
            query_parameters=[
                bigquery.ScalarQueryParameter(
                    "resolution_status", "STRING", ledger_status
                ),
                bigquery.ScalarQueryParameter("resolved_at", "TIMESTAMP", now),
                bigquery.ScalarQueryParameter(
                    "resolution_notes", "STRING", result.outcome_notes
                ),
                bigquery.ScalarQueryParameter(
                    "prediction_hash", "STRING", result.prediction_hash
                ),
            ],
        )
        logger.debug(
            f"Synced ledger status for {result.prediction_hash[:16]}…: {ledger_status}"
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
    reason: "str | VoidReason",
    db: Optional[DBManager] = None,
    retroactive: bool = False,
) -> ResolutionResult:
    """
    Mark a prediction as VOID (unresolvable — e.g. player injured before outcome).

    Args:
        prediction_hash: SHA-256 hash of the claim.
        reason: A VoidReason enum value (preferred) or a plain string reason.
            Passing a VoidReason gives structured dashboard tooltips and allows
            is_pipeline_artifact filtering.
        db: Optional shared DBManager.
        retroactive: Set True when voiding a claim that was already scored
            (CORRECT/INCORRECT).  The MERGE in record_resolution will overwrite
            the existing row, nulling out brier_score, binary_correct, and
            weighted_score.  Callers should re-run downstream aggregations
            (get_pundit_accuracy_summary, scoring.run_backfill) after a
            retroactive void.

    Returns:
        ResolutionResult with resolution_status="VOID" and no score fields.
    """
    reason_str = reason.value if isinstance(reason, VoidReason) else reason
    resolver = "retroactive_void" if retroactive else "manual"
    result = ResolutionResult(
        prediction_hash=prediction_hash,
        resolution_status="VOID",
        resolver=resolver,
        outcome_notes=reason_str,
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
        sport_filter = "AND COALESCE(l.sport, 'NFL') = @sport" if sport else ""
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
        query_parameters = (
            [bigquery.ScalarQueryParameter("sport", "STRING", sport)] if sport else []
        )
        return db.fetch_df(query, query_parameters=query_parameters)
    finally:
        if close_db:
            db.close()


def get_pundit_accuracy_summary(
    sport: Optional[str] = None,
    db: Optional[DBManager] = None,
    min_quality: Optional[float] = None,
    min_resolved_claims: int = 0,
    published_only: bool = False,
) -> pd.DataFrame:
    """
    Returns per-pundit accuracy metrics from resolved predictions.
    Used by the Scorecard API to power leaderboard and pundit profiles.

    Args:
        sport:               Filter to a specific sport (e.g. 'NFL'); omit for all.
        db:                  Optional shared DBManager; created and closed if None.
        min_quality:         Restrict to predictions with quality >= this score.
                             Requires gold_layer.assertion_quality to be populated.
        min_resolved_claims: Minimum number of resolved (CORRECT|INCORRECT) claims
                             a pundit must have for their accuracy to be returned.
                             Pundits below this threshold are excluded from results
                             so the API can return null rather than misleading stats.
                             Default 0 (no filter). Issue #830: public API uses 5.
        published_only:      If True, restrict to pundits with published=TRUE in
                             pundit_registry. Use for public-facing API endpoints.
                             Default False (admin / internal use).

    VOID treatment (Issue #686): VOID predictions are excluded from
    accuracy_rate and avg_brier_score.  They are counted in total_predictions
    (so coverage breadth is not inflated) but not in resolved_count.  BigQuery
    AVG() ignores NULL rows, and VOID rows always have brier_score = NULL, so
    no special filter is required.
    """
    close_db = db is None
    if db is None:
        db = DBManager()

    try:
        project_id = os.environ.get("GCP_PROJECT_ID")
        where_clauses = []
        if sport:
            where_clauses.append("COALESCE(l.sport, 'NFL') = @sport")
        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        quality_join = ""
        if min_quality is not None:
            quality_join = (
                f"INNER JOIN `{project_id}.gold_layer.assertion_quality` q "
                f"ON l.prediction_hash = q.prediction_hash "
                f"AND q.quality_score >= {float(min_quality)}"
            )

        published_join = ""
        if published_only:
            published_join = (
                f"INNER JOIN `{project_id}.nfl_dead_money.pundit_registry` pr "
                f"ON l.pundit_id = pr.pundit_id AND pr.published = TRUE"
            )
        min_resolved = max(0, int(min_resolved_claims))
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
            {quality_join}
            {published_join}
            {where_sql}
            GROUP BY l.pundit_id, l.pundit_name, sport
            HAVING COUNTIF(r.resolution_status IN ('CORRECT', 'INCORRECT')) >= {min_resolved}
            ORDER BY avg_weighted_score DESC NULLS LAST
        """
        query_parameters = (
            [bigquery.ScalarQueryParameter("sport", "STRING", sport)] if sport else []
        )
        return db.fetch_df(query, query_parameters=query_parameters)
    finally:
        if close_db:
            db.close()


# ---------------------------------------------------------------------------
# Retraction-aware resolution (Issue #830)
# ---------------------------------------------------------------------------


def resolve_with_retraction_check(
    prediction_hash: str,
    retracted_at: datetime,
    resolution_horizon: datetime,
    correct: bool,
    outcome_source: str,
    outcome_reference_id: Optional[str] = None,
    outcome_notes: Optional[str] = None,
    prediction_ts: Optional[datetime] = None,
    outcome_ts: Optional[datetime] = None,
    db: Optional[DBManager] = None,
) -> ResolutionResult:
    """
    Resolve a prediction that carries a retraction timestamp.

    Adjudication rule (Issue #830 decision):
      - If retracted_at < resolution_horizon:
          The source retracted the claim *before* the outcome window closed.
          This means the pundit themselves withdrew the prediction; mark VOID.
      - If retracted_at >= resolution_horizon:
          The retraction came after the resolution horizon — the prediction
          was already in play when the outcome was decided.  Score it normally
          as CORRECT or INCORRECT.

    Args:
        prediction_hash:     SHA-256 identifier of the prediction ledger row.
        retracted_at:        Timezone-aware datetime when the pundit retracted.
        resolution_horizon:  Timezone-aware datetime marking the end of the
                             valid prediction window (e.g. season start, draft day).
        correct:             Whether the prediction ultimately proved correct.
        outcome_source:      Data source that determined correctness.
        outcome_reference_id: Optional reference ID in that source.
        outcome_notes:       Human-readable resolution note.
        prediction_ts:       When the prediction was first made (for timeliness).
        outcome_ts:          When the outcome occurred (for timeliness).
        db:                  Optional shared DBManager (created + closed if None).

    Returns:
        ResolutionResult with status VOID (early retraction) or
        CORRECT / INCORRECT (late retraction scored normally).
    """
    if retracted_at < resolution_horizon:
        # Retraction before horizon → VOID
        void_reason = (
            f"Retracted at {retracted_at.isoformat()} before resolution horizon "
            f"{resolution_horizon.isoformat()}. " + (outcome_notes or "")
        ).strip()
        return void_prediction(prediction_hash, void_reason, db=db)
    else:
        # Retraction at or after horizon → score normally
        return resolve_binary(
            prediction_hash,
            correct,
            outcome_source,
            outcome_reference_id=outcome_reference_id,
            outcome_notes=outcome_notes,
            prediction_ts=prediction_ts,
            outcome_ts=outcome_ts,
            db=db,
        )
