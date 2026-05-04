-- Migration 015: silver_v2_core — General-Purpose Truth Ledger (Phase B-0)
-- Issue: #555 — Pivot to general-purpose truth ledger data model
-- Description: Core entity resolution and attribute-event tables for the
--              domain-agnostic silver_v2 layer. These tables support sports,
--              politics, finance, tech, and any future domain without schema changes.
--
-- Design decisions:
--   - UUIDv7 primary keys (own IDs, never third-party slugs)
--   - external_ids JSON for PFR/Wikidata/Sportradar slug mapping
--   - entity_attribute_event: dual-confidence (extraction_confidence + corroboration_count)
--   - domain_taxonomy drives runtime-configurable validation + resolution adapters
--   - Testability threshold is a runtime param, not a schema constraint
--
-- Usage:
--   export PROJECT_ID=cap-alpha-protocol
--   envsubst < pipeline/migrations/015_create_silver_v2_core.sql | \
--     bq query --use_legacy_sql=false --project_id=$PROJECT_ID

CREATE SCHEMA IF NOT EXISTS `{project_id}.silver_v2_core`;

-- ============================================================
-- 1. entity — stable root, never mutates primary key
-- ============================================================
CREATE TABLE IF NOT EXISTS `{project_id}.silver_v2_core.entity`
(
  entity_id           STRING    NOT NULL  OPTIONS(description="UUIDv7 we generate. Never equals a PFR slug or any third-party key. Immutable."),
  entity_kind         STRING    NOT NULL  OPTIONS(description="person|team_brand|franchise|org|product|event|office"),
  primary_domain      STRING    NOT NULL  OPTIONS(description="Top-level domain this entity primarily belongs to: sports.nfl, politics.us, finance.macro, tech, etc."),
  birth_or_founded    DATE                OPTIONS(description="Date of birth for persons; founding date for orgs/franchises. NULL when unknown."),
  death_or_dissolved  DATE                OPTIONS(description="Date of death or dissolution. NULL when still active."),
  external_ids        JSON                OPTIONS(description="JSON map of third-party identifiers, e.g. {\"pfr_slug\":\"BradTo00\",\"wikidata\":\"Q9685\",\"sportradar\":\"abc123\"}. Append-only field; never use these as join keys."),
  created_at          TIMESTAMP NOT NULL  OPTIONS(description="UTC wall-clock time this entity was first inserted into the ledger"),
  notes               STRING              OPTIONS(description="Free-text notes for edge cases; do not store structured data here")
)
PARTITION BY DATE_TRUNC(birth_or_founded, YEAR)
CLUSTER BY entity_kind, primary_domain
OPTIONS (
  description = "Root entity table for the general-purpose truth ledger. One row per real-world entity. UUIDv7 primary keys; external slugs stored in external_ids JSON. Partitioned by birth/founding year."
);

-- ============================================================
-- 2. entity_alias — resolved names and handles across time
-- ============================================================
CREATE TABLE IF NOT EXISTS `{project_id}.silver_v2_core.entity_alias`
(
  alias_id            STRING    NOT NULL  OPTIONS(description="UUIDv7 for this alias record"),
  entity_id           STRING    NOT NULL  OPTIONS(description="FK to silver_v2_core.entity.entity_id"),
  alias_text          STRING    NOT NULL  OPTIONS(description="The alias string exactly as used in source material"),
  alias_kind          STRING    NOT NULL  OPTIONS(description="legal_name|preferred_name|nickname|handle|ticker|jersey_number|former_legal_name|misspelling"),
  valid_from          TIMESTAMP NOT NULL  OPTIONS(description="When this alias became valid. Use earliest known usage if exact date unknown."),
  valid_to            TIMESTAMP           OPTIONS(description="When this alias stopped being valid. NULL = still current."),
  is_legal            BOOL      NOT NULL  OPTIONS(description="TRUE if this alias appears on legal/official documents"),
  source_event_id     STRING              OPTIONS(description="FK to entity_attribute_event.event_id that sourced this alias, if applicable"),
  confidence          FLOAT64   NOT NULL  OPTIONS(description="0.0–1.0 LLM extraction confidence that this alias text maps to entity_id"),
  language            STRING              OPTIONS(description="BCP-47 language tag for the alias, e.g. en, es, zh-Hans")
)
CLUSTER BY entity_id, alias_text
OPTIONS (
  description = "All names, handles, tickers, and nicknames for each entity, with validity windows. Enables backward-linking of raw alias text found in claims."
);

