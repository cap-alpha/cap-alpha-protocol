-- Migration: 010_create_pundit_materialized_views
-- Issue: #71 — SP20-2: Optimize BigQuery query execution paths
-- Description: Creates materialized views for the two most expensive pundit API queries:
--
--   1. mv_pundit_accuracy_summary  — per-pundit aggregate stats (accuracy, Brier, weighted score)
--      Source: leaderboard, /pundits/, /pundits/{id} all previously ran this JOIN+GROUP BY live
--
--   2. mv_recent_resolved_predictions — latest resolved predictions across all pundits
--      Source: /predictions/recent previously ran a full JOIN + ORDER BY on every request
--
-- BigQuery materialized view notes:
--   • Auto-refreshed within max_staleness (set to 15 minutes below — adjust to taste)
--   • MAX_STALENESS = 900 seconds (15 min) is appropriate for leaderboard / recent-feed data
--   • Querying a stale MV falls back to the live base tables automatically if staleness
--     exceeds the budget, so the result is always correct — just potentially from cache
--   • DROP MATERIALIZED VIEW IF EXISTS before CREATE allows idempotent re-runs
--
-- Application layer: pipeline/api/pundit_router.py reads these views directly
-- instead of calling get_pundit_accuracy_summary() on every request.

-- ============================================================================
-- 1. mv_pundit_accuracy_summary
-- ============================================================================

DROP MATERIALIZED VIEW IF EXISTS `{project_id}.gold_layer.mv_pundit_accuracy_summary`;

CREATE MATERIALIZED VIEW `{project_id}.gold_layer.mv_pundit_accuracy_summary`
OPTIONS (
  enable_refresh = TRUE,
  refresh_interval_minutes = 15
)
AS
SELECT
    l.pundit_id,
    l.pundit_name,
    COALESCE(l.sport, 'NFL')                                          AS sport,
    COUNT(*)                                                          AS total_predictions,
    COUNTIF(r.resolution_status IN ('CORRECT', 'INCORRECT'))          AS resolved_count,
    COUNTIF(r.resolution_status = 'CORRECT')                         AS correct_count,
    SAFE_DIVIDE(
        COUNTIF(r.resolution_status = 'CORRECT'),
        COUNTIF(r.resolution_status IN ('CORRECT', 'INCORRECT'))
    )                                                                 AS accuracy_rate,
    AVG(r.brier_score)                                                AS avg_brier_score,
    AVG(r.weighted_score)                                             AS avg_weighted_score
FROM `{project_id}.gold_layer.prediction_ledger` l
LEFT JOIN `{project_id}.gold_layer.prediction_resolutions` r
    ON l.prediction_hash = r.prediction_hash
GROUP BY l.pundit_id, l.pundit_name, sport;

-- ============================================================================
-- 2. mv_recent_resolved_predictions
-- ============================================================================

DROP MATERIALIZED VIEW IF EXISTS `{project_id}.gold_layer.mv_recent_resolved_predictions`;

CREATE MATERIALIZED VIEW `{project_id}.gold_layer.mv_recent_resolved_predictions`
OPTIONS (
  enable_refresh = TRUE,
  refresh_interval_minutes = 60
)
AS
SELECT
    l.prediction_hash,
    l.pundit_id,
    l.pundit_name,
    l.ingestion_timestamp,
    l.extracted_claim,
    l.claim_category,
    l.season_year,
    l.target_player_id,
    l.target_team,
    r.resolution_status,
    r.resolved_at,
    r.binary_correct,
    r.brier_score,
    r.weighted_score,
    r.outcome_notes
FROM `{project_id}.gold_layer.prediction_ledger` l
INNER JOIN `{project_id}.gold_layer.prediction_resolutions` r
    ON l.prediction_hash = r.prediction_hash
WHERE r.resolution_status IN ('CORRECT', 'INCORRECT');

-- ============================================================================
-- ROLLBACK (run to revert this migration)
-- ============================================================================
-- DROP MATERIALIZED VIEW IF EXISTS `{project_id}.gold_layer.mv_pundit_accuracy_summary`;
-- DROP MATERIALIZED VIEW IF EXISTS `{project_id}.gold_layer.mv_recent_resolved_predictions`;
