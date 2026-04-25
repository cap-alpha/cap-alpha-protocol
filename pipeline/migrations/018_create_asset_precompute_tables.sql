-- Migration: 018_create_asset_precompute_tables
-- Issue: #88 — SP24-3 Asset Pre-computation
-- Description: Gold-layer tables that store pre-aggregated statistics computed
--   once per daily pipeline run, eliminating repeated heavy aggregations in
--   the web server action layer (getTeamCapSummary) and frontend (buildLeaderboard).
--
-- These tables are WRITE_TRUNCATE (CREATE OR REPLACE TABLE) — no merge needed.
-- The pipeline asset_precompute stage rebuilds them atomically on each run.

-- gold_layer.team_cap_summary
-- One row per NFL team; pre-aggregates totals from fact_player_efficiency.
-- Replaces the JavaScript reduce() loop in web/app/actions.ts::getTeamCapSummary().
CREATE TABLE IF NOT EXISTS `{project_id}.gold_layer.team_cap_summary` (
    team                STRING    NOT NULL,
    player_count        INT64     NOT NULL,
    total_cap           FLOAT64   NOT NULL,
    risk_cap            FLOAT64   NOT NULL,   -- cap tied to players with risk_score > 0.7
    avg_age             FLOAT64,
    avg_risk_score      FLOAT64,
    total_dead_cap      FLOAT64,
    total_surplus_value FLOAT64,
    computed_at         TIMESTAMP NOT NULL
);

-- gold_layer.player_risk_tiers
-- One row per player (most-recent contract year), enriched with risk_tier label.
-- Pre-computes the ROW_NUMBER() de-dup + CASE risk bucket done at request time.
-- Replaces filter calls in web/app/dashboard/fan/page.tsx and actions.ts.
CREATE TABLE IF NOT EXISTS `{project_id}.gold_layer.player_risk_tiers` (
    player_name             STRING    NOT NULL,
    team                    STRING    NOT NULL,
    position                STRING,
    year                    INT64,
    age                     INT64,
    games_played            INT64,
    cap_hit_millions        FLOAT64   NOT NULL,
    dead_cap_millions       FLOAT64,
    risk_score              FLOAT64,
    fair_market_value       FLOAT64,
    edce_risk               FLOAT64,
    risk_tier               STRING    NOT NULL,  -- SAFE | MODERATE | HIGH
    computed_at             TIMESTAMP NOT NULL
);
