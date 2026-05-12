/**
 * Tier utilities for Server Components and Route Handlers.
 *
 * Reads `clerk.publicMetadata.tier` (written by the Stripe and LemonSqueezy
 * webhook handlers) and exposes typed helpers for gating features.
 *
 * Issue: #771 Phase 1
 */

import { currentUser } from "@clerk/nextjs/server";

/** Tiers that grant access to Pro-gated features on the web surface. */
export const PAID_TIERS = new Set(["pro", "agent"]);

/** Maximum predictions returned to a free-tier user on the predictions API. */
export const FREE_PREDICTION_CAP = 15;

export type UserTier = "free" | "pro" | "agent";

/**
 * Resolve the current user's tier from Clerk publicMetadata.
 *
 * Intended for **Server Components and Route Handlers** only — requires an
 * active Clerk request context. Returns `"free"` for unauthenticated users
 * and for any tier string not in the known paid set.
 */
export async function getUserTier(): Promise<UserTier> {
    const user = await currentUser();
    if (!user) return "free";
    const tier = (user.publicMetadata?.tier as string) ?? "free";
    if (PAID_TIERS.has(tier)) {
        return tier as UserTier;
    }
    return "free";
}

/**
 * Returns `true` if the current request comes from a Pro or Agent subscriber.
 */
export async function isPro(): Promise<boolean> {
    const tier = await getUserTier();
    return PAID_TIERS.has(tier);
}
