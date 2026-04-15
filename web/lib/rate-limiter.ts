/**
 * Rate limiter backed by Upstash Redis.
 *
 * Defines per-tier rate limit configs using @upstash/ratelimit with a
 * sliding window algorithm. When Redis is unavailable, all requests
 * are allowed (no-op mode for local dev).
 */
import { Ratelimit } from "@upstash/ratelimit";
import { redis } from "./redis";

/** Supported billing tiers. Must stay in sync with api-keys/tiers.ts. */
export type RateLimitTier =
    | "free"
    | "pro"
    | "api_starter"
    | "api_growth"
    | "enterprise";

export interface RateLimitResult {
    success: boolean;
    limit: number;
    remaining: number;
    reset: number; // Unix timestamp (ms)
}

/**
 * Per-tier rate limit configuration.
 *
 * Each tier has a per-minute and a per-day limiter.  The tighter of the
 * two governs any given request.
 */
interface TierLimitConfig {
    perMinute: number;
    perDay: number;
}

const TIER_LIMITS: Record<RateLimitTier, TierLimitConfig> = {
    free: { perMinute: 100, perDay: 10_000 },
    pro: { perMinute: 1_000, perDay: 100_000 },
    api_starter: { perMinute: 10_000, perDay: 1_000_000 },
    api_growth: { perMinute: 100_000, perDay: 10_000_000 },
    enterprise: { perMinute: 100_000, perDay: 10_000_000 },
};

/**
 * Build Ratelimit instances for a tier.
 *
 * We cache instances per tier so they are created at most once.
 */
const minuteLimiters = new Map<string, Ratelimit>();
const dayLimiters = new Map<string, Ratelimit>();

function getMinuteLimiter(tier: RateLimitTier): Ratelimit | null {
    if (!redis) return null;

    if (!minuteLimiters.has(tier)) {
        minuteLimiters.set(
            tier,
            new Ratelimit({
                redis,
                limiter: Ratelimit.slidingWindow(
                    TIER_LIMITS[tier].perMinute,
                    "1 m"
                ),
                prefix: `rl:min:${tier}`,
                analytics: true,
            })
        );
    }
    return minuteLimiters.get(tier)!;
}

function getDayLimiter(tier: RateLimitTier): Ratelimit | null {
    if (!redis) return null;

    if (!dayLimiters.has(tier)) {
        dayLimiters.set(
            tier,
            new Ratelimit({
                redis,
                limiter: Ratelimit.slidingWindow(
                    TIER_LIMITS[tier].perDay,
                    "1 d"
                ),
                prefix: `rl:day:${tier}`,
                analytics: true,
            })
        );
    }
    return dayLimiters.get(tier)!;
}

/**
 * Check rate limits for a request.
 *
 * The identifier is typically the hashed API key so limits are scoped
 * per-key (which maps 1:1 to a user for most tiers).
 *
 * When Redis is unavailable the request is always allowed.
 */
export async function checkRateLimit(
    identifier: string,
    tier: string
): Promise<RateLimitResult> {
    const resolvedTier = (
        Object.keys(TIER_LIMITS).includes(tier) ? tier : "free"
    ) as RateLimitTier;

    const minLimiter = getMinuteLimiter(resolvedTier);
    const dayLimiter = getDayLimiter(resolvedTier);

    // No-op when Redis is unavailable
    if (!minLimiter || !dayLimiter) {
        console.warn("[rate-limiter] Redis unavailable, allowing request (no-op mode)");
        return {
            success: true,
            limit: TIER_LIMITS[resolvedTier].perMinute,
            remaining: TIER_LIMITS[resolvedTier].perMinute,
            reset: Date.now() + 60_000,
        };
    }

    // Check both limits concurrently
    const [minResult, dayResult] = await Promise.all([
        minLimiter.limit(identifier),
        dayLimiter.limit(identifier),
    ]);

    // If either limit is exceeded, deny the request.
    // Return the tighter (more restrictive) remaining count.
    const success = minResult.success && dayResult.success;
    const isMinTighter = minResult.remaining <= dayResult.remaining;
    const tighterResult = isMinTighter ? minResult : dayResult;
    const tighterLimit = isMinTighter
        ? TIER_LIMITS[resolvedTier].perMinute
        : TIER_LIMITS[resolvedTier].perDay;

    return {
        success,
        limit: tighterLimit,
        remaining: tighterResult.remaining,
        reset: tighterResult.reset,
    };
}

/**
 * Get the rate limit config for a tier (useful for tests and display).
 */
export function getRateLimitConfig(
    tier: string
): TierLimitConfig {
    const resolvedTier = (
        Object.keys(TIER_LIMITS).includes(tier) ? tier : "free"
    ) as RateLimitTier;
    return TIER_LIMITS[resolvedTier];
}
