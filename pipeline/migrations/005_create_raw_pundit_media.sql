-- Migration: 005_create_raw_pundit_media
-- Issue: #78 — Data Ingestion (Media Pipes)
-- Description: Bronze landing table for raw pundit media content.
-- All scraped/fetched content lands here before NLP extraction (#79).

CREATE TABLE IF NOT EXISTS `{project_id}.nfl_dead_money.raw_pundit_media`
(
  -- Identity & dedup
  content_hash          STRING    NOT NULL OPTIONS(description="SHA-256 of source_url + title — used for deduplication"),
  source_id             STRING    NOT NULL OPTIONS(description="Matches media_sources.yaml source id (e.g. espn_nfl, pft_nbc)"),

  -- Content
  title                 STRING    OPTIONS(description="Article/video title"),
  raw_text              STRING    OPTIONS(description="Full article text, transcript, or RSS summary"),
  source_url            STRING    NOT NULL OPTIONS(description="Canonical URL of the source content"),

  -- Attribution
  author                STRING    OPTIONS(description="Author name as reported by the source"),
  matched_pundit_id     STRING    OPTIONS(description="Pundit ID from media_sources.yaml if author was matched"),
  matched_pundit_name   STRING    OPTIONS(description="Display name of matched pundit"),

  -- Temporal
  published_at          TIMESTAMP OPTIONS(description="When the content was originally published"),
  ingested_at           TIMESTAMP NOT NULL OPTIONS(description="When this record was fetched by the ingestor"),

  -- Metadata
  content_type          STRING    OPTIONS(description="article|video|podcast|tweet"),
  fetch_source_type     STRING    OPTIONS(description="rss|youtube_rss|web_scrape"),
  raw_metadata          STRING    OPTIONS(description="JSON blob of extra metadata from the source")
)
PARTITION BY DATE(ingested_at)
CLUSTER BY source_id, matched_pundit_id
OPTIONS (
  description = "Bronze layer: raw media content from pundit sources. Deduped by content_hash."
);
