-- BigQuery schema for API key management
-- Dataset: monetization
-- Table: api_keys
--
-- NOTE: No `tier` column — tier is resolved from the user's Stripe subscription
-- at request time via Clerk user metadata.

CREATE TABLE IF NOT EXISTS `monetization.api_keys` (
    -- Primary key: full key ID including prefix (capk_live_xxx or capk_test_xxx)
    key_id STRING NOT NULL,

    -- SHA-256(pepper || plaintext_key). Never store the plaintext key.
    key_hash STRING NOT NULL,

    -- Pepper version used to compute the hash. Allows pepper rotation
    -- without mass invalidation of existing keys.
    pepper_version INT64 NOT NULL DEFAULT 1,

    -- Last 4 characters of the key for dashboard display
    key_last_four STRING NOT NULL,

    -- Clerk user ID that owns this key
    user_id STRING NOT NULL,

    -- Forward-compatible scopes (no enforcement yet)
    scopes ARRAY<STRING>,

    -- Key status: 'active' or 'revoked'
    status STRING NOT NULL DEFAULT 'active',

    -- User-supplied label for the key
    name STRING NOT NULL,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    revoked_at TIMESTAMP,
    last_used_at TIMESTAMP,
    last_used_ip STRING
)
OPTIONS (
    description = 'API keys for the Pundit Prediction Ledger. Keys are hashed with a versioned pepper. Tier is resolved from the user, not stored on the key.'
);
