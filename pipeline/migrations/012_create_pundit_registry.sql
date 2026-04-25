-- Migration 012: Adaptive Pundit Registry (Issue #119)
--
-- Creates three tables:
--   nfl_dead_money.pundit_registry   — tracked pundits with adaptive cadence
--   nfl_dead_money.source_registry   — ingest source definitions (replaces YAML)
--   nfl_dead_money.registry_audit_log — append-only change ledger
--
-- Usage:
--   export PROJECT_ID=cap-alpha-protocol
--   envsubst < pipeline/migrations/012_create_pundit_registry.sql | \
--     bq query --use_legacy_sql=false --project_id=$PROJECT_ID

-- ============================================================
-- 1. Pundit Registry
-- ============================================================
CREATE TABLE IF NOT EXISTS `{project_id}.nfl_dead_money.pundit_registry`
(
  pundit_id           STRING    NOT NULL OPTIONS(description="Stable snake_case identifier, e.g. adam_schefter"),
  pundit_name         STRING    NOT NULL OPTIONS(description="Display name, e.g. Adam Schefter"),
  sport               STRING    NOT NULL OPTIONS(description="Sport context: NFL|MLB|NBA|NHL|NCAAF|NCAAB"),
  source_ids          ARRAY<STRING>       OPTIONS(description="Source IDs this pundit appears in"),
  match_authors       ARRAY<STRING>       OPTIONS(description="Author name patterns used for matching in ingested content"),
  enabled             BOOL      NOT NULL  OPTIONS(description="Whether this pundit is actively tracked and extracted"),
  is_source_default   BOOL                OPTIONS(description="True if this is a source-level default attribution, not per-author"),
  polling_cadence     STRING    NOT NULL  OPTIONS(description="Ingest frequency: daily|twice_weekly|weekly|biweekly|monthly"),
  last_seen_at        TIMESTAMP           OPTIONS(description="Most recent content ingested for this pundit"),
  posts_per_month     FLOAT64             OPTIONS(description="Rolling 30-day posting frequency, used to compute cadence"),
  created_at          TIMESTAMP NOT NULL  OPTIONS(description="When this pundit was added to the registry"),
  updated_at          TIMESTAMP NOT NULL  OPTIONS(description="When this row was last modified")
)
CLUSTER BY sport, enabled
OPTIONS (
  description = "Adaptive pundit registry. Source of truth for tracked pundits; replaces static media_sources.yaml pundit definitions."
);

-- ============================================================
-- 2. Source Registry
-- ============================================================
CREATE TABLE IF NOT EXISTS `{project_id}.nfl_dead_money.source_registry`
(
  source_id           STRING    NOT NULL  OPTIONS(description="Stable identifier, e.g. espn_nfl"),
  source_name         STRING    NOT NULL  OPTIONS(description="Human-readable name, e.g. ESPN NFL"),
  source_type         STRING    NOT NULL  OPTIONS(description="rss|youtube_transcript|youtube_rss"),
  url                 STRING    NOT NULL  OPTIONS(description="Feed URL or YouTube channel feed URL"),
  sport               STRING    NOT NULL  OPTIONS(description="Sport context: NFL|MLB|NBA|NHL|NCAAF|NCAAB"),
  enabled             BOOL      NOT NULL  OPTIONS(description="Whether this source is actively polled"),
  scrape_full_text    BOOL                OPTIONS(description="If true, fetch full article HTML beyond RSS summary"),
  keyword_filter      ARRAY<STRING>       OPTIONS(description="Skip entries that do not match any of these keywords"),
  default_pundit_id   STRING              OPTIONS(description="Pundit ID to attribute content to when author matching fails"),
  polling_cadence     STRING    NOT NULL  OPTIONS(description="How often to poll: daily|twice_weekly|weekly|biweekly|monthly"),
  last_fetched_at     TIMESTAMP           OPTIONS(description="Timestamp of most recent successful fetch"),
  last_item_count     INT64               OPTIONS(description="Number of items returned in the most recent fetch"),
  created_at          TIMESTAMP NOT NULL  OPTIONS(description="When this source was added to the registry"),
  updated_at          TIMESTAMP NOT NULL  OPTIONS(description="When this row was last modified")
)
CLUSTER BY sport, enabled
OPTIONS (
  description = "Ingest source registry. Source of truth for feed URLs and polling config; replaces static media_sources.yaml source definitions."
);

-- ============================================================
-- 3. Registry Audit Log
-- ============================================================
CREATE TABLE IF NOT EXISTS `{project_id}.nfl_dead_money.registry_audit_log`
(
  log_id              STRING    NOT NULL  OPTIONS(description="UUID for this log entry"),
  entity_type         STRING    NOT NULL  OPTIONS(description="pundit|source|candidate"),
  entity_id           STRING    NOT NULL  OPTIONS(description="pundit_id or source_id this change applies to"),
  action              STRING    NOT NULL  OPTIONS(description="create|update|enable|disable|cadence_change|candidate_discovered|candidate_promoted"),
  old_value           STRING              OPTIONS(description="JSON snapshot of the row before this change"),
  new_value           STRING              OPTIONS(description="JSON snapshot of the row after this change"),
  reason              STRING              OPTIONS(description="Human-readable description of why this change was made"),
  logged_at           TIMESTAMP NOT NULL  OPTIONS(description="When this event was recorded")
)
PARTITION BY DATE(logged_at)
CLUSTER BY entity_type, entity_id
OPTIONS (
  description = "Append-only audit log for all changes to pundit_registry and source_registry."
);
