-- Migration 014: Add extraction provenance columns to processed_media_hashes (Issue #247)
--
-- Tracks per-article extraction metadata so model comparison experiments are possible:
--   - extractor_model / extractor_provider: which LLM processed the article
--   - assertions_extracted: how many assertions landed in prediction_ledger
--   - extraction_duration_ms: wall-clock time for the LLM call
--   - prompt_version: which prompt template produced these results
--   - tokens_used: token count from LLM response (Ollama returns this natively)
--
-- All columns nullable — existing rows have NULL (= pre-provenance era). No backfill needed.
--
-- Run with:
--   bq query --use_legacy_sql=false --project_id=cap-alpha-protocol \
--     < pipeline/migrations/014_add_processed_media_provenance.sql

ALTER TABLE `cap-alpha-protocol`.nfl_dead_money.processed_media_hashes
ADD COLUMN IF NOT EXISTS extractor_model STRING,
ADD COLUMN IF NOT EXISTS extractor_provider STRING,
ADD COLUMN IF NOT EXISTS assertions_extracted INT64,
ADD COLUMN IF NOT EXISTS extraction_duration_ms INT64,
ADD COLUMN IF NOT EXISTS prompt_version STRING,
ADD COLUMN IF NOT EXISTS tokens_used INT64;
