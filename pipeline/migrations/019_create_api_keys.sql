-- Migration: 019_create_api_keys
-- Issue: #108 — SP30-1 B2B API Key Authentication
-- Description: Stores hashed B2B API keys for authenticating /v1/cap/ routes.
--   Keys are stored as SHA-256 hashes — raw keys are never persisted.
--
-- Key lifecycle:
--   1. Admin generates a random key (e.g. openssl rand -hex 32)
--   2. SHA-256 hash of the key is inserted here with owner/tier info
--   3. Consumer sends the raw key in X-API-Key header
--   4. API hashes the incoming key and looks it up in this table
--
-- Tiers:
--   free     — read-only cap data, 100 req/day
--   standard — all cap + pundit endpoints, 1,000 req/day
--   premium  — all endpoints + bulk export, 10,000 req/day

CREATE TABLE IF NOT EXISTS `{project_id}.gold_layer.api_keys` (
    key_hash       STRING    NOT NULL,   -- SHA-256 hex of the raw API key
    owner          STRING    NOT NULL,   -- human-readable owner identifier
    tier           STRING    NOT NULL,   -- free | standard | premium
    is_active      BOOL      NOT NULL DEFAULT TRUE,
    daily_limit    INT64     NOT NULL,   -- max requests per calendar day (UTC)
    created_at     TIMESTAMP NOT NULL,
    revoked_at     TIMESTAMP,           -- NULL if still active
    notes          STRING               -- optional memo
);
