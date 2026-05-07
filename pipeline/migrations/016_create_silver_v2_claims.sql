-- Migration 016: silver_v2_claims — Claim + Resolution tables (Phase B-0)
-- Issue: #555 — Pivot to general-purpose truth ledger data model
-- Description: Raw utterance capture, structured claim normalization, resolution
--              method registry, and cryptographically chained resolution records.
--
-- Design decisions:
--   - speech_act_type classified inline with LLM extraction (same call)
--   - testability_score stored as runtime artifact; threshold is a pipeline config param
--   - resolution chain uses prev_hash/this_hash matching existing ledger cryptography
--   - resolution_method is a lookup table; adapters are Python importable paths
--
-- Usage:
--   export PROJECT_ID=cap-alpha-protocol
--   envsubst < pipeline/migrations/016_create_silver_v2_claims.sql | \
--     bq query --use_legacy_sql=false --project_id=$PROJECT_ID

CREATE SCHEMA IF NOT EXISTS `{project_id}.silver_v2_claims`;

-- ============================================================
-- 1. raw_utterance — verbatim speech acts from source docs
-- ============================================================
CREATE TABLE IF NOT EXISTS `{project_id}.silver_v2_claims.raw_utterance`
(
  utterance_id            STRING    NOT NULL  OPTIONS(description="UUIDv7 for this utterance"),
  source_doc_id           STRING    NOT NULL  OPTIONS(description="FK to raw source document (e.g. raw_pundit_media row)"),
  speaker_entity_id       STRING    NOT NULL  OPTIONS(description="FK to silver_v2_core.entity.entity_id of the speaker"),
  uttered_at              TIMESTAMP NOT NULL  OPTIONS(description="When the speaker made this utterance"),
  text                    STRING    NOT NULL  OPTIONS(description="Verbatim or lightly cleaned text of the utterance"),
  speech_act_type         STRING    NOT NULL  OPTIONS(description="assertion|conditional|recall|rhetorical_question|hedge|commentary|opinion|analogy|joke — classified by LLM in the same extraction call"),
  testability_score       FLOAT64   NOT NULL  OPTIONS(description="0.0–1.0 score for how empirically testable this utterance is. Threshold for promotion to claim is runtime-configurable, not hardcoded."),
  resolution_horizon      TIMESTAMP           OPTIONS(description="Estimated latest date by which this utterance could be resolved. NULL = unresolvable or open-ended."),
  domain                  STRING    NOT NULL  OPTIONS(description="Primary domain of this utterance, matching domain_taxonomy.domain"),
  extraction_confidence   FLOAT64   NOT NULL  OPTIONS(description="0.0–1.0 LLM confidence in the speech_act_type classification and field extraction"),
  created_at              TIMESTAMP NOT NULL  OPTIONS(description="UTC wall-clock insertion time")
)
PARTITION BY DATE(uttered_at)
CLUSTER BY speaker_entity_id, domain
OPTIONS (
  description = "All verbatim speech acts extracted from source documents. Includes LLM-classified speech_act_type and testability_score. Only rows with speech_act_type in (assertion, conditional, recall) and testability_score >= runtime threshold are promoted to claim."
);

-- ============================================================
-- 2. resolution_method — lookup for resolution adapters
-- ============================================================
CREATE TABLE IF NOT EXISTS `{project_id}.silver_v2_claims.resolution_method`
(
  resolution_method_id    STRING    NOT NULL  OPTIONS(description="Stable slug identifier, e.g. nfl_team_record_sportradar"),
  domain                  STRING    NOT NULL  OPTIONS(description="Domain this method applies to, matching domain_taxonomy.domain"),
  name                    STRING    NOT NULL  OPTIONS(description="Human-readable name, e.g. NFL Team Win-Loss via Sportradar"),
  adapter_path            STRING    NOT NULL  OPTIONS(description="Python callable path: module:function, e.g. pipeline.resolvers.nfl.team_record:resolve"),
  data_source             STRING    NOT NULL  OPTIONS(description="Canonical data source slug, e.g. sportradar.nfl, fred.cpi, fec.elections"),
  config                  JSON                OPTIONS(description="Adapter-specific config JSON, e.g. {\"stat\":\"wins\",\"agg\":\"season_total\"}. NULL if no config needed.")
)
OPTIONS (
  description = "Registry of resolution methods. Maps claim predicates to Python adapter callables and their upstream data sources. Not partitioned — small reference table."
);