-- ============================================================
-- 3. entity_attribute_event — immutable attribute change log
-- ============================================================
CREATE TABLE IF NOT EXISTS `{project_id}.silver_v2_core.entity_attribute_event`
(
  event_id                STRING    NOT NULL  OPTIONS(description="UUIDv7 for this attribute event"),
  entity_id               STRING    NOT NULL  OPTIONS(description="FK to silver_v2_core.entity.entity_id"),
  domain                  STRING    NOT NULL  OPTIONS(description="Attribute namespace matching domain_taxonomy.domain, e.g. sports.nfl"),
  attr                    STRING    NOT NULL  OPTIONS(description="Attribute name: legal_name|status|employment|position|party_affiliation|citizenship|number|salary|contract_years|..."),
  value                   STRING    NOT NULL  OPTIONS(description="Canonical scalar value as a string"),
  value_json              JSON                OPTIONS(description="Richer structured payload when a scalar is insufficient (e.g. contract terms object)"),
  valid_from              TIMESTAMP NOT NULL  OPTIONS(description="When this attribute value became effective"),
  valid_to                TIMESTAMP           OPTIONS(description="When this attribute value was superseded. NULL = still current."),
  evidence_type           STRING    NOT NULL  OPTIONS(description="public_announce|legal_filing|first_observed_use|inferred"),
  source_claim_id         STRING              OPTIONS(description="FK to silver_v2_claims.claim.claim_id that evidenced this attribute, if applicable"),
  source_doc_id           STRING              OPTIONS(description="FK to raw source document that evidenced this attribute"),
  extraction_confidence   FLOAT64   NOT NULL  OPTIONS(description="0.0–1.0 LLM certainty that this attribute value is correct"),
  corroboration_count     INT64     NOT NULL  OPTIONS(description="Number of independent sources corroborating this attribute value. Incremented at write-time."),
  is_concurrent_ok        BOOL      NOT NULL  OPTIONS(description="TRUE for attributes that can have multiple current values simultaneously, e.g. employment (dual contracts), citizenship"),
  superseded_by           STRING              OPTIONS(description="event_id of the correction event that replaced this record. NULL = not corrected."),
  created_at              TIMESTAMP NOT NULL  OPTIONS(description="UTC wall-clock insertion time")
)
PARTITION BY DATE(valid_from)
CLUSTER BY entity_id, domain, attr
OPTIONS (
  description = "Immutable log of entity attribute changes. Dual-confidence model: extraction_confidence (LLM certainty) + corroboration_count (independent sources). Supports concurrent multi-valued attrs via is_concurrent_ok flag."
);

-- ============================================================
-- 4. transition_event — discrete life/career events
-- ============================================================
CREATE TABLE IF NOT EXISTS `{project_id}.silver_v2_core.transition_event`
(
  event_id                STRING    NOT NULL  OPTIONS(description="UUIDv7 for this transition event"),
  entity_id               STRING    NOT NULL  OPTIONS(description="FK to silver_v2_core.entity.entity_id"),
  domain                  STRING    NOT NULL  OPTIONS(description="Domain context matching domain_taxonomy.domain, e.g. sports.nfl"),
  type                    STRING    NOT NULL  OPTIONS(description="NameChange|GenderTransition|SportChange|LeagueChange|PositionChange|TeamChange|Draft|SignContract|FirstAppearance|Retire|Unretire|Suspend|Reinstate|Incarcerate|Release|MilitaryEnlist|MilitaryDischarge|PartyChange|CaucusChange|Naturalize|FieldChange|Restructure|Acquire|IPO|Rename|Death|Restart"),
  from_value              STRING              OPTIONS(description="State before the transition, if applicable (e.g. previous team abbreviation)"),
  to_value                STRING              OPTIONS(description="State after the transition, if applicable (e.g. new team abbreviation)"),
  occurred_at             TIMESTAMP NOT NULL  OPTIONS(description="When the transition occurred"),
  occurred_at_precision   STRING    NOT NULL  OPTIONS(description="Temporal precision of occurred_at: second|day|month|year"),
  payload                 JSON                OPTIONS(description="Domain-specific structured payload (e.g. draft round/pick, contract ACV, suspension length in games)"),
  source_claim_id         STRING              OPTIONS(description="FK to silver_v2_claims.claim.claim_id that evidenced this event"),
  source_doc_id           STRING              OPTIONS(description="FK to raw source document"),
  confidence              FLOAT64   NOT NULL  OPTIONS(description="0.0–1.0 confidence this transition event is correctly attributed to this entity"),
  created_at              TIMESTAMP NOT NULL  OPTIONS(description="UTC wall-clock insertion time")
)
PARTITION BY DATE(occurred_at)
CLUSTER BY entity_id, type
OPTIONS (
  description = "Discrete transition events in an entity's lifecycle. Covers career, status, legal, organizational, and other domain-relevant milestones. Paired with entity_attribute_event for attribute-level state tracking."
);

