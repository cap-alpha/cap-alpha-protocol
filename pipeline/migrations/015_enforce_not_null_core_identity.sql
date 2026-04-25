-- Migration: 015_enforce_not_null_core_identity
-- Issue: #106 — Schema Integrity & Output Guardrails (SP29-1)
-- Description: Canonical schemas for core identity tables enforcing NOT NULL
--   (REQUIRED mode in BigQuery) on all primary key, join-key, and business-critical
--   columns.  Run once on a fresh dataset; for existing tables see the ALTER note below.
--
-- NOTE: BigQuery does not support ALTER COLUMN ... SET NOT NULL on existing tables.
-- To backfill constraints on a live table, use the recreation pattern:
--   1. Run CREATE TABLE ... AS SELECT on a new table name
--   2. Validate row counts match
--   3. Drop old table and rename new one
-- This file defines the authoritative target schema for new environments.

-- ============================================================
-- 1. silver_spotrac_contracts
--    Primary contract ledger. SCD Type 2. Immutable append.
-- ============================================================
CREATE TABLE IF NOT EXISTS `{project_id}.nfl_dead_money.silver_spotrac_contracts`
(
  -- Surrogate keys
  contract_id               STRING    NOT NULL OPTIONS(description="MD5(player_name|team|year) — dedup key for SCD merge"),
  player_id                 STRING    NOT NULL OPTIONS(description="MD5(player_name) — cross-table join key (see audit: fragile for duplicate names)"),

  -- Business identity — all REQUIRED; a contract row without these is unresolvable
  player_name               STRING    NOT NULL OPTIONS(description="Full player name as scraped from Spotrac"),
  team                      STRING    NOT NULL OPTIONS(description="NFL team abbreviation (e.g. KC, SF)"),
  year                      INT64     NOT NULL OPTIONS(description="Roster/cap year"),
  position                  STRING    NOT NULL OPTIONS(description="Position code (QB, WR, etc.)"),

  -- Financial figures — nullable (some are unavailable for minimum-salary players)
  cap_hit_millions          FLOAT64   OPTIONS(description="Total cap charge in millions"),
  dead_cap_millions         FLOAT64   OPTIONS(description="Dead money if cut/traded"),
  signing_bonus_millions    FLOAT64,
  guaranteed_money_millions FLOAT64,
  total_contract_value_millions FLOAT64,
  base_salary_millions      FLOAT64,
  prorated_bonus_millions   FLOAT64,
  roster_bonus_millions     FLOAT64,
  guaranteed_salary_millions FLOAT64,
  age                       FLOAT64   OPTIONS(description="Player age at start of season"),

  -- SCD Type 2 temporal columns
  valid_from                TIMESTAMP NOT NULL OPTIONS(description="When this record version became effective (UTC)"),
  valid_until               TIMESTAMP          OPTIONS(description="NULL = currently active version"),
  is_current                BOOL      NOT NULL OPTIONS(description="TRUE if valid_until IS NULL — partition-filter shortcut"),

  -- Provenance
  source_name               STRING    NOT NULL OPTIONS(description="Data provider (spotrac)") DEFAULT 'spotrac',
  system_ingest_ts          TIMESTAMP NOT NULL OPTIONS(description="Wall-clock time this row was written by the pipeline (UTC)")
)
PARTITION BY DATE(valid_from)
CLUSTER BY year, team, player_name
OPTIONS (
  description = "Silver layer: NFL contract data from Spotrac. SCD Type 2 ledger — append only, never update/delete."
);

-- ============================================================
-- 2. silver_player_metadata
--    Canonical player bio/identity table. SCD Type 2.
-- ============================================================
CREATE TABLE IF NOT EXISTS `{project_id}.nfl_dead_money.silver_player_metadata`
(
  -- Surrogate key
  player_id                 STRING    NOT NULL OPTIONS(description="MD5(full_name) — join key; aligns with silver_spotrac_contracts.player_id"),

  -- Identity — REQUIRED
  full_name                 STRING    NOT NULL OPTIONS(description="Full player name"),
  position                  STRING    NOT NULL OPTIONS(description="Current position code"),

  -- Bio — nullable (not always available from provider)
  birth_date                DATE               OPTIONS(description="Date of birth (DATE type, not STRING)"),
  college                   STRING,
  experience_years          INT64              OPTIONS(description="NFL seasons of experience"),
  draft_round               INT64              OPTIONS(description="Draft round; NULL for undrafted (0 = legacy, migrate to NULL)"),
  draft_pick                INT64              OPTIONS(description="Draft pick within round; NULL for undrafted"),

  -- Current state (point-in-time snapshot within the SCD row)
  team                      STRING             OPTIONS(description="Team abbreviation at valid_from; NULL if free agent"),
  status                    STRING             OPTIONS(description="Active | Inactive | IR | PUP etc."),
  photo_url                 STRING             OPTIONS(description="CDN URL for player headshot"),

  -- Vendor-native IDs (stable cross-table references)
  sportsdataio_player_id    STRING             OPTIONS(description="SportsData.io native PlayerID for stable vendor lookups"),

  -- SCD Type 2 temporal columns
  valid_from                TIMESTAMP NOT NULL OPTIONS(description="When this record version became effective (UTC)"),
  valid_until               TIMESTAMP          OPTIONS(description="NULL = currently active version"),
  is_current                BOOL      NOT NULL OPTIONS(description="TRUE if valid_until IS NULL"),

  -- Provenance
  source_name               STRING    NOT NULL OPTIONS(description="Data provider (sportsdataio)") DEFAULT 'sportsdataio',
  system_ingest_ts          TIMESTAMP NOT NULL OPTIONS(description="Wall-clock ingest timestamp (UTC)")
)
PARTITION BY DATE(valid_from)
CLUSTER BY full_name, position
OPTIONS (
  description = "Silver layer: canonical player bio/identity. SCD Type 2. Source: SportsData.io."
);

-- ============================================================
-- 3. silver_teams
--    Reference table for NFL franchise identities.
--    Rarely changes; system_ingest_ts only (no full SCD needed).
-- ============================================================
CREATE TABLE IF NOT EXISTS `{project_id}.nfl_dead_money.silver_teams`
(
  -- Primary key
  team_abbr                 STRING    NOT NULL OPTIONS(description="Three-letter abbreviation used throughout the pipeline (e.g. KC, SF, NWE)"),

  -- Identity
  team_name                 STRING    NOT NULL OPTIONS(description="Full franchise name (e.g. Kansas City Chiefs)"),
  city                      STRING    NOT NULL OPTIONS(description="City or region (e.g. Kansas City)"),
  conference                STRING    NOT NULL OPTIONS(description="AFC or NFC"),
  division                  STRING    NOT NULL OPTIONS(description="e.g. AFC West"),

  -- Metadata
  active                    BOOL      NOT NULL OPTIONS(description="FALSE for relocated/renamed franchises (e.g. Oakland Raiders)") DEFAULT TRUE,
  system_ingest_ts          TIMESTAMP NOT NULL OPTIONS(description="When this row was last written")
)
CLUSTER BY conference, division
OPTIONS (
  description = "Silver layer: NFL franchise reference table. One row per active/historical franchise abbreviation."
);
