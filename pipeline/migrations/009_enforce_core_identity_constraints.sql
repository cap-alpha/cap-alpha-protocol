-- Migration: 009_enforce_core_identity_constraints
-- Issue: #106 — SP29-1: Enforce strict BigQuery NOT NULL constraints
-- Description: Adds NOT NULL constraints to identity columns across all core Silver and
--              Gold layer tables. These constraints prevent NULL identity keys from
--              propagating into downstream aggregations and the ML feature store.
--
-- BigQuery DDL note: ALTER TABLE ... ALTER COLUMN ... SET NOT NULL is valid in BigQuery
-- but will fail if the column contains existing NULL values. Before running this migration
-- against a live dataset, run the null-audit queries in the comments at the bottom to
-- confirm zero NULLs in the identity columns.
--
-- Application-layer enforcement: pipeline/src/data_quality_tests.py::validate_not_null_constraints()
-- is the primary gate — it raises ValueError before any write that would violate these constraints.

-- ============================================================================
-- silver_pfr_game_logs
-- ============================================================================
ALTER TABLE `{project_id}.nfl_dead_money.silver_pfr_game_logs`
  ALTER COLUMN player_name SET NOT NULL;

ALTER TABLE `{project_id}.nfl_dead_money.silver_pfr_game_logs`
  ALTER COLUMN team SET NOT NULL;

ALTER TABLE `{project_id}.nfl_dead_money.silver_pfr_game_logs`
  ALTER COLUMN year SET NOT NULL;

ALTER TABLE `{project_id}.nfl_dead_money.silver_pfr_game_logs`
  ALTER COLUMN week SET NOT NULL;

-- ============================================================================
-- silver_penalties
-- ============================================================================
ALTER TABLE `{project_id}.nfl_dead_money.silver_penalties`
  ALTER COLUMN player_name_short SET NOT NULL;

ALTER TABLE `{project_id}.nfl_dead_money.silver_penalties`
  ALTER COLUMN team SET NOT NULL;

ALTER TABLE `{project_id}.nfl_dead_money.silver_penalties`
  ALTER COLUMN year SET NOT NULL;

-- ============================================================================
-- silver_spotrac_contracts  (core Contracts identity table)
-- ============================================================================
ALTER TABLE `{project_id}.nfl_dead_money.silver_spotrac_contracts`
  ALTER COLUMN contract_id SET NOT NULL;

ALTER TABLE `{project_id}.nfl_dead_money.silver_spotrac_contracts`
  ALTER COLUMN player_name SET NOT NULL;

ALTER TABLE `{project_id}.nfl_dead_money.silver_spotrac_contracts`
  ALTER COLUMN team SET NOT NULL;

ALTER TABLE `{project_id}.nfl_dead_money.silver_spotrac_contracts`
  ALTER COLUMN year SET NOT NULL;

ALTER TABLE `{project_id}.nfl_dead_money.silver_spotrac_contracts`
  ALTER COLUMN cap_hit_millions SET NOT NULL;

ALTER TABLE `{project_id}.nfl_dead_money.silver_spotrac_contracts`
  ALTER COLUMN system_ingest_time SET NOT NULL;

-- ============================================================================
-- silver_spotrac_rankings
-- ============================================================================
ALTER TABLE `{project_id}.nfl_dead_money.silver_spotrac_rankings`
  ALTER COLUMN player_name SET NOT NULL;

ALTER TABLE `{project_id}.nfl_dead_money.silver_spotrac_rankings`
  ALTER COLUMN year SET NOT NULL;

-- ============================================================================
-- silver_team_cap  (core Teams identity table)
-- ============================================================================
ALTER TABLE `{project_id}.nfl_dead_money.silver_team_cap`
  ALTER COLUMN team SET NOT NULL;

ALTER TABLE `{project_id}.nfl_dead_money.silver_team_cap`
  ALTER COLUMN year SET NOT NULL;

