-- BigQuery schema: monetization.api_requests
-- Purpose: every paid API request is streamed here for usage analytics,
--          abuse detection, and pricing research (#148, #122).
--
-- Partitioned by day on `ts` and clustered by (key_id, user_id) so that
-- per-key and per-user queries hit only the relevant partitions.
--
-- To apply:
--   export PROJECT_ID=cap-alpha-protocol
--   bq query --use_legacy_sql=false --project_id=$PROJECT_ID \
--     < web/lib/api-metering.sql

CREATE TABLE IF NOT EXISTS `cap-alpha-protocol.monetization.api_requests` (
    -- When the request was received (partition key)
    ts TIMESTAMP NOT NULL,

    -- API key that made the request (clustered)
    key_id STRING NOT NULL,

    -- Clerk user ID that owns the key (clustered)
    user_id STRING NOT NULL,

    -- Subscription tier at request time (free/pro/agent/api_starter/api_growth/enterprise)
    tier STRING NOT NULL,

    -- URL path template for grouping — e.g. /v1/pundits/{id}
    endpoint STRING NOT NULL,

    -- Resolved URL path — e.g. /v1/pundits/adam-schefter (for per-endpoint CTAs)
    endpoint_path STRING NOT NULL,

    -- HTTP method (GET, POST, etc.)
    method STRING NOT NULL,

    -- HTTP response status code
    status_code INT64 NOT NULL,

    -- End-to-end latency in milliseconds
    latency_ms INT64 NOT NULL,

    -- Response body size in bytes
    bytes_out INT64 NOT NULL,

    -- Caller's User-Agent header (nullable)
    user_agent STRING,

    -- SHA-256(METERING_IP_PEPPER || ip) — for abuse detection, never raw IP
    ip_hash STRING,

    -- Whether this request hit the rate limit
    rate_limit_hit BOOL NOT NULL DEFAULT FALSE,

    -- Two-axis quota enforcement: "cheap" = KV/lookup, "expensive" = /ask,/backtest,semantic
    cost_class STRING NOT NULL,

    -- Sport slug (nfl / mlb / …) for future multi-sport filtering
    sport STRING NOT NULL DEFAULT 'nfl'
)
PARTITION BY DATE(ts)
CLUSTER BY key_id, user_id
OPTIONS (
    description = 'Per-request API metering log. Fire-and-forget streaming inserts. '
                  'Partitioned daily, clustered by key_id + user_id. '
                  'ip_hash is SHA-256(pepper || ip) — never raw IPs. '
                  'cost_class distinguishes cheap (quota-A) vs expensive (quota-B) calls. '
                  'Feeds: usage dashboard (#148), pricing research (#122).',
    require_partition_filter = FALSE
);
