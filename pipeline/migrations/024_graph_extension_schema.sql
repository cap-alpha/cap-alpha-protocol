-- Migration 024: Graph Extension Schema — Entities + Sidecar + claim_edges View (#807)
--
-- Architecture decision: SIDECAR pattern — NOT altering the append-only ledger.
-- The existing gold_layer.prediction_ledger is sacred and immutable. All graph-
-- extension metadata lives in prediction_ledger_graph_extension, joined on
-- prediction_hash. The claim_edges view stitches them together for consumers.
--
-- Tables created:
--   nfl_dead_money.entities                            — canonical entity nodes
--   nfl_dead_money.prediction_ledger_graph_extension  — sidecar graph metadata
--   gold_layer.claim_edges                             — view joining ledger + sidecar
--
-- Usage:
--   export PROJECT_ID=cap-alpha-protocol
--   envsubst < pipeline/migrations/024_graph_extension_schema.sql | \
--     bq query --use_legacy_sql=false --project_id=$PROJECT_ID

-- ============================================================
-- 1. entities — canonical entity nodes
-- ============================================================
-- entity_id format: '{type}_{slug}_{shorthash6}'
-- Examples:
--   player_patrick-mahomes_e3f9a2
--   team_kansas-city-chiefs_a1b2c3
--   award_super-bowl-mvp_f4e5d6

CREATE TABLE IF NOT EXISTS `{project_id}.nfl_dead_money.entities`
(
  entity_id           STRING    NOT NULL  OPTIONS(description="Stable composite ID: '{type}_{slug}_{shorthash6}'. Never mutable after first write."),
  entity_type         STRING    NOT NULL  OPTIONS(description="PLAYER|TEAM|GAME|AWARD|COACH|ORGANIZATION|EVENT"),
  canonical_name      STRING    NOT NULL  OPTIONS(description="Primary human-readable name for this entity."),
  aliases             ARRAY<STRING>       OPTIONS(description="Alternative names, nicknames, abbreviations this entity is known by."),
  domain              STRING    NOT NULL  OPTIONS(description="Top-level domain: SPORTS|FINANCE|POLITICS. Defaults to SPORTS."),
  metadata            JSON                OPTIONS(description="Flexible domain-specific attributes: {position, sport, team_id, division, etc.}."),
  first_seen_at       TIMESTAMP           OPTIONS(description="Earliest timestamp this entity appeared in a claim."),
  last_seen_at        TIMESTAMP           OPTIONS(description="Most recent timestamp this entity appeared in a claim."),
  claim_count         INT64               OPTIONS(description="Running count of claims referencing this entity. Updated on upsert."),
  created_at          TIMESTAMP           OPTIONS(description="UTC wall-clock time this entity was first inserted.")
)
PARTITION BY DATE(created_at)
CLUSTER BY entity_type, domain
OPTIONS (
  description = "Canonical entity node registry. One row per real-world entity referenced in pundit predictions. entity_id is the stable foreign key used in prediction_ledger_graph_extension.entity_ids."
);

-- ============================================================
-- 2. prediction_ledger_graph_extension — sidecar graph metadata
-- ============================================================
-- FK: prediction_hash → gold_layer.prediction_ledger.prediction_hash
-- This table is write-once per prediction_hash by the enrichment pipeline;
-- updates go via MERGE (upsert_graph_extension in db_manager.py).

CREATE TABLE IF NOT EXISTS `{project_id}.nfl_dead_money.prediction_ledger_graph_extension`
(
  prediction_hash               STRING    NOT NULL  OPTIONS(description="FK to gold_layer.prediction_ledger.prediction_hash. SHA-256 hex (64 chars)."),
  entity_ids                    ARRAY<STRING>       OPTIONS(description="All entity_id references found in this claim."),
  primary_entity_id             STRING              OPTIONS(description="The main subject entity_id of the claim (the entity being predicted about)."),
  claim_type                    STRING              OPTIONS(description="GAME_OUTCOME|TRADE_MOVE|PLAYER_PROP|AWARD|DRAFT|CONTRACT|OTHER"),
  domain                        STRING              OPTIONS(description="SPORTS|FINANCE|POLITICS. Inherited from the claim context."),
  asserted_state                JSON                OPTIONS(description="Structured prediction payload: {outcome, target_value, operator, comparator_entity_id, etc.}."),
  embedding                     ARRAY<FLOAT64>      OPTIONS(description="nomic-embed-text dense vector for semantic dedup/search. NULL until async embedding job runs."),
  cluster_id                    STRING              OPTIONS(description="Cluster assignment from dedup pipeline (#808). NULL until clustering runs."),
  entity_resolution_confidence  FLOAT64             OPTIONS(description="0.0–1.0 confidence that entity_ids were correctly resolved from raw claim text."),
  created_at                    TIMESTAMP           OPTIONS(description="UTC wall-clock time this sidecar row was first written."),
  updated_at                    TIMESTAMP           OPTIONS(description="UTC wall-clock time this sidecar row was last updated (e.g. cluster_id backfill).")
)
PARTITION BY DATE(created_at)
CLUSTER BY primary_entity_id, claim_type
OPTIONS (
  description = "Sidecar graph extension for gold_layer.prediction_ledger. Stores entity links, claim type, embedding vector, and cluster ID without mutating the append-only ledger. Joined on prediction_hash."
);

-- ============================================================
-- 3. claim_edges view — joined consumer surface
-- ============================================================
-- Consumers query this view instead of joining manually.
-- LEFT JOIN means all ledger rows appear; sidecar columns are nullable
-- for claims not yet enriched by the entity-resolution pipeline.

CREATE OR REPLACE VIEW `{project_id}.gold_layer.claim_edges` AS
SELECT
  p.prediction_hash                      AS claim_id,
  p.pundit_id,
  p.pundit_name,
  p.raw_assertion_text,
  p.extracted_claim,
  p.claim_category,
  p.ingestion_timestamp                  AS timestamp_made,
  p.season_year,
  p.target_player_id,
  p.target_player_name,
  p.target_team,
  p.target_entity,
  p.stance,
  p.sport,
  p.resolution_status                    AS resolution,
  p.resolved_at,
  p.resolution_notes,
  p.chain_hash,
  p.source_url,
  p.prompt_version,
  p.llm_provider,
  p.llm_model,
  -- graph extension fields (nullable until enriched by entity-resolution pipeline)
  e.entity_ids,
  e.primary_entity_id,
  e.claim_type,
  e.domain,
  e.asserted_state,
  e.embedding,
  e.cluster_id,
  e.entity_resolution_confidence
FROM `{project_id}.gold_layer.prediction_ledger` p
LEFT JOIN `{project_id}.nfl_dead_money.prediction_ledger_graph_extension` e
  ON p.prediction_hash = e.prediction_hash;
