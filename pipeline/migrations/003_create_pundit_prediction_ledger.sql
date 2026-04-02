-- Migration: 003_create_pundit_prediction_ledger
-- Issue: #111 — Cryptographic Hashing Pipeline for Prediction Integrity
-- Description: Creates the append-only BigQuery gold layer table for pundit predictions.
--
-- Append-only enforcement: BigQuery has no SQL-level row locks. Immutability is
-- enforced at the application layer (WRITE_APPEND only, never WRITE_TRUNCATE/WRITE_EMPTY)
-- and at the IAM layer (service account has bigquery.tables.updateData but NOT
-- bigquery.tables.delete or bigquery.tables.update on this table).

CREATE TABLE IF NOT EXISTS `{project_id}.gold_layer.prediction_ledger`
(
  -- Identity & integrity
  prediction_hash     STRING    NOT NULL OPTIONS(description="SHA-256 of canonical payload (ingestion_timestamp|source_url|pundit_id|raw_assertion_text)"),
  chain_hash          STRING    NOT NULL OPTIONS(description="SHA-256(prediction_hash + previous row's chain_hash). Empty string seed for first row."),

  -- Provenance
  ingestion_timestamp TIMESTAMP NOT NULL OPTIONS(description="UTC wall-clock time this record entered the ledger"),
  source_url          STRING    NOT NULL OPTIONS(description="Canonical URL of the source article, tweet, or transcript"),
  pundit_id           STRING    NOT NULL OPTIONS(description="Stable slug: e.g. 'adam_schefter', 'pat_mcafee'"),
  pundit_name         STRING    NOT NULL OPTIONS(description="Display name of the pundit"),

  -- Assertion content
  raw_assertion_text  STRING    NOT NULL OPTIONS(description="Verbatim quote or transcribed text"),
  extracted_claim     STRING    OPTIONS(description="Structured NLP summary of the easily testable prediction"),
  claim_category      STRING    OPTIONS(description="One of: player_performance|game_outcome|trade|draft_pick|injury|contract"),

  -- Targeting
  season_year         INT64     OPTIONS(description="NFL season year the prediction applies to"),
  target_player_id    STRING    OPTIONS(description="FK to silver_sportsdataio_players.player_id if claim targets a specific player"),
  target_team         STRING    OPTIONS(description="NFL team abbreviation if claim targets a specific team"),

  -- Resolution (populated by Prediction Resolution Engine, issue #112)
  resolution_status   STRING    OPTIONS(description="PENDING|CORRECT|INCORRECT|VOID") DEFAULT 'PENDING',
  resolved_at         TIMESTAMP OPTIONS(description="When the prediction was scored against real-world outcomes"),
  resolution_notes    STRING    OPTIONS(description="Human-readable explanation of the scoring decision")
)
PARTITION BY DATE(ingestion_timestamp)
CLUSTER BY pundit_id, claim_category
OPTIONS (
  description = "Append-only cryptographic ledger of pundit predictions. Partitioned by ingestion date. No UPDATE or DELETE — immutability enforced by application + IAM."
);