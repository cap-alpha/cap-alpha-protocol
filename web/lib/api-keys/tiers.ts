/**
 * Tier configuration and resolution.
 *
 * Tier lives on the USER (via Clerk/Stripe), NOT on the API key.
 * Per-tier key caps are enforced on key creation.
 */

export type Tier = "free" | "pro" | "api_starter" | "api_growth" | "enterprise";

interface TierConfig {
    maxKeys: number;
}

const TIER_CONFIGS: Record<Tier, TierConfig> = {
    free: { maxKeys: 1 },
    pro: { maxKeys: 3 },
    api_starter: { maxKeys: 10 },
    api_growth: { maxKeys: 25 },
    enterprise: { maxKeys: 25 },
};

/**
 * Resolve a user's tier from their subscription state.
 *
 * TODO(#146/#147): Wire this to Stripe subscription state via Clerk metadata.
 * For now, returns 'free' as the default tier for all users.
 */
export async function getUserTier(_userId: string): Promise<Tier> {
    // Stub: always returns 'free' until Stripe integration in #146/#147
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
