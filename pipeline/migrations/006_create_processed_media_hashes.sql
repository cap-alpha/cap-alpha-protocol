-- Migration: 006_create_processed_media_hashes
-- Issue: #79 — NLP Assertion Extraction
-- Description: Tracks which raw_pundit_media rows have been processed by the
-- assertion extractor, preventing duplicate extraction runs.

CREATE TABLE IF NOT EXISTS `{project_id}.nfl_dead_money.processed_media_hashes`
(
  content_hash    STRING    NOT NULL OPTIONS(description="FK to raw_pundit_media.content_hash"),
  processed_at    TIMESTAMP NOT NULL OPTIONS(description="When extraction was completed")
)
PARTITION BY DATE(processed_at)
OPTIONS (
  description = "Tracks which media items have been processed by the assertion extractor."
);
