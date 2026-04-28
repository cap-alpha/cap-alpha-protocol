/**
 * Rate limiting infrastructure using Upstash Redis.
 *
 * Implements tiered sliding-window rate limits (per minute).
 * Gracefully degrades (fail-open) when UPSTASH_REDIS_REST_URL is not
 * configured, so the API remains available before Upstash is provisioned.
 *
 * Issue: #144
 */
import { Ratelimit } from "@upstash/ratelimit";
import { Redis } from "@upstash/redis";
import type { Tier } from "@/lib/api-keys/tiers";

export interface RateLimitResult {
    success: boolean;
    limit: number;
    remaining: number;
    /** Unix timestamp (seconds) when the current window resets */
    reset: number;
    /** Seconds to wait before retrying — only set when success=false */
    retryAfter?: number;
}

/** Per-minute request limits by tier */
export const TIER_RATE_LIMITS: Record<Tier, number> = {
    free: 100,
    pro: 1_000,
    api_starter: 10_000,
    api_growth: 100_000,
    enterprise: 1_000_000, // effectively unlimited
};

// Module-level cache — only populated when UPSTASH env vars are present.
// Re-checked on every call when env vars are absent (fail-open path).
let _redis: Redis | null = null;
const _limiters = new Map<Tier, Ratelimit>();

function getRedis(): Redis | null {
    if (_redis !== null) return _redis;

    const url = process.env.UPSTASH_REDIS_REST_URL;
    const token = process.env.UPSTASH_REDIS_REST_TOKEN;

    if (!url || !token) {
        // Env vars absent — do NOT cache null so we re-check on each call.
        return null;
    }

    _redis = new Redis({ url, token });
    return _redis;
}

function getLimiter(tier: Tier): Ratelimit | null {
    const redis = getRedis();
    if (!redis) return null;

    if (_limiters.has(tier)) return _limiters.get(tier)!;

    const limiter = new Ratelimit({
        redis,
        limiter: Ratelimit.slidingWindow(TIER_RATE_LIMITS[tier], "60 s"),
        prefix: `rl:${tier}`,
        analytics: true,
    });

    _limiters.set(tier, limiter);
    return limiter;
}

/**
 * Check the rate limit for an API key.
 *
 * @param keyId - The API key ID used as the per-key rate limit identifier.
 * @param tier  - The user's subscription tier.
 * @returns Result with success flag and values for rate limit response headers.
 */
export async function checkRateLimit(
    keyId: string,
    tier: Tier
): Promise<RateLimitResult> {
    const limiter = getLimiter(tier);
    const limit = TIER_RATE_LIMITS[tier];

    // Fail-open: allow all requests if Upstash is not configured.
    if (!limiter) {
        return {
            success: true,
            limit,
            remaining: limit,
            reset: Math.floor(Date.now() / 1000) + 60,
        };
    }

    const result = await limiter.limit(keyId);
    const resetSeconds = Math.floor(result.reset / 1000);
    const nowSeconds = Math.floor(Date.now() / 1000);

    return {
        success: result.success,
        limit: result.limit,
        remaining: result.remaining,
        reset: resetSeconds,
        ...(result.success
            ? {}
            : { retryAfter: Math.max(0, resetSeconds - nowSeconds) }),
    };
}

/**
 * Build rate limit response headers from a RateLimitResult.
 *
 * Include these on every API response so clients can self-throttle.
 */
export function buildRateLimitHeaders(result: RateLimitResult): HeadersInit {
    const headers: Record<string, string> = {
        "X-RateLimit-Limit": String(result.limit),
        "X-RateLimit-Remaining": String(result.remaining),
        "X-RateLimit-Reset": String(result.reset),
    };

    if (result.retryAfter !== undefined) {
        headers["Retry-After"] = String(result.retryAfter);
    }

    return headers;
}
