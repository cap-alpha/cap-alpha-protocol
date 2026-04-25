/**
 * Stripe client singleton and tier mapping.
 *
 * Tier is derived from the Stripe price ID on each subscription event.
 * Price IDs are configured via environment variables so they work in both
 * test mode and live mode without code changes.
 */
import Stripe from "stripe";

import type { Tier } from "./api-keys/tiers";

export const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!, {
    apiVersion: "2024-12-18.acacia",
});

// Map Stripe price IDs → internal tier names.
// Each env var holds the price ID from the Stripe Dashboard.
// Example: STRIPE_PRICE_PRO=price_1OzXXXXXXXXXXXXX
function buildPriceMap(): Record<string, Tier> {
    const map: Record<string, Tier> = {};
    const entries: [string | undefined, Tier][] = [
        [process.env.STRIPE_PRICE_PRO, "pro"],
        [process.env.STRIPE_PRICE_API_STARTER, "api_starter"],
        [process.env.STRIPE_PRICE_ENTERPRISE, "enterprise"],
    ];
    for (const [priceId, tier] of entries) {
        if (priceId) map[priceId] = tier;
    }
    return map;
}

export function tierFromPriceId(priceId: string | null | undefined): Tier {
    if (!priceId) return "free";
    const map = buildPriceMap();
    return map[priceId] ?? "pro"; // unknown paid price → default to pro
}