-- ============================================================
-- 5. domain_taxonomy — runtime configuration per domain
-- ============================================================
CREATE TABLE IF NOT EXISTS `{project_id}.silver_v2_core.domain_taxonomy`
(
  domain                STRING    NOT NULL  OPTIONS(description="Hierarchical domain identifier, e.g. sports.nfl. Acts as primary key."),
  parent_domain         STRING              OPTIONS(description="Parent domain, e.g. sports is parent of sports.nfl. NULL for root domains."),
  display_name          STRING    NOT NULL  OPTIONS(description="Human-readable domain name, e.g. NFL Football"),
  attribute_specs       JSON      NOT NULL  OPTIONS(description="JSON array of valid attribute definitions: [{\"attr\":\"position\",\"value_type\":\"string\",\"is_concurrent_ok\":false},...]"),
  resolution_adapter    STRING    NOT NULL  OPTIONS(description="Python module path for the domain resolution adapter, e.g. pipeline.resolvers.nfl.base:NflResolver"),
  created_at            TIMESTAMP NOT NULL  OPTIONS(description="UTC wall-clock time this domain was registered")
)
OPTIONS (
  description = "Runtime-configurable domain taxonomy. Drives attribute validation, entity resolution adapters, and testability thresholds without schema changes. Not partitioned — expected to be small (< 100 rows)."
);

-- ============================================================
-- Seed domain_taxonomy with initial domains
-- ============================================================
INSERT INTO `{project_id}.silver_v2_core.domain_taxonomy`
  (domain, parent_domain, display_name, attribute_specs, resolution_adapter, created_at)
