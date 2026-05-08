-- Migration 016: Create claim_dedup_log table (Issue #808 Phase 0)
--
-- Stores every claim that was suppressed as a duplicate of an existing ledger entry.
-- Duplicates are NOT dropped -- they are logged here instead of being written to
-- prediction_ledger, preserving an audit trail of suppressed exact matches.
--
-- match_type starts as 'exact' (Phase 0). Future phases will add 'semantic'.
--
-- Run against the project with:
--   bq query --use_legacy_sql=false --project_id=<PROJECT_ID> \
--     < pipeline/migrations/016_create_claim_dedup_log.sql

CREATE TABLE IF NOT EXISTS `${PROJECT_ID}.gold_layer.claim_dedup_log`
(
  -- The hash that was suppressed (same key as prediction_hash in prediction_ledger)
  dupe_hash         STRING    NOT NULL OPTIONS(description="SHA-256 hash of the incoming claim that was flagged as a duplicate"),
  -- The hash of the existing canonical claim in the ledger
  canonical_hash    STRING    NOT NULL OPTIONS(description="prediction_hash of the first/canonical claim this duplicate matched"),
  -- The norm key that triggered the match
  norm_key          STRING    NOT NULL OPTIONS(description="claim_norm_key value used for the exact match"),
  -- Provenance of the duplicate claim
  pundit_id         STRING    NOT NULL OPTIONS(description="pundit_id of the source that produced the duplicate claim"),
  -- When this dedup event was recorded
  ingested_at       TIMESTAMP NOT NULL OPTIONS(description="UTC timestamp when this dedup event was logged"),
  -- Phase 0 = 'exact'; future phases may add 'semantic'
  match_type        STRING    NOT NULL DEFAULT 'exact' OPTIONS(description="Dedup match strategy: 'exact' (Phase 0) or 'semantic' (Phase 1+)")
)
PARTITION BY DATE(ingested_at)
CLUSTER BY pundit_id, match_type
OPTIONS (
  description = "Audit log of claim deduplication events. Claims suppressed from prediction_ledger are written here instead. Append-only."
);
