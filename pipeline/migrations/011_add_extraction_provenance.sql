-- Migration 011: Add extraction provenance columns to prediction_ledger (Issue #247)
--
-- Tracks which prompt version and LLM produced each prediction, enabling:
--   - Quality comparison across prompt versions (prompt_version)
--   - Quality comparison across LLM backends (llm_provider + llm_model)
--   - Rollback analysis if a new prompt degrades extraction quality
--
-- All columns are nullable — existing rows will have NULL (treated as "unknown").
-- No backfill required: NULL = pre-provenance-tracking era.
--
-- Run against the project with:
--   bq query --use_legacy_sql=false --project_id=<PROJECT_ID> \
--     < pipeline/migrations/011_add_extraction_provenance.sql

ALTER TABLE `${PROJECT_ID}.gold_layer.prediction_ledger`
ADD COLUMN IF NOT EXISTS prompt_version STRING,
ADD COLUMN IF NOT EXISTS llm_provider STRING,
ADD COLUMN IF NOT EXISTS llm_model STRING;