-- ============================================================================
-- silver_player_metadata  (core Players identity table)
-- ============================================================================
ALTER TABLE `{project_id}.nfl_dead_money.silver_player_metadata`
  ALTER COLUMN full_name SET NOT NULL;

-- ============================================================================
-- silver_team_finance
-- ============================================================================
ALTER TABLE `{project_id}.nfl_dead_money.silver_team_finance`
  ALTER COLUMN Team SET NOT NULL;

ALTER TABLE `{project_id}.nfl_dead_money.silver_team_finance`
  ALTER COLUMN Year SET NOT NULL;

-- ============================================================================
-- silver_spotrac_salaries
-- ============================================================================
ALTER TABLE `{project_id}.nfl_dead_money.silver_spotrac_salaries`
  ALTER COLUMN player_name SET NOT NULL;

ALTER TABLE `{project_id}.nfl_dead_money.silver_spotrac_salaries`
  ALTER COLUMN team SET NOT NULL;

ALTER TABLE `{project_id}.nfl_dead_money.silver_spotrac_salaries`
  ALTER COLUMN year SET NOT NULL;

-- ============================================================================
-- silver_pfr_draft_history
-- ============================================================================
ALTER TABLE `{project_id}.nfl_dead_money.silver_pfr_draft_history`
  ALTER COLUMN player_name SET NOT NULL;

ALTER TABLE `{project_id}.nfl_dead_money.silver_pfr_draft_history`
  ALTER COLUMN team SET NOT NULL;

ALTER TABLE `{project_id}.nfl_dead_money.silver_pfr_draft_history`
  ALTER COLUMN year SET NOT NULL;

-- ============================================================================
-- fact_player_efficiency  (Gold Layer — primary downstream table)
-- ============================================================================
ALTER TABLE `{project_id}.nfl_dead_money.fact_player_efficiency`
  ALTER COLUMN player_name SET NOT NULL;

ALTER TABLE `{project_id}.nfl_dead_money.fact_player_efficiency`
  ALTER COLUMN team SET NOT NULL;

ALTER TABLE `{project_id}.nfl_dead_money.fact_player_efficiency`
  ALTER COLUMN year SET NOT NULL;

ALTER TABLE `{project_id}.nfl_dead_money.fact_player_efficiency`
  ALTER COLUMN position SET NOT NULL;

ALTER TABLE `{project_id}.nfl_dead_money.fact_player_efficiency`
  ALTER COLUMN cap_hit_millions SET NOT NULL;

-- ============================================================================
-- PRE-RUN NULL AUDIT (run these SELECT queries first — all must return 0)
-- ============================================================================
-- SELECT COUNT(*) FROM `{project_id}.nfl_dead_money.silver_pfr_game_logs`        WHERE player_name IS NULL OR team IS NULL OR year IS NULL OR week IS NULL;
-- SELECT COUNT(*) FROM `{project_id}.nfl_dead_money.silver_spotrac_contracts`     WHERE contract_id IS NULL OR player_name IS NULL OR team IS NULL OR year IS NULL OR cap_hit_millions IS NULL OR system_ingest_time IS NULL;
-- SELECT COUNT(*) FROM `{project_id}.nfl_dead_money.silver_team_cap`              WHERE team IS NULL OR year IS NULL;
-- SELECT COUNT(*) FROM `{project_id}.nfl_dead_money.silver_player_metadata`       WHERE full_name IS NULL;
-- SELECT COUNT(*) FROM `{project_id}.nfl_dead_money.silver_spotrac_salaries`      WHERE player_name IS NULL OR team IS NULL OR year IS NULL;
-- SELECT COUNT(*) FROM `{project_id}.nfl_dead_money.silver_pfr_draft_history`     WHERE player_name IS NULL OR team IS NULL OR year IS NULL;
-- SELECT COUNT(*) FROM `{project_id}.nfl_dead_money.fact_player_efficiency`       WHERE player_name IS NULL OR team IS NULL OR year IS NULL OR position IS NULL OR cap_hit_millions IS NULL;
