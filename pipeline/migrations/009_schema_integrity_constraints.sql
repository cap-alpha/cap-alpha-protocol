-- Migration 009: Schema Integrity — NOT NULL Constraints (Issue #106)
--
-- Goal: Enforce strict NOT NULL on all core identity columns across Players,
-- Teams, and Contracts tables to prevent NULL data from propagating into
-- the Gold layer or user-facing APIs.
--
-- BigQuery note: ALTER TABLE ... ALTER COLUMN ... SET NOT NULL only succeeds
-- if the column has ZERO existing NULL rows. Run the validation queries
-- (see below) before applying each constraint block.
--
-- Usage:
--   export PROJECT_ID=cap-alpha-protocol
--   envsubst < pipeline/migrations/009_schema_integrity_constraints.sql | \
--     bq query --use_legacy_sql=false --project_id=$PROJECT_ID

-- ============================================================
-- PRE-FLIGHT: Validate no NULLs exist before adding constraints
-- ============================================================

-- 1. bronze_sportsdataio_players — identity columns
SELECT
  'bronze_sportsdataio_players' AS table_name,
  COUNTIF(PlayerID IS NULL)   AS null_player_id,
  COUNTIF(Name IS NULL)       AS null_name,
  COUNTIF(Team IS NULL)       AS null_team,
  COUNTIF(Status IS NULL)     AS null_status
FROM `${PROJECT_ID}.nfl_dead_money.bronze_sportsdataio_players`;

-- 2. fact_player_efficiency — analytical layer
SELECT
  'fact_player_efficiency' AS table_name,
  COUNTIF(player_name IS NULL)        AS null_player_name,
  COUNTIF(team IS NULL)               AS null_team,
  COUNTIF(position IS NULL)           AS null_position,
  COUNTIF(cap_hit_millions IS NULL)   AS null_cap_hit
FROM `${PROJECT_ID}.nfl_dead_money.fact_player_efficiency`;

-- 3. silver_spotrac_contracts — contracts
SELECT
  'silver_spotrac_contracts' AS table_name,
  COUNTIF(player_name IS NULL)       AS null_player_name,
  COUNTIF(year IS NULL)              AS null_year,
  COUNTIF(cap_hit_millions IS NULL)  AS null_cap_hit
FROM `${PROJECT_ID}.nfl_dead_money.silver_spotrac_contracts`;


-- ============================================================
-- bronze_sportsdataio_players — player identity
-- ============================================================
-- Run only after validation above shows 0 NULLs.

ALTER TABLE `${PROJECT_ID}.nfl_dead_money.bronze_sportsdataio_players`
  ALTER COLUMN PlayerID SET NOT NULL;

ALTER TABLE `${PROJECT_ID}.nfl_dead_money.bronze_sportsdataio_players`
  ALTER COLUMN Name SET NOT NULL;

ALTER TABLE `${PROJECT_ID}.nfl_dead_money.bronze_sportsdataio_players`
  ALTER COLUMN Team SET NOT NULL;


-- ============================================================
-- fact_player_efficiency — analytical layer identity
-- ============================================================
-- Run only after validation shows 0 NULLs in these columns.

ALTER TABLE `${PROJECT_ID}.nfl_dead_money.fact_player_efficiency`
  ALTER COLUMN player_name SET NOT NULL;

ALTER TABLE `${PROJECT_ID}.nfl_dead_money.fact_player_efficiency`
  ALTER COLUMN team SET NOT NULL;

ALTER TABLE `${PROJECT_ID}.nfl_dead_money.fact_player_efficiency`
  ALTER COLUMN position SET NOT NULL;


-- ============================================================
-- silver_spotrac_contracts — contracts identity
-- ============================================================
-- Run only after validation shows 0 NULLs.

ALTER TABLE `${PROJECT_ID}.nfl_dead_money.silver_spotrac_contracts`
  ALTER COLUMN player_name SET NOT NULL;

ALTER TABLE `${PROJECT_ID}.nfl_dead_money.silver_spotrac_contracts`
  ALTER COLUMN year SET NOT NULL;


-- ============================================================
-- raw_pundit_media — content type completeness
-- ============================================================
-- content_type and fetch_source_type should always be set by the ingestor.

ALTER TABLE `${PROJECT_ID}.nfl_dead_money.raw_pundit_media`
  ALTER COLUMN content_type SET NOT NULL;

ALTER TABLE `${PROJECT_ID}.nfl_dead_money.raw_pundit_media`
  ALTER COLUMN fetch_source_type SET NOT NULL;


-- ============================================================
-- POST-MIGRATION: Verify constraints landed
-- ============================================================
-- Check INFORMATION_SCHEMA to confirm REQUIRED mode:

SELECT
  table_name,
  column_name,
  is_nullable
FROM `${PROJECT_ID}.nfl_dead_money.INFORMATION_SCHEMA.COLUMNS`
WHERE table_name IN (
    'bronze_sportsdataio_players',
    'fact_player_efficiency',
    'silver_spotrac_contracts',
    'raw_pundit_media'
  )
  AND column_name IN (
    'PlayerID', 'Name', 'Team',
    'player_name', 'team', 'position',
    'year', 'cap_hit_millions',
    'content_type', 'fetch_source_type'
  )
ORDER BY table_name, column_name;
