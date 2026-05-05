-- Migration: LemonSqueezy billing columns + idempotency table
-- Adds ls_* subscription columns to users and creates ls_processed_events
-- for webhook idempotency (parallel to stripe_processed_events).

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS ls_customer_id TEXT,
    ADD COLUMN IF NOT EXISTS ls_subscription_id TEXT,
    ADD COLUMN IF NOT EXISTS ls_subscription_status TEXT,
    ADD COLUMN IF NOT EXISTS ls_variant_id TEXT,
    ADD COLUMN IF NOT EXISTS ls_current_period_end TIMESTAMP;

CREATE TABLE IF NOT EXISTS ls_processed_events (
    id SERIAL PRIMARY KEY,
    ls_event_id TEXT UNIQUE NOT NULL,
    event_type TEXT NOT NULL,
    processed_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ls_processed_events_event_id_idx ON ls_processed_events (ls_event_id);
