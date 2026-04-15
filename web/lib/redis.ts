/**
 * Upstash Redis client singleton.
 *
 * Initialised from UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN env vars.
 * When those are missing the module exports `null` and logs a warning so the
 * app can still start for local dev (rate limiting becomes a no-op).
 */
import { Redis } from "@upstash/redis";

function createRedisClient(): Redis | null {
    const url = process.env.UPSTASH_REDIS_REST_URL;
    const token = process.env.UPSTASH_REDIS_REST_TOKEN;

    if (!url || !token) {
        console.warn(
            "[redis] UPSTASH_REDIS_REST_URL and/or UPSTASH_REDIS_REST_TOKEN not set. " +
                "Redis features (rate limiting, tier caching) will be disabled."
        );
        return null;
    }

    return new Redis({ url, token });
}

/**
 * Shared Redis client. `null` when env vars are missing (local dev fallback).
 */
export const redis: Redis | null = createRedisClient();
