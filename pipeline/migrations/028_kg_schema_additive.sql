-- Migration 028: KG Schema Additive — Phase 1 of #920
-- Issue: #920 — silver_v2 graph completion
-- Description: Adds claim_entity_link (junction replacing subject_entity_ids string),
--              claim_state_history (SCD-2 for claim resolution status),
--              entity_resolution_queue (work queue for unresolvable entity references),
--              and value_entity_id column on entity_attribute_event.
--
-- Design: Additive only — no existing tables are dropped or altered destructively.
--         claim_entity_link replaces the STRING subject_entity_ids array with a
--         proper many-to-many join table. claim_state_history provides a full SCD-2
--         audit trail of claim state transitions (PENDING → CORRECT/INCORRECT/etc).
--
-- Usage:
--   export PROJECT_ID=cap-alpha-protocol
--   envsubst < pipeline/migrations/028_kg_schema_additive.sql | \
--     bq query --use_legacy_sql=false --project_id=$PROJECT_ID

-- ============================================================
-- 1. claim_entity_link — proper junction table
-- ============================================================
-- Replaces the ARRAY<STRING> subject_entity_ids on silver_v2_claims.claim.
-- Many claims name multiple entities; this table preserves role and order.

CREATE TABLE IF NOT EXISTS `{project_id}.silver_v2_claims.claim_entity_link`
(
  link_id        STRING    NOT NULL  OPTIONS(description="UUIDv4 for this link row"),
  claim_id       STRING    NOT NULL  OPTIONS(description="FK to silver_v2_claims.claim.claim_id"),
  entity_id      STRING    NOT NULL  OPTIONS(description="FK to silver_v2_core.entity.entity_id. May be a placeholder 'unresolved:{sha256}' sentinel."),
  entity_role    STRING    NOT NULL  OPTIONS(description="Role of this entity in the claim: subject|object|context|comparison"),
  ordinal        INT64               OPTIONS(description="Preserves insertion order when multiple entities share the same role"),
  created_at     TIMESTAMP NOT NULL  OPTIONS(description="UTC wall-clock insertion time")
)
PARTITION BY DATE(created_at)
CLUSTER BY entity_id, claim_id
OPTIONS (
  description = "Junction table linking claims to the entities they reference. Replaces the ARRAY<STRING> subject_entity_ids field with a proper many-to-many relationship that preserves role and order. Enables O(1) lookups by entity_id."
);

-- ============================================================
-- 2. claim_state_history — SCD-2 audit trail for claim status
-- ============================================================
-- Records every state transition a claim goes through.
-- PENDING → VOID | CORRECT | INCORRECT | PARTIAL | UNVERIFIABLE
-- effective_to IS NULL means this is the current state.

CREATE TABLE IF NOT EXISTS `{project_id}.silver_v2_claims.claim_state_history`
(
  history_id       STRING    NOT NULL  OPTIONS(description="UUIDv4 for this history row"),
  claim_id         STRING    NOT NULL  OPTIONS(description="FK to silver_v2_claims.claim.claim_id"),
  state            STRING    NOT NULL  OPTIONS(description="PENDING|VOID|CORRECT|INCORRECT|PARTIAL|UNVERIFIABLE"),
  effective_from   TIMESTAMP NOT NULL  OPTIONS(description="When this state became active"),
  effective_to     TIMESTAMP           OPTIONS(description="When this state was superseded. NULL = current state."),
  effective_source STRING    NOT NULL  OPTIONS(description="'asserted_at' for backfill rows | 'ingestion' for new claims written by the pipeline"),
  resolution_id    STRING              OPTIONS(description="FK to silver_v2_claims.resolution.resolution_id when state != PENDING"),
  brier_score      FLOAT64             OPTIONS(description="Brier score from the resolution, populated when resolved"),
  binary_correct   BOOL                OPTIONS(description="True/false outcome for binary claims, populated when resolved"),
  notes            STRING              OPTIONS(description="Human-readable notes about this state transition"),
  created_at       TIMESTAMP NOT NULL  OPTIONS(description="UTC wall-clock insertion time")
)
PARTITION BY DATE(effective_from)
CLUSTER BY claim_id, state
OPTIONS (
  description = "SCD-2 audit trail of claim state transitions. Every state change appends a new row (closing effective_to on the previous row). The current state has effective_to IS NULL. Used to answer 'when did this claim become CORRECT?' and 'how long was it PENDING?'"
);

-- ============================================================
-- 3. entity_resolution_queue — work queue for unresolved entities
-- ============================================================
-- When extraction cannot resolve a mention to a known entity_id,
-- a placeholder entity is created and this queue row is inserted.
-- A background process or human resolves PENDING items.

CREATE TABLE IF NOT EXISTS `{project_id}.silver_v2_claims.entity_resolution_queue`
(
  queue_id              STRING    NOT NULL  OPTIONS(description="UUIDv4 for this queue row"),
  raw_entity_string     STRING    NOT NULL  OPTIONS(description="The raw entity string that failed resolution (e.g. 'Patrick Mahommes')"),
  normalized_string     STRING              OPTIONS(description="Lowercased, trimmed, deaccented version for fuzzy matching"),
  domain                STRING              OPTIONS(description="Domain of the claim this entity appeared in (e.g. 'nfl', 'sports.nfl')"),
  placeholder_entity_id STRING    NOT NULL  OPTIONS(description="FK to silver_v2_core.entity — the unresolved placeholder that was created"),
  first_seen_at         TIMESTAMP NOT NULL  OPTIONS(description="When this string first appeared in a claim"),
  last_attempted_at     TIMESTAMP           OPTIONS(description="When resolution was last attempted. NULL = never attempted beyond initial insert."),
  attempt_count         INT64               OPTIONS(description="Number of resolution attempts made so far"),
  status                STRING    NOT NULL  OPTIONS(description="PENDING|RESOLVED|MANUAL_REQUIRED|DUPLICATE"),
  resolved_entity_id    STRING              OPTIONS(description="Populated when status=RESOLVED — the real entity_id this mention maps to"),
  resolved_by           STRING              OPTIONS(description="'auto:{process}' or 'manual:{user}' — who resolved this entry"),
  resolved_at           TIMESTAMP           OPTIONS(description="When this entry was resolved"),
  notes                 STRING              OPTIONS(description="Human-readable notes about the resolution decision"),
  created_at            TIMESTAMP NOT NULL  OPTIONS(description="UTC wall-clock insertion time")
)
PARTITION BY DATE(created_at)
CLUSTER BY status, domain
OPTIONS (
  description = "Work queue for entity mentions that could not be resolved to a known silver_v2_core.entity row at extraction time. A placeholder entity is created immediately so claims are never orphaned. This queue tracks pending resolutions for later automated or manual triage."
);

-- ============================================================
-- 4. Add value_entity_id to entity_attribute_event (additive)
-- ============================================================
-- When attr references another entity (team, agent, coach, opponent),
-- value_entity_id stores the entity_id for typed traversal.
-- value (STRING) is kept for display; value_entity_id enables graph walks.

ALTER TABLE `{project_id}.silver_v2_core.entity_attribute_event`
  ADD COLUMN IF NOT EXISTS value_entity_id STRING
  OPTIONS(description="When the attribute value is an entity reference (e.g. attr='team'), this is the FK to silver_v2_core.entity.entity_id. Keep 'value' for display; use value_entity_id for graph traversal.");
