-- backfill: issue #920
-- Migration 028: Knowledge Graph Schema — Phase 1 additive DDL (#920)
--
-- Adds new tables required by Phase 2 migration scripts:
--   silver_v2_claims.claim_entity_link       — many-to-many claim↔entity junction
--   silver_v2_claims.claim_state_history     — SCD-2 for claim resolution status
--   silver_v2_claims.entity_resolution_queue — queue for unresolvable entity strings
--
-- Adds new columns (additive, no existing data touched):
--   silver_v2_core.entity_attribute_event.value_entity_id  — typed entity-to-entity edges
--   silver_v2_claims.claim.legacy_prediction_hash          — preserves original prediction_hash
--   silver_v2_claims.claim.legacy_chain_hash               — preserves original chain_hash
--
-- Design notes:
--   - All additions are IF NOT EXISTS / ADD COLUMN IF NOT EXISTS — fully idempotent
--   - entity_timeline is already a VIEW in migration 015; no change needed here
--   - legacy_* columns on claim table support migration idempotency keying
--
-- Usage:
--   export PROJECT_ID=cap-alpha-protocol
--   envsubst < pipeline/migrations/028_kg_schema_additive.sql | \
--     bq query --use_legacy_sql=false --project_id=$PROJECT_ID

-- ============================================================
-- 1. claim_entity_link — junction table replacing subject_entity_ids string
-- ============================================================
CREATE TABLE IF NOT EXISTS `{project_id}.silver_v2_claims.claim_entity_link`
(
  link_id        STRING    NOT NULL  OPTIONS(description="UUIDv4 for this link row"),
  claim_id       STRING    NOT NULL  OPTIONS(description="FK to silver_v2_claims.claim.claim_id"),
  entity_id      STRING    NOT NULL  OPTIONS(description="FK to silver_v2_core.entity.entity_id"),
  entity_role    STRING    NOT NULL  OPTIONS(description="subject | object | context | comparison — role the entity plays in this claim"),
  ordinal        INT64               OPTIONS(description="Preserves order when a claim names multiple entities in the same role"),
  created_at     TIMESTAMP NOT NULL  OPTIONS(description="UTC wall-clock insertion time")
)
PARTITION BY DATE(created_at)
CLUSTER BY entity_id, claim_id
OPTIONS (
  description = "Many-to-many junction between claims and entities. Replaces the subject_entity_ids STRING array on claim. Enables proper entity_id lookups and role-aware conflict detection."
);

-- ============================================================
-- 2. claim_state_history — SCD-2 for claim resolution status
-- ============================================================
CREATE TABLE IF NOT EXISTS `{project_id}.silver_v2_claims.claim_state_history`
(
  history_id      STRING    NOT NULL  OPTIONS(description="UUIDv4 for this state row"),
  claim_id        STRING    NOT NULL  OPTIONS(description="FK to silver_v2_claims.claim.claim_id"),
  state           STRING    NOT NULL  OPTIONS(description="PENDING | VOID | CORRECT | INCORRECT | PARTIAL | UNVERIFIABLE"),
  effective_from  TIMESTAMP NOT NULL  OPTIONS(description="When this state became effective"),
  effective_to    TIMESTAMP           OPTIONS(description="When this state was superseded. NULL = current state."),
  effective_source STRING   NOT NULL  OPTIONS(description="asserted_at for backfill rows | ingestion for ongoing new claims"),
  resolution_id   STRING              OPTIONS(description="FK to silver_v2_claims.resolution.resolution_id when state is not PENDING"),
  brier_score     FLOAT64             OPTIONS(description="Brier score for this resolution, if applicable"),
  binary_correct  BOOL                OPTIONS(description="True if prediction was correct, false if not, null if pending"),
  notes           STRING              OPTIONS(description="Human-readable notes about this state transition"),
  created_at      TIMESTAMP NOT NULL  OPTIONS(description="UTC wall-clock insertion time")
)
PARTITION BY DATE(effective_from)
CLUSTER BY claim_id, state
OPTIONS (
  description = "SCD-2 history of claim resolution status. One open row (effective_to IS NULL) per claim at any time. Backfilled rows use effective_source=asserted_at; ongoing rows use effective_source=ingestion."
);

-- ============================================================
-- 3. entity_resolution_queue — pending unresolvable entity strings
-- ============================================================
CREATE TABLE IF NOT EXISTS `{project_id}.silver_v2_claims.entity_resolution_queue`
(
  queue_id              STRING    NOT NULL  OPTIONS(description="UUIDv4 for this queue entry"),
  raw_entity_string     STRING    NOT NULL  OPTIONS(description="The raw entity string that failed resolution"),
  normalized_string     STRING              OPTIONS(description="Lowercased/cleaned version of raw_entity_string"),
  domain                STRING              OPTIONS(description="Domain context: sports.nfl, politics, finance, etc."),
  placeholder_entity_id STRING    NOT NULL  OPTIONS(description="FK to silver_v2_core.entity — the unresolved placeholder created for this string"),
  first_seen_at         TIMESTAMP NOT NULL  OPTIONS(description="When this unresolvable string was first encountered"),
  last_attempted_at     TIMESTAMP           OPTIONS(description="When resolution was last attempted"),
  attempt_count         INT64               OPTIONS(description="Number of resolution attempts made"),
  status                STRING    NOT NULL  OPTIONS(description="PENDING | RESOLVED | MANUAL_REQUIRED | DUPLICATE"),
  resolved_entity_id    STRING              OPTIONS(description="Populated when status=RESOLVED — the real entity_id this placeholder maps to"),
  resolved_by           STRING              OPTIONS(description="auto:{process} or manual:{user} — who resolved this entry"),
  resolved_at           TIMESTAMP           OPTIONS(description="When this entry was resolved"),
  notes                 STRING              OPTIONS(description="Free-text notes for manual triage"),
  created_at            TIMESTAMP NOT NULL  OPTIONS(description="UTC wall-clock insertion time")
)
PARTITION BY DATE(created_at)
CLUSTER BY status, domain
OPTIONS (
  description = "Queue of entity strings that could not be resolved to a silver_v2_core.entity row during migration or extraction. Observable via SELECT * WHERE status=PENDING. Batchable for automated re-resolution."
);

-- ============================================================
-- 4. ADD COLUMN: entity_attribute_event.value_entity_id
-- ============================================================
ALTER TABLE `{project_id}.silver_v2_core.entity_attribute_event`
  ADD COLUMN IF NOT EXISTS value_entity_id STRING
    OPTIONS(description="When attr references another entity (team, agent, coach), stores the FK to silver_v2_core.entity.entity_id. Keep value as human-readable label.");

-- ============================================================
-- 5. ADD COLUMNS: claim.legacy_prediction_hash + legacy_chain_hash
-- ============================================================
ALTER TABLE `{project_id}.silver_v2_claims.claim`
  ADD COLUMN IF NOT EXISTS legacy_prediction_hash STRING
    OPTIONS(description="Original prediction_hash from gold_layer.prediction_ledger. Used for idempotency keying during Phase 2 migration. Null for new claims created post-migration.");

ALTER TABLE `{project_id}.silver_v2_claims.claim`
  ADD COLUMN IF NOT EXISTS legacy_chain_hash STRING
    OPTIONS(description="Original chain_hash from gold_layer.prediction_ledger. Preserves the old cryptographic chain record alongside the new silver_v2 chain.");
