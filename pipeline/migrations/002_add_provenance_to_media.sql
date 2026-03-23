-- Migration: 002_add_provenance_to_media.sql
-- Enforces intelligence provenance by treating media scraps as immutable ledger snapshots.

ALTER TABLE raw_media_mentions ADD COLUMN IF NOT EXISTS provenance_hash VARCHAR;
ALTER TABLE raw_media_mentions ADD COLUMN IF NOT EXISTS snapshot_type VARCHAR DEFAULT 'TEXT_SCRAPE';

-- For existing ledgers, generate a fast hash from source + content + timestamp to backfill the immutable proof.
UPDATE raw_media_mentions
SET provenance_hash = md5(COALESCE(source, '') || COALESCE(content, '') || COALESCE(timestamp::VARCHAR, ''))
WHERE provenance_hash IS NULL;
