-- Migration: 016_create_gold_build_watermark
-- Issue: #66 — SP18.5-3 Incremental Gold/Fact aggregation
-- Description: Tracks the last successful Gold layer build timestamp per mart.
-- Allows incremental re-computation of only changed (player_name, year, team) rows
-- instead of a full CREATE OR REPLACE on every pipeline run.

CREATE TABLE IF NOT EXISTS `{project_id}.nfl_dead_money.gold_build_watermark`
(
  mart_name         STRING    NOT NULL OPTIONS(description="Target Gold/fact table name (e.g. fact_player_efficiency)"),
  last_built_at     TIMESTAMP NOT NULL OPTIONS(description="UTC timestamp of the last successful full or incremental build"),
  build_type        STRING    NOT NULL OPTIONS(description="full | incremental"),
  rows_affected     INT64              OPTIONS(description="Number of rows written in the last build"),
  system_ingest_ts  TIMESTAMP NOT NULL OPTIONS(description="When this row was written")
)
CLUSTER BY mart_name
OPTIONS (
  description = "Gold layer build watermarks. One row per mart (UPSERT on mart_name). Used by incremental refresh to scope delta queries."
);
