-- Migration 008: Add target_player_name to prediction_ledger (Issue #170)
--
-- The target_player_id column was receiving raw player names (e.g. "Fernando Mendoza")
-- instead of actual player IDs. This migration:
-- 1. Adds a target_player_name column for the raw name
-- 2. Backfills existing data from target_player_id → target_player_name
-- 3. Clears target_player_id (which held names, not IDs) so it can be used for real IDs
--
-- Note: Requires BQ billing enabled for DML (UPDATE). Run against the project with:
--   bq query --use_legacy_sql=false < pipeline/migrations/008_add_target_player_name.sql

ALTER TABLE `${PROJECT_ID}.gold_layer.prediction_ledger`
ADD COLUMN IF NOT EXISTS target_player_name STRING;

-- Backfill: copy current target_player_id (which has names) into target_player_name
UPDATE `${PROJECT_ID}.gold_layer.prediction_ledger`
SET target_player_name = target_player_id
WHERE target_player_name IS NULL
  AND target_player_id IS NOT NULL;

-- Clear the mis-populated IDs (they contain names, not IDs)
UPDATE `${PROJECT_ID}.gold_layer.prediction_ledger`
SET target_player_id = NULL
WHERE target_player_id IS NOT NULL
  AND target_player_id = target_player_name;
