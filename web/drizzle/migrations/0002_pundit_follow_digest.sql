-- Migration: pundit follow system — digest tracking columns on users
-- Adds last_digest_sent_at and digest_unsubscribed_at to users.
-- Separate from emailUnsubscribedAt so users can opt-out of digests
-- while keeping transactional emails (receipts, API keys).
-- Part of issue #773 — return-user retention loop Phase 1.

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS last_digest_sent_at TIMESTAMP,
    ADD COLUMN IF NOT EXISTS digest_unsubscribed_at TIMESTAMP;
