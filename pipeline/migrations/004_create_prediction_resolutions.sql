-- Migration: 004_create_prediction_resolutions
-- Issue: #112 — Prediction Resolution Engine — Auto-score Pundit Accuracy
-- Description: Stores scored outcomes for predictions in the cryptographic ledger.
--
-- Resolution states: PENDING | CORRECT | INCORRECT | VOID
-- Scoring: Brier score for probabilistic claims, binary accuracy for yes/no claims.
-- This table is NOT append-only — resolution_status updates are expected as outcomes arrive.

CREATE TABLE IF NOT EXISTS `{project_id}.gold_layer.prediction_resolutions`
(
  -- FK to prediction_ledger
  prediction_hash       STRING    NOT NULL OPTIONS(description="SHA-256 FK to gold_layer.prediction_ledger.prediction_hash"),

  -- Resolution state
  resolution_status     STRING    NOT NULL OPTIONS(description="PENDING|CORRECT|INCORRECT|VOID"),
  resolved_at           TIMESTAMP OPTIONS(description="When the resolution was determined"),
  resolver              STRING    OPTIONS(description="auto|manual — how resolution was determined"),

  -- Scoring
  brier_score           FLOAT64   OPTIONS(description="Brier score (0-1) for probabilistic claims; NULL for binary claims"),
  binary_correct        BOOL      OPTIONS(description="True/False for yes/no claims; NULL for probabilistic claims"),
  timeliness_weight     FLOAT64   OPTIONS(description="Weight multiplier based on how early the prediction was made (1.0 = baseline)"),
  weighted_score        FLOAT64   OPTIONS(description="Final weighted score combining accuracy and timeliness"),

  -- Outcome evidence
  outcome_source        STRING    OPTIONS(description="Which data source confirmed the outcome: sportsdataio|pfr|spotrac|otc|manual"),
  outcome_reference_id  STRING    OPTIONS(description="External ID from the outcome source (e.g. game_id, transaction_id)"),
  outcome_notes         STRING    OPTIONS(description="Human-readable description of the actual outcome"),

  -- Metadata
  created_at            TIMESTAMP NOT NULL OPTIONS(description="When this resolution record was first created"),
  updated_at            TIMESTAMP NOT NULL OPTIONS(description="When this resolution record was last updated")
)
PARTITION BY DATE(created_at)
CLUSTER BY resolution_status, resolver
OPTIONS (
  description = "Scored outcomes for pundit predictions. Linked to prediction_ledger by prediction_hash."
);
