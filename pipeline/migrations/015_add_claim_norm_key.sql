-- Migration 015: Add claim_norm_key to prediction_ledger (Issue #808 Phase 0)
--
-- Adds a normalised key column used for exact-match claim deduplication.
-- The key is SHA-256 of LOWER(TRIM(claim_category|target_player_name|target_team|season_year)).
-- NULL fields are treated as empty string so the hash is always deterministic.
--
-- Column is nullable; existing rows keep NULL (treated as "pre-dedup era").
-- The dedup gate in assertion_extractor.py populates claim_norm_key at write time
-- for all new claims and uses it for the BQ existence check.
--
-- Run against the project with:
--   bq query --use_legacy_sql=false --project_id=<PROJECT_ID> \
--     < pipeline/migrations/015_add_claim_norm_key.sql

ALTER TABLE `${PROJECT_ID}.gold_layer.prediction_ledger`
ADD COLUMN IF NOT EXISTS claim_norm_key STRING
  OPTIONS(description="SHA-256 of LOWER(TRIM(claim_category|target_player_name|target_team|season_year)). Used for exact-match deduplication gate (Issue #808 Phase 0).");
