-- Migration 013: Create monetization.stripe_events audit table (Issue #147)
--
-- Immutable audit log of every Stripe webhook event processed by
-- POST /api/webhooks/stripe. Used for idempotency checks, billing
-- dispute resolution, and monitoring subscription state transitions.
--
-- Partitioned by processed_at date for cost-efficient time-range scans.
-- Clustered by event_type for per-type queries.

CREATE TABLE IF NOT EXISTS `cap-alpha-protocol.monetization.stripe_events` (
    event_id          STRING    NOT NULL,   -- Stripe event ID (evt_xxx) — globally unique
    event_type        STRING    NOT NULL,   -- e.g. checkout.session.completed
    user_id           STRING,              -- Clerk user ID, null if not yet resolved
    stripe_customer_id STRING,             -- Stripe customer ID (cus_xxx)
    livemode          BOOL      NOT NULL,  -- false = test mode
    payload           JSON,               -- Serialized event.data.object
    processed_at      TIMESTAMP NOT NULL   -- When our handler processed the event
)
PARTITION BY DATE(processed_at)
CLUSTER BY event_type, stripe_customer_id;
