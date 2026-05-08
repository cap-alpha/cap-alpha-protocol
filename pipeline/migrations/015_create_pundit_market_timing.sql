-- Migration: 015_create_pundit_market_timing
-- Issue: #811 — Market Correlation Phase 1: publication lead-time analysis
-- Description: Stores per-pundit × entity_class × claim_type median lead hours,
--              measuring how far in advance claims arrive relative to resolution.
--              Partitioned by computed_at date for incremental refreshes.
--
-- Lead time proxy: TIMESTAMP_DIFF(resolution_date, ingestion_timestamp, HOUR)
-- Populated via daily MERGE from gold_layer.prediction_resolutions
-- joined to gold_layer.prediction_ledger.

CREATE TABLE IF NOT EXISTS `{project_id}.gold_layer.pundit_market_timing`
(
  -- Grouping dimensions
  pundit_id             STRING    NOT NULL OPTIONS(description="Stable pundit slug, e.g. 'adam_schefter'. FK to pundit_registry.pundit_id"),
  entity_class          STRING    NOT NULL OPTIONS(description="Entity class of the claim: player|team|game|contract|draft_pick|other"),
  claim_type            STRING    NOT NULL OPTIONS(description="Claim category, e.g. trade|injury|draft_pick|game_outcome|player_performance|contract"),
  sport                 STRING    NOT NULL OPTIONS(description="Sport context: NFL|MLB|NBA|NHL|NCAAF|NCAAB"),

  -- Lead-time metric
  median_lead_hours     FLOAT64   OPTIONS(description="Median hours between ingestion_timestamp and resolution_date across all resolved (non-VOID) claims in this group"),
  sample_size           INT64     OPTIONS(description="Number of non-VOID resolved predictions used to compute the median"),

  -- Metadata
  computed_at           TIMESTAMP NOT NULL OPTIONS(description="UTC timestamp when this aggregate row was computed")
)
PARTITION BY DATE(computed_at)
CLUSTER BY pundit_id, sport, claim_type
OPTIONS (
  description = "Per-pundit publication lead-time aggregates (Phase 1 market correlation). Median hours between ingestion and resolution, grouped by pundit x entity_class x claim_type. Refreshed daily via MERGE."
);