VALUES
  (
    'sports',
    NULL,
    'Sports',
    JSON '[{"attr":"status","value_type":"string","is_concurrent_ok":false},{"attr":"employment","value_type":"string","is_concurrent_ok":true}]',
    'pipeline.resolvers.sports.base:SportsResolver',
    CURRENT_TIMESTAMP()
  ),
  (
    'sports.nfl',
    'sports',
    'NFL Football',
    JSON '[{"attr":"position","value_type":"string","is_concurrent_ok":false},{"attr":"team","value_type":"string","is_concurrent_ok":false},{"attr":"jersey_number","value_type":"string","is_concurrent_ok":false},{"attr":"status","value_type":"string","is_concurrent_ok":false},{"attr":"employment","value_type":"string","is_concurrent_ok":true},{"attr":"contract_years","value_type":"int","is_concurrent_ok":false},{"attr":"salary_aav","value_type":"float","is_concurrent_ok":false}]',
    'pipeline.resolvers.nfl.base:NflResolver',
    CURRENT_TIMESTAMP()
  ),
  (
    'politics',
    NULL,
    'Politics',
    JSON '[{"attr":"party_affiliation","value_type":"string","is_concurrent_ok":false},{"attr":"status","value_type":"string","is_concurrent_ok":false}]',
    'pipeline.resolvers.politics.base:PoliticsResolver',
    CURRENT_TIMESTAMP()
  ),
  (
    'politics.us',
    'politics',
    'U.S. Politics',
    JSON '[{"attr":"party_affiliation","value_type":"string","is_concurrent_ok":false},{"attr":"caucus","value_type":"string","is_concurrent_ok":false},{"attr":"office","value_type":"string","is_concurrent_ok":false},{"attr":"state","value_type":"string","is_concurrent_ok":false},{"attr":"citizenship","value_type":"string","is_concurrent_ok":true}]',
    'pipeline.resolvers.politics.us:UsPoliticsResolver',
    CURRENT_TIMESTAMP()
  ),
  (
    'politics.us.federal',
    'politics.us',
    'U.S. Federal Government',
    JSON '[{"attr":"party_affiliation","value_type":"string","is_concurrent_ok":false},{"attr":"caucus","value_type":"string","is_concurrent_ok":false},{"attr":"chamber","value_type":"string","is_concurrent_ok":false},{"attr":"office","value_type":"string","is_concurrent_ok":false},{"attr":"committee_membership","value_type":"string","is_concurrent_ok":true}]',
    'pipeline.resolvers.politics.us.federal:UsFederalResolver',
    CURRENT_TIMESTAMP()
  ),
  (
    'finance',
    NULL,
    'Finance',
    JSON '[{"attr":"status","value_type":"string","is_concurrent_ok":false},{"attr":"sector","value_type":"string","is_concurrent_ok":false}]',
    'pipeline.resolvers.finance.base:FinanceResolver',
    CURRENT_TIMESTAMP()
  ),
  (
    'finance.macro',
    'finance',
    'Macroeconomics',
    JSON '[{"attr":"indicator","value_type":"string","is_concurrent_ok":false},{"attr":"data_source","value_type":"string","is_concurrent_ok":true},{"attr":"unit","value_type":"string","is_concurrent_ok":false}]',
    'pipeline.resolvers.finance.macro:MacroResolver',
    CURRENT_TIMESTAMP()
  ),
  (
    'tech',
    NULL,
    'Technology',
    JSON '[{"attr":"status","value_type":"string","is_concurrent_ok":false},{"attr":"ticker","value_type":"string","is_concurrent_ok":false},{"attr":"sector","value_type":"string","is_concurrent_ok":false},{"attr":"employment","value_type":"string","is_concurrent_ok":true}]',
    'pipeline.resolvers.tech.base:TechResolver',
    CURRENT_TIMESTAMP()
  );

-- ============================================================
-- Snapshot views
-- ============================================================

-- entity_current: latest attribute values per (entity_id, domain, attr)
CREATE OR REPLACE VIEW `{project_id}.silver_v2_core.entity_current` AS
SELECT
  eae.entity_id,
  e.entity_kind,
  e.primary_domain,
  eae.domain,
  eae.attr,
  eae.value,
  eae.value_json,
  eae.valid_from,
  eae.evidence_type,
  eae.extraction_confidence,
  eae.corroboration_count,
  eae.is_concurrent_ok
FROM `{project_id}.silver_v2_core.entity_attribute_event` AS eae
INNER JOIN `{project_id}.silver_v2_core.entity` AS e
  ON e.entity_id = eae.entity_id
WHERE
  eae.valid_to IS NULL
  AND eae.superseded_by IS NULL;

-- entity_timeline: full sorted history per entity
CREATE OR REPLACE VIEW `{project_id}.silver_v2_core.entity_timeline` AS
SELECT
  te.entity_id,
  e.entity_kind,
  e.primary_domain,
  te.domain,
  te.type          AS event_type,
  te.from_value,
  te.to_value,
  te.occurred_at,
  te.occurred_at_precision,
  te.confidence,
  te.payload,
  'transition'     AS record_kind
FROM `{project_id}.silver_v2_core.transition_event` AS te
INNER JOIN `{project_id}.silver_v2_core.entity` AS e
  ON e.entity_id = te.entity_id

UNION ALL

SELECT
  eae.entity_id,
  e.entity_kind,
  e.primary_domain,
  eae.domain,
  CONCAT('attr:', eae.attr) AS event_type,
  NULL                      AS from_value,
  eae.value                 AS to_value,
  eae.valid_from            AS occurred_at,
  'second'                  AS occurred_at_precision,
  eae.extraction_confidence AS confidence,
  eae.value_json            AS payload,
  'attribute'               AS record_kind
FROM `{project_id}.silver_v2_core.entity_attribute_event` AS eae
INNER JOIN `{project_id}.silver_v2_core.entity` AS e
  ON e.entity_id = eae.entity_id

ORDER BY entity_id, occurred_at;
