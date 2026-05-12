-- Migration 027: gold_layer.prediction_ledger_shadow — testability gate shadow table
-- Issue: #824 — feat: claim corpus expansion + quality improvement strategy
-- Description: Holds claims that failed the testability gate (score below threshold
--              or missing required fields). Same schema as prediction_ledger plus
--              shadow_reason and testability_score audit columns.
--
-- Claims land here instead of prediction_ledger when:
--   - testability_score < TESTABILITY_THRESHOLD (env var, default 0.6)
--   - (future) missing subject entity, predicate, timeframe, or resolution criteria
--
-- Usage:
--   export PROJECT_ID=cap-alpha-protocol
--   envsubst < pipeline/migrations/027_add_prediction_ledger_shadow.sql | \
--     bq query --use_legacy_sql=false --project_id=$PROJECT_ID

CREATE TABLE IF NOT EXISTS `{project_id}.gold_layer.prediction_ledger_shadow`
(
  -- Identity & integrity (mirrors prediction_ledger)
  prediction_hash     STRING    NOT NULL OPTIONS(description="SHA-256 of canonical payload (ingestion_timestamp|source_url|pundit_id|raw_assertion_text)"),
  chain_hash          STRING    NOT NULL OPTIONS(description="SHA-256(prediction_hash + previous row's chain_hash). Empty string seed for first row."),

  -- Provenance (mirrors prediction_ledger)
  ingestion_timestamp TIMESTAMP NOT NULL OPTIONS(description="UTC wall-clock time this record entered the shadow ledger"),
  source_url          STRING    NOT NULL OPTIONS(description="Canonical URL of the source article, tweet, or transcript"),
  pundit_id           STRING    NOT NULL OPTIONS(description="Stable slug: e.g. 'adam_schefter', 'pat_mcafee'"),
  pundit_name         STRING    NOT NULL OPTIONS(description="Display name of the pundit"),

  -- Assertion content (mirrors prediction_ledger)
  raw_assertion_text  STRING    NOT NULL OPTIONS(description="Verbatim quote or transcribed text"),
  extracted_claim     STRING    OPTIONS(description="Structured NLP summary of the prediction"),
  claim_category      STRING    OPTIONS(description="One of: player_performance|game_outcome|trade|draft_pick|injury|contract"),

  -- Targeting (mirrors prediction_ledger)
  season_year         INT64     OPTIONS(description="Season year the prediction applies to"),
  target_player_id    STRING    OPTIONS(description="FK to silver_sportsdataio_players.player_id if claim targets a specific player"),
  target_team         STRING    OPTIONS(description="Team abbreviation if claim targets a specific team"),

  -- Sport context (mirrors prediction_ledger)
  sport               STRING    DEFAULT 'NFL' OPTIONS(description="Sport: NFL|MLB|NBA|NHL|NCAAF|NCAAB. Default NFL."),

  -- Resolution (mirrors prediction_ledger — always PENDING at shadow write time)
  resolution_status   STRING    DEFAULT 'PENDING' OPTIONS(description="PENDING|CORRECT|INCORRECT|VOID"),
  resolved_at         TIMESTAMP OPTIONS(description="Populated if shadow claim is later promoted and resolved"),
  resolution_notes    STRING    OPTIONS(description="Human-readable explanation of the scoring decision"),

  -- Shadow-specific audit columns
  shadow_reason       STRING    NOT NULL OPTIONS(description="Why this claim was gated: low_testability | missing_entity | missing_timeframe | missing_predicate"),
  testability_score   FLOAT64   OPTIONS(description="testability_score at gate time; NULL if absent from LLM response")
)
PARTITION BY DATE(ingestion_timestamp)
CLUSTER BY pundit_id, shadow_reason
OPTIONS (
  description = "Shadow ledger for claims that failed the testability gate. Same schema as prediction_ledger plus shadow_reason and testability_score. Partitioned by ingestion date; clustered for fast gate-reason analytics."
);

-- Add gated column to silver_v2_claims.extraction_run (Issue #824)
-- Tracks claims routed to shadow table (low testability_score) separately from
-- suppressed (wrong speech_act_type), which already existed.
ALTER TABLE `{project_id}.silver_v2_claims.extraction_run`
  ADD COLUMN IF NOT EXISTS gated INT64
    OPTIONS(description="Number of promotable claims (assertion/conditional/recall) routed to prediction_ledger_shadow because testability_score was below TESTABILITY_THRESHOLD. Distinct from suppressed (wrong speech_act_type).");
