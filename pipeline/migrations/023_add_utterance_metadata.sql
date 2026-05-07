-- Migration 023: add metadata fields to silver_v2_claims.raw_utterance
-- Issues: #674 (persist existing metadata), #675 (resolution_condition, hedge_level, 7B verification)
--
-- All new columns are NULLABLE for full backward compatibility.
-- The 32B extraction model already returns the subscore/stance/horizon/note fields
-- but write_raw_utterances() was discarding them. This migration adds the BQ
-- columns so they can be persisted. The verification columns are populated by
-- the new 7B post-extraction verification pass.
--
-- Usage:
--   export PROJECT_ID=cap-alpha-protocol
--   envsubst < pipeline/migrations/023_add_utterance_metadata.sql | \
--     bq query --use_legacy_sql=false --project_id=$PROJECT_ID

-- Part A: subscore columns already produced by 32B but previously discarded (#674)
ALTER TABLE `{project_id}.silver_v2_claims.raw_utterance`
  ADD COLUMN IF NOT EXISTS subscore_subject_specificity FLOAT64,
  ADD COLUMN IF NOT EXISTS subscore_predicate_falsifiability FLOAT64,
  ADD COLUMN IF NOT EXISTS subscore_threshold_concreteness FLOAT64,
  ADD COLUMN IF NOT EXISTS subscore_resolution_horizon_defined FLOAT64,
  ADD COLUMN IF NOT EXISTS subscore_evidence_accessibility FLOAT64,
  ADD COLUMN IF NOT EXISTS stance STRING,
  ADD COLUMN IF NOT EXISTS prediction_horizon_days INT64,
  ADD COLUMN IF NOT EXISTS confidence_note STRING,

-- Part B: new fields added to the extraction prompt (#675)
  ADD COLUMN IF NOT EXISTS resolution_condition STRING,
  ADD COLUMN IF NOT EXISTS hedge_level STRING,

-- Part B: 7B post-extraction verification pass (#675)
  ADD COLUMN IF NOT EXISTS claim_text_alignment FLOAT64,
  ADD COLUMN IF NOT EXISTS hallucination_risk STRING,
  ADD COLUMN IF NOT EXISTS verification_flags ARRAY<STRING>,
  ADD COLUMN IF NOT EXISTS quality_score FLOAT64,
  ADD COLUMN IF NOT EXISTS needs_review BOOL;
