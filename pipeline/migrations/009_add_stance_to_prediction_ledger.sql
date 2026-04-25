-- Migration: 009_add_stance_to_prediction_ledger
-- Issue: #79 — SP22-2 NLP Assertion Extraction
-- Description: Adds a `stance` column to gold_layer.prediction_ledger to capture
--              the directional sentiment of each prediction (bullish/bearish/neutral).
--              Existing rows will have NULL stance (unknown — predates this field).
--
-- BigQuery ALTER TABLE adds the column as NULLABLE, safe for append-only tables.

ALTER TABLE `{project_id}.gold_layer.prediction_ledger`
  ADD COLUMN IF NOT EXISTS stance STRING
    OPTIONS(description="Directional stance of the prediction: bullish|bearish|neutral. bullish=positive outcome predicted; bearish=negative outcome predicted; neutral=no clear directional bias. NULL for rows ingested before this migration.");
