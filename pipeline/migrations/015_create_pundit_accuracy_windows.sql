-- Migration 015: Create gold_layer.pundit_accuracy_windows
--
-- Rolling accuracy windows for pundits across 3 time horizons:
--   30d         — last 30 days (displayable if resolved_count >= 5)
--   last_season — most recently completed sport season (displayable if >= 10)
--   career      — all time (displayable if >= 20)
--
-- Also stores drift_flagged / drift_magnitude (career vs last_season divergence).
--
-- Partition:  DATE(computed_at)
-- Cluster:    pundit_id, window_type, entity_class

CREATE TABLE IF NOT EXISTS `${project_id}.gold_layer.pundit_accuracy_windows` (
    pundit_id       STRING    NOT NULL,
    entity_class    STRING,
    claim_type      STRING,
    sport           STRING,
    window_type     STRING    NOT NULL,   -- '30d' | 'last_season' | 'career'
    accuracy_rate   FLOAT64,
    brier_score     FLOAT64,
    resolved_count  INT64,
    displayable     BOOL,
    drift_flagged   BOOL,
    drift_magnitude FLOAT64,
    computed_at     TIMESTAMP NOT NULL
)
PARTITION BY DATE(computed_at)
CLUSTER BY pundit_id, window_type, entity_class
OPTIONS (
    description = 'Rolling accuracy windows (30d / last_season / career) per pundit, '
                  'with drift flags when career vs last_season diverge >= 0.12'
);
