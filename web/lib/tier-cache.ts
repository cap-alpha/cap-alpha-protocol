/**
 * Tier cache backed by Upstash Redis.
 *
 * Hot-path tier resolution: check Redis first, fall back to Clerk private
 * metadata, then cache the result with a 5-minute TTL.
 */
import { redis } from "./redis";

/** TTL for cached tier values (seconds). */
const TIER_CACHE_TTL_SECONDS = 300; // 5 minutes

/** Redis key prefix for tier cache entries. */
function tierKey(userId: string): string {
    return `tier:${userId}`;
}

/**
 * Resolve a user's tier, checking Redis cache first.
 *
 * Falls back to Clerk private metadata when the cache is cold, then stores
 * the result in Redis with a 5-minute TTL for subsequent requests.
 *
 * When Redis is unavailable the function returns "free" (safe default).
 */
export async function getCachedTier(userId: string): Promise<string> {
    if (!redis) {
        console.warn("[tier-cache] Redis unavailable, returning default tier 'free'");
        return "free";
    }

    try {
        // Check Redis cache
        const cached = await redis.get<string>(tierKey(userId));
        if (cached) {
            return cached;
        }

        // Cache miss -- resolve from Clerk private metadata
        const tier = await resolveTierFromClerk(userId);

        // Store in cache with TTL
        await redis.set(tierKey(userId), tier, { ex: TIER_CACHE_TTL_SECONDS });

        return tier;
    } catch (error) {
        console.error("[tier-cache] Error resolving tier, falling back to 'free':", error);
        return "free";
    }
}

/**
 * Invalidate the cached tier for a user.
 *
 * Should be called by webhook handlers when a user's subscription tier changes
 * (e.g. Stripe webhook for plan upgrade/downgrade).
 */
export async function invalidateTierCache(userId: string): Promise<void> {
    if (!redis) {
        return;
    }

    try {
        await redis.del(tierKey(userId));
    } catch (error) {
        console.error("[tier-cache] Error invalidating tier cache:", error);
    }
}

/**
 * Resolve tier from Clerk private metadata.
 *
 * TODO(#146/#147): Wire to real Clerk metadata once Stripe integration lands.
 * For now returns "free" as the default tier.
 */
async function resolveTierFromClerk(_userId: string): Promise<string> {
    // Stub: always returns "free" until Stripe integration in #146/#147.
    // When wired up, this will call:
    //   const user = await clerkClient.users.getUser(userId);
    //   return (user.privateMetadata.tier as string) || "free";
    return "free";
}
