-- Migration 028: silver_v2 temporal knowledge graph — additive schema DDL
-- Issue: #920 — Phase 1: silver_v2 KG schema DDL (claim_entity_link, claim_state_history,
--               entity_resolution_queue)
-- backfill: issue #920
--
-- Phase 1: ADDITIVE ONLY — no tables are dropped or replaced.
-- All statements are idempotent (CREATE TABLE IF NOT EXISTS / ADD COLUMN IF NOT EXISTS).
--
-- Summary of changes:
--   1. silver_v2_claims.claim_entity_link       — junction table replacing subject_entity_ids STRING
--   2. silver_v2_claims.entity_resolution_queue — holds unresolvable entity strings pending triage
--   3. silver_v2_claims.claim_state_history     — SCD-2 for claim resolution status
--   4. silver_v2_core.entity_attribute_event    — ADD COLUMN value_entity_id STRING
--   5. silver_v2_claims.claim                   — ADD COLUMN legacy_prediction_hash STRING
--   6. silver_v2_claims.claim                   — ADD COLUMN legacy_chain_hash STRING
--
-- entity_timeline is NOT dropped here — it remains as the view defined in migration 015.
-- Phase 5 will archive entity_timeline after confirming no writers remain.
--
-- Usage:
--   source .env
--   python3 pipeline/scripts/apply_kg_schema.py
-- OR via the standard migration runner:
--   python3 pipeline/scripts/apply_migrations.py

-- ============================================================
-- 1. silver_v2_claims.claim_entity_link
--    Junction table: proper many-to-many between claims and entities.
--    Replaces the subject_entity_ids ARRAY<STRING> column on claim.
-- ============================================================
CREATE TABLE IF NOT EXISTS `{project_id}.silver_v2_claims.claim_entity_link`
(
  link_id     STRING    NOT NULL  OPTIONS(description="UUIDv7 for this link record"),
  claim_id    STRING    NOT NULL  OPTIONS(description="FK to silver_v2_claims.claim.claim_id"),
  entity_id   STRING    NOT NULL  OPTIONS(description="FK to silver_v2_core.entity.entity_id (may be a placeholder 'unresolved:...' entity)"),
  entity_role STRING    NOT NULL  OPTIONS(description="Role of the entity in the claim: subject | object | context | comparison"),
  ordinal     INT64               OPTIONS(description="1-based position when a claim names multiple entities in the same role. NULL when only one entity per role."),
  created_at  TIMESTAMP NOT NULL  OPTIONS(description="UTC wall-clock insertion time")
)
PARTITION BY DATE(created_at)
CLUSTER BY entity_id, claim_id
OPTIONS (
  description = "Junction table linking claims to their referenced entities. Replaces the subject_entity_ids ARRAY<STRING> field on silver_v2_claims.claim. Supports proper entity-id lookups, role semantics (subject/object/context/comparison), and multi-entity claims via ordinal."
);

-- ============================================================
-- 2. silver_v2_claims.entity_resolution_queue
--    Holds unresolvable entity strings pending automated or manual triage.
--    Every unresolvable entity gets a placeholder in silver_v2_core.entity
--    AND a row here so resolution is observable and batchable.
-- ============================================================
CREATE TABLE IF NOT EXISTS `{project_id}.silver_v2_claims.entity_resolution_queue`
(
  queue_id              STRING    NOT NULL  OPTIONS(description="UUIDv7 for this queue entry"),
  raw_entity_string     STRING    NOT NULL  OPTIONS(description="The exact entity string the extractor produced that failed resolution"),
  normalized_string     STRING              OPTIONS(description="Lowercased and whitespace-normalized version of raw_entity_string"),
  domain                STRING              OPTIONS(description="Domain context for the failed resolution, e.g. sports.nfl, politics.us"),
  placeholder_entity_id STRING    NOT NULL  OPTIONS(description="FK to silver_v2_core.entity.entity_id for the 'unresolved:{sha256}' placeholder created at queue time"),
  first_seen_at         TIMESTAMP NOT NULL  OPTIONS(description="UTC time this raw_entity_string was first encountered and queued"),
  last_attempted_at     TIMESTAMP           OPTIONS(description="UTC time of the most recent resolution attempt. NULL if never retried."),
  attempt_count         INT64               OPTIONS(description="Number of automated resolution attempts made so far. Set to 0 at insert time by the caller."),
  status                STRING    NOT NULL  OPTIONS(description="PENDING | RESOLVED | MANUAL_REQUIRED | DUPLICATE. Set to PENDING at insert time by the caller."),
  resolved_entity_id    STRING              OPTIONS(description="FK to silver_v2_core.entity.entity_id of the real entity, populated when status = RESOLVED"),
  resolved_by           STRING              OPTIONS(description="How resolution happened: 'auto:{process_name}' or 'manual:{user_id}'"),
  resolved_at           TIMESTAMP           OPTIONS(description="UTC time this queue entry was resolved"),
  notes                 STRING              OPTIONS(description="Human-readable notes for manual triage or auto-resolution context"),
  created_at            TIMESTAMP NOT NULL  OPTIONS(description="UTC wall-clock insertion time")
)
PARTITION BY DATE(created_at)
CLUSTER BY status, domain
OPTIONS (
  description = "Resolution queue for entity strings that failed automated resolution during claim extraction or migration. Each entry has a placeholder entity in silver_v2_core.entity keyed as 'unresolved:{sha256_of_normalized_string}'. Status lifecycle: PENDING -> RESOLVED | MANUAL_REQUIRED | DUPLICATE. Batch-resolvable by status+domain."
);

