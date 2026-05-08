-- Migration 024: Per-Pundit Calibration Table (Issue #809)
--
-- Creates gold_layer.pundit_calibration to store Murphy-decomposed Brier scores
-- per pundit × entity_class × claim_type × season_year.
--
-- GROUPING SETS covering:
--   (pundit_id, season_year, entity_class, claim_type) — full breakdown
--   (pundit_id, season_year, entity_class)              — by entity class
--   (pundit_id, season_year, claim_type)                — by claim type
--   (pundit_id, season_year)                            — season totals
--   (pundit_id)                                         — all-time totals
--
-- NULL in season_year / entity_class / claim_type denotes an aggregated grouping
-- (GROUPING SETS semantics). Use COALESCE(season_year, 'ALL') etc. in queries
-- that need human-readable labels.
--
-- Anomaly flag (anomaly_flag) reserved for the anomaly engine (Issue #810).
-- It is always FALSE here; #810 will MERGE-update it.

CREATE TABLE IF NOT EXISTS `{project_id}.gold_layer.pundit_calibration`
(
  pundit_id           STRING    NOT NULL,
  pundit_name         STRING,
  season_year         INT64,              -- NULL = all-time aggregate grouping
  entity_class        STRING,             -- PLAYER | TEAM | GAME | AWARD | ALL (NULL = aggregated)
  claim_type          STRING,             -- game_outcome | player_performance | trade | draft | injury | ALL (NULL = aggregated)
  sport               STRING    DEFAULT 'nfl',
  -- Brier score components (Murphy decomposition)
  brier_score         FLOAT64,            -- lower = better calibrated (full Brier MSE)
  reliability         FLOAT64,            -- calibration curve MSE component (how well confidence matches reality)
  resolution          FLOAT64,            -- sharpness component (how far from base rate)
  uncertainty         FLOAT64,            -- base rate term p_bar * (1 - p_bar)
  -- Accuracy
  accuracy_rate       FLOAT64,            -- binary correct / total resolved
  total_claims        INT64,
  resolved_claims     INT64,
  correct_claims      INT64,
  -- Anomaly flag (set by Issue #810 anomaly engine)
  anomaly_flag        BOOL      DEFAULT FALSE,
  last_updated        TIMESTAMP NOT NULL
)
PARTITION BY DATE(last_updated)
CLUSTER BY pundit_id, season_year, entity_class
OPTIONS(description="Per-pundit calibration scores. GROUPING SETS across entity_class x claim_type. Recomputed nightly by compute_calibration(). Anomaly flag populated by #810.");
