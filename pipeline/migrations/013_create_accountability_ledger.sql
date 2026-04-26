-- Migration: 012_create_accountability_ledger
-- Issue: #162 — Accountability dimension: 7th scoring axis
-- Description: Stores per-prediction classifications of how pundits behaved
--              after being proven wrong. Enables the Accountability scoring axis.
--
-- Accountability classes:
--   owns_it        — pundit references the miss and explains what they got wrong
--   silent_burial  — no mention of the miss in subsequent content
--   revisionism    — "What I actually said was..." reframing
--   doubling_down  — "I'm still right, the outcome was fluky"
--   deflection     — "Nobody could've predicted that"
--   insufficient_data — not enough subsequent content to classify

CREATE TABLE IF NOT EXISTS `{project_id}.gold_layer.accountability_ledger`
(
  -- FK to prediction_ledger / prediction_resolutions
  prediction_hash       STRING    NOT NULL OPTIONS(description="SHA-256 FK to gold_layer.prediction_ledger.prediction_hash"),

  -- Pundit identity (denormalized for query convenience)
  pundit_id             STRING    NOT NULL OPTIONS(description="Pundit identifier, matches prediction_ledger.pundit_id"),
  pundit_name           STRING    OPTIONS(description="Human-readable pundit name"),

  -- The original missed prediction
  original_claim        STRING    OPTIONS(description="extracted_claim text from prediction_ledger"),
  resolution_status     STRING    OPTIONS(description="Always INCORRECT for records in this table"),
  resolved_at           TIMESTAMP OPTIONS(description="When the prediction was resolved as INCORRECT"),

  -- Accountability classification
  accountability_class  STRING    NOT NULL OPTIONS(description="owns_it|silent_burial|revisionism|doubling_down|deflection|insufficient_data"),

  -- Evidence
  evidence_url          STRING    OPTIONS(description="URL of the article containing accountability evidence"),
  evidence_snippet      STRING    OPTIONS(description="Relevant text excerpt from evidence article (<=500 chars)"),

  -- Scan metadata
  window_days           INT64     OPTIONS(description="Number of days of subsequent content scanned"),
  articles_scanned      INT64     OPTIONS(description="Number of subsequent articles examined"),
  llm_model             STRING    OPTIONS(description="LLM model used for classification (e.g. qwen2.5:32b)"),

  -- Timestamps
  classified_at         TIMESTAMP NOT NULL OPTIONS(description="When this classification was produced"),
  created_at            TIMESTAMP NOT NULL OPTIONS(description="When this record was first inserted"),
  updated_at            TIMESTAMP NOT NULL OPTIONS(description="When this record was last updated")
)
PARTITION BY DATE(classified_at)
CLUSTER BY pundit_id, accountability_class
OPTIONS (
  description = "Accountability dimension (7th scoring axis): how pundits behave after missed predictions. Linked to prediction_ledger by prediction_hash."
);
