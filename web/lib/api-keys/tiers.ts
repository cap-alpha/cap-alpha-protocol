/**
 * Tier configuration and resolution.
 *
 * Tier lives on the USER (via Clerk/Stripe), NOT on the API key.
 * Per-tier key caps are enforced on key creation.
 */

import { clerkClient } from "@clerk/nextjs/server";

export type Tier = "free" | "pro" | "api_starter" | "enterprise";

interface TierConfig {
    maxKeys: number;
}

const TIER_CONFIGS: Record<Tier, TierConfig> = {
    free: { maxKeys: 1 },
    pro: { maxKeys: 3 },
    api_starter: { maxKeys: 10 },
    enterprise: { maxKeys: 25 },
};

/**
 * Resolve a user's tier from Clerk publicMetadata.
 *
 * The Stripe webhook handler (POST /api/webhooks/stripe) sets
 * publicMetadata.tier on every subscription state change, so this
 * read is O(1) without touching the database on every API request.
 */
export async function getUserTier(userId: string): Promise<Tier> {
    try {
        const user = await clerkClient.users.getUser(userId);
        const tier = user.publicMetadata?.tier as Tier | undefined;
        if (tier && tier in TIER_CONFIGS) {
            return tier;
        }
    } catch (err) {
        console.error(`[getUserTier] Clerk lookup failed for ${userId}:`, err);
    }
    return "free";
}

/**
 * Get the maximum number of active API keys allowed for a given tier.
 */
export function getMaxKeysForTier(tier: Tier): number {
    return TIER_CONFIGS[tier].maxKeys;
}

/**
 * Get the full tier config (for future use with rate limits, etc.)
 */
export function getTierConfig(tier: Tier): TierConfig {
    return TIER_CONFIGS[tier];
}