-- ============================================================
-- 3. silver_v2_claims.claim_state_history
--    SCD-2 (slowly-changing dimension type 2) for claim resolution status.
--    One open row per claim (effective_to IS NULL = current state).
--    Transitions close the prior open row and append a new open row.
-- ============================================================
CREATE TABLE IF NOT EXISTS `{project_id}.silver_v2_claims.claim_state_history`
(
  history_id       STRING    NOT NULL  OPTIONS(description="UUIDv7 for this state history record"),
  claim_id         STRING    NOT NULL  OPTIONS(description="FK to silver_v2_claims.claim.claim_id"),
  state            STRING    NOT NULL  OPTIONS(description="PENDING | VOID | CORRECT | INCORRECT | PARTIAL | UNVERIFIABLE"),
  effective_from   TIMESTAMP NOT NULL  OPTIONS(description="When this state became effective. For PENDING rows from backfill, equals claim asserted_at (or ingestion_timestamp if asserted_at unavailable)."),
  effective_to     TIMESTAMP           OPTIONS(description="When this state was superseded. NULL = current (open) row."),
  effective_source STRING    NOT NULL  OPTIONS(description="How effective_from was determined: 'asserted_at' for backfilled claims | 'ingestion' for ongoing claims written post-cutover"),
  resolution_id    STRING              OPTIONS(description="FK to silver_v2_claims.resolution.resolution_id. Populated when state is not PENDING."),
  brier_score      FLOAT64             OPTIONS(description="Brier score for this resolution outcome. NULL for PENDING rows."),
  binary_correct   BOOL                OPTIONS(description="TRUE if resolution outcome was correct; FALSE if incorrect. NULL for PENDING, VOID, UNVERIFIABLE."),
  notes            STRING              OPTIONS(description="Human-readable explanation of the state transition"),
  created_at       TIMESTAMP NOT NULL  OPTIONS(description="UTC wall-clock time this history row was written")
)
PARTITION BY DATE(effective_from)
CLUSTER BY claim_id, state
OPTIONS (
  description = "SCD-2 state history for silver_v2_claims.claim. Each row represents a period when a claim held a given resolution state. The open row (effective_to IS NULL) is the current state. Transitions close the prior open row and append a new open row. Supports full audit trail of PENDING -> CORRECT/INCORRECT/VOID/PARTIAL/UNVERIFIABLE."
);

-- ============================================================
-- 4. silver_v2_core.entity_attribute_event — add value_entity_id
--    When attr references another entity (e.g. team, agent, coach),
--    value_entity_id holds the FK to silver_v2_core.entity.
--    value (STRING) remains as the human-readable display label.
-- ============================================================
ALTER TABLE `{project_id}.silver_v2_core.entity_attribute_event`
  ADD COLUMN IF NOT EXISTS value_entity_id STRING
    OPTIONS(description="FK to silver_v2_core.entity.entity_id when this attribute value references another entity (e.g. attr='team', attr='agent', attr='coach'). NULL for scalar attributes. Populate alongside value (STRING label) for entity-typed attrs.");

-- ============================================================
-- 5. silver_v2_claims.claim — add legacy_prediction_hash
--    Preserves the original gold_layer.prediction_ledger prediction_hash
--    verbatim for cross-reference and idempotent migration keying.
-- ============================================================
ALTER TABLE `{project_id}.silver_v2_claims.claim`
  ADD COLUMN IF NOT EXISTS legacy_prediction_hash STRING
    OPTIONS(description="The original prediction_hash from gold_layer.prediction_ledger (SHA-256 of ingestion_timestamp|source_url|pundit_id|raw_assertion_text). Preserved verbatim for cross-reference and migration idempotency keying. NULL for claims written natively to silver_v2 after cutover.");

-- ============================================================
-- 6. silver_v2_claims.claim — add legacy_chain_hash
--    Preserves the original chain_hash from gold_layer.prediction_ledger
--    so both the old and new cryptographic audit chains are traceable.
-- ============================================================
ALTER TABLE `{project_id}.silver_v2_claims.claim`
  ADD COLUMN IF NOT EXISTS legacy_chain_hash STRING
    OPTIONS(description="The original chain_hash from gold_layer.prediction_ledger. Preserved verbatim alongside legacy_prediction_hash. The new silver_v2 chain is computed separately over the silver_v2 payload (UUID + asserted_at + predicate + speaker_entity_id). NULL for claims written natively to silver_v2 after cutover.");
