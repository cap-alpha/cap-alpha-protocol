-- Migration: 007_add_sport_to_prediction_tables
-- Issue: #120 — Sport-Agnostic Schema
-- Description: Adds `sport` column to all prediction/ledger/media tables so the
-- schema supports multi-sport expansion (NFL first, MLB next).
--
-- All existing rows are backfilled with 'NFL'.
-- New rows must explicitly set sport at write time.
--
-- Run order: execute this after 003, 004, 005, 006 are applied.

-- 1. prediction_ledger (gold_layer) ─────────────────────────────────────────

ALTER TABLE `{project_id}.gold_layer.prediction_ledger`
ADD COLUMN IF NOT EXISTS sport STRING
  OPTIONS(description="Sport context: NFL|MLB|NBA|NHL|NCAAF|NCAAB. Default NFL for backfilled rows.");

UPDATE `{project_id}.gold_layer.prediction_ledger`
SET sport = 'NFL'
WHERE sport IS NULL;

-- 2. prediction_resolutions (gold_layer) ─────────────────────────────────────
-- Sport lives on the ledger row; resolutions join back to it.
-- Adding a denormalized sport column here for query performance (avoids JOIN for filtering).

ALTER TABLE `{project_id}.gold_layer.prediction_resolutions`
ADD COLUMN IF NOT EXISTS sport STRING
  OPTIONS(description="Denormalized from prediction_ledger.sport. Allows sport-filtered resolution queries without JOIN.");

-- No backfill needed — resolution rows can JOIN to ledger to derive sport.
-- Populated at resolution write time going forward.

-- 3. raw_pundit_media (nfl_dead_money / bronze layer) ────────────────────────

ALTER TABLE `{project_id}.nfl_dead_money.raw_pundit_media`
ADD COLUMN IF NOT EXISTS sport STRING
  OPTIONS(description="Sport context inferred from source config (media_sources.yaml). NFL|MLB|NBA etc.");

UPDATE `{project_id}.nfl_dead_money.raw_pundit_media`
SET sport = 'NFL'
WHERE sport IS NULL;
