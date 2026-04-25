-- Migration: 017_create_pundit_leaderboard_mv
-- Issue: #71 — SP20-2 BigQuery Query Optimization
-- Description: Materialized view pre-aggregating per-pundit accuracy metrics
--   from prediction_ledger + prediction_resolutions.
--   Refresh every 60 minutes so leaderboard/pundits API routes read from cache
--   instead of executing a full JOIN on every request.
--
-- BigQuery materialized view constraints:
--   - Base tables must be in the same dataset or cross-dataset with correct permissions
--   - Supported: GROUP BY, COUNT, SUM, AVG — no WINDOW FUNCTIONS or DISTINCT in SELECT
--   - Refresh: automatic (incremental when possible, full otherwise)
--
-- Usage: get_pundit_accuracy_summary() reads from this view if it exists,
--   falling back to the base query if not (handled in resolution_engine.py).

CREATE MATERIALIZED VIEW IF NOT EXISTS `{project_id}.gold_layer.pundit_leaderboard_mv`
OPTIONS (
  enable_refresh        = TRUE,
  refresh_interval_minutes = 60,
  description = "Pre-aggregated per-pundit accuracy metrics. Refreshes every 60 minutes. Source: gold_layer.prediction_ledger + prediction_resolutions."
)
AS
SELECT
  l.pundit_id,
  l.pundit_name,
  COALESCE(l.sport, 'NFL')                                                       AS sport,
  COUNT(*)                                                                        AS total_predictions,
  COUNTIF(r.resolution_status IN ('CORRECT', 'INCORRECT'))                       AS resolved_count,
  COUNTIF(r.resolution_status = 'CORRECT')                                       AS correct_count,
  SAFE_DIVIDE(
    COUNTIF(r.resolution_status = 'CORRECT'),
    COUNTIF(r.resolution_status IN ('CORRECT', 'INCORRECT'))
  )                                                                               AS accuracy_rate,
  AVG(r.brier_score)                                                              AS avg_brier_score,
  AVG(r.weighted_score)                                                           AS avg_weighted_score,
  -- Timeliness: proportion of predictions made early (before the event)
  SAFE_DIVIDE(
    COUNTIF(r.resolution_status = 'CORRECT' AND r.timeliness_bonus > 0),
    COUNTIF(r.resolution_status IN ('CORRECT', 'INCORRECT'))
  )                                                                               AS timeliness_hit_rate
FROM `{project_id}.gold_layer.prediction_ledger` l
LEFT JOIN `{project_id}.gold_layer.prediction_resolutions` r
  ON l.prediction_hash = r.prediction_hash
GROUP BY l.pundit_id, l.pundit_name, sport;