-- ============================================================
-- 3. claim — structured, normalized testable claims
-- ============================================================
CREATE TABLE IF NOT EXISTS `{project_id}.silver_v2_claims.claim`
(
  claim_id                STRING    NOT NULL  OPTIONS(description="UUIDv7 for this claim"),
  utterance_id            STRING    NOT NULL  OPTIONS(description="FK to silver_v2_claims.raw_utterance.utterance_id this claim was derived from"),
  speaker_entity_id       STRING    NOT NULL  OPTIONS(description="FK to silver_v2_core.entity.entity_id of the speaker. Denormalized for query convenience."),
  domain                  STRING    NOT NULL  OPTIONS(description="Primary domain matching domain_taxonomy.domain"),
  claim_subject_type      STRING    NOT NULL  OPTIONS(description="entity|event|aggregate|metric|category — what kind of thing the claim is about"),
  subject_entity_ids      ARRAY<STRING>       OPTIONS(description="Entity UUIDs that are the subject of this claim. Empty for metric/aggregate claims."),
  subject_metric          STRING              OPTIONS(description="Metric name when claim_subject_type=metric, e.g. us_cpi_yoy, nfl_passing_yards_season"),
  predicate               STRING    NOT NULL  OPTIONS(description="Normalized predicate verb, e.g. will_win|will_be_below|will_retire|will_not_run|will_be_drafted_before|will_exceed"),
  predicate_args          JSON      NOT NULL  OPTIONS(description="Structured predicate arguments, e.g. {\"threshold\":3.0,\"comparator\":\"lt\",\"by\":\"2025-12-31\",\"unit\":\"percent\"}"),
  resolution_window_start TIMESTAMP NOT NULL  OPTIONS(description="Start of the window in which the claim must resolve"),
  resolution_window_end   TIMESTAMP NOT NULL  OPTIONS(description="End of the window in which the claim must resolve. After this, unresolved claims become unresolvable."),
  resolution_method_id    STRING    NOT NULL  OPTIONS(description="FK to silver_v2_claims.resolution_method.resolution_method_id"),
  asserted_at             TIMESTAMP NOT NULL  OPTIONS(description="When the speaker made the original assertion"),
  ledger_locked_at        TIMESTAMP NOT NULL  OPTIONS(description="When this claim was locked into the ledger. After this point the claim record is immutable."),
  prior_claim_id          STRING              OPTIONS(description="FK to claim.claim_id of the predecessor in a claim chain (e.g. revised prediction). NULL for first in chain."),
  prev_hash               STRING    NOT NULL  OPTIONS(description="Hash of the prior claim record in the chain. Empty string for chain root."),
  this_hash               STRING    NOT NULL  OPTIONS(description="SHA-256 of this claim's canonical payload. Ensures tamper-evidence."),
  created_at              TIMESTAMP NOT NULL  OPTIONS(description="UTC wall-clock insertion time")
)
PARTITION BY DATE(asserted_at)
CLUSTER BY speaker_entity_id, domain, predicate
OPTIONS (
  description = "Normalized testable claims derived from raw_utterance. Cryptographically chained via prev_hash/this_hash. Only utterances with qualifying speech_act_type and testability_score are promoted here."
);

-- ============================================================
-- 4. resolution — chained, immutable resolution outcomes
-- ============================================================
CREATE TABLE IF NOT EXISTS `{project_id}.silver_v2_claims.resolution`
(
  resolution_id           STRING    NOT NULL  OPTIONS(description="UUIDv7 for this resolution record"),
  claim_id                STRING    NOT NULL  OPTIONS(description="FK to silver_v2_claims.claim.claim_id being resolved"),
  resolved_at             TIMESTAMP NOT NULL  OPTIONS(description="When this resolution was computed"),
  outcome                 STRING    NOT NULL  OPTIONS(description="true|false|partial|unresolvable|vacuous|pending — the resolution verdict"),
  outcome_confidence      FLOAT64   NOT NULL  OPTIONS(description="0.0–1.0 confidence in the outcome verdict"),
  evidence                JSON      NOT NULL  OPTIONS(description="Structured evidence that supports this outcome, e.g. {\"source\":\"sportradar.nfl\",\"stat\":\"wins\",\"value\":14}"),
  resolution_method_id    STRING    NOT NULL  OPTIONS(description="FK to silver_v2_claims.resolution_method.resolution_method_id used for this resolution"),
  prev_hash               STRING    NOT NULL  OPTIONS(description="Hash of the prior resolution in the chain for this claim. Empty string for first resolution."),
  this_hash               STRING    NOT NULL  OPTIONS(description="SHA-256 of this resolution's canonical payload. Tamper-evident append-only log."),
  notes                   STRING              OPTIONS(description="Human-readable notes explaining the resolution decision or edge cases")
)
PARTITION BY DATE(resolved_at)
CLUSTER BY claim_id
OPTIONS (
  description = "Append-only resolution outcomes for claims. Cryptographically chained (prev_hash/this_hash) for tamper-evidence. Multiple resolutions per claim are allowed when outcome changes (e.g. partial -> true)."
);
