/**
 * Stripe client singleton and tier mapping.
 *
 * Tier is derived from the Stripe price ID on each subscription event.
 * Price IDs are configured via environment variables so they work in both
 * test mode and live mode without code changes.
 */
import Stripe from "stripe";

import type { Tier } from "./api-keys/tiers";

// Lazily-initialized Stripe client so that environments without billing
// configured (e.g., local dev without STRIPE_SECRET_KEY) do not fail at
// module import time before the webhook handler can return a controlled error.
let _stripe: Stripe | null = null;

export function getStripe(): Stripe {
    if (!_stripe) {
        const key = process.env.STRIPE_SECRET_KEY;
        if (!key) {
            throw new Error(
                "[Stripe] STRIPE_SECRET_KEY is not set. Configure it in your environment."
            );
        }
        _stripe = new Stripe(key, { apiVersion: "2026-04-22.dahlia" });
    }
    return _stripe;
}

/** Convenience re-export for call sites that already validate env at startup. */
export const stripe = {
    subscriptions: {
        retrieve: (...args: Parameters<Stripe["subscriptions"]["retrieve"]>) =>
            getStripe().subscriptions.retrieve(...args),
    },
    webhooks: {
        constructEvent: (
            ...args: Parameters<Stripe["webhooks"]["constructEvent"]>
        ) => getStripe().webhooks.constructEvent(...args),
    },
} as unknown as Stripe;

// Map Stripe price IDs → internal tier names.
// Each env var holds the price ID from the Stripe Dashboard.
// Example: STRIPE_PRICE_PRO=price_1OzXXXXXXXXXXXXX
function buildPriceMap(): Record<string, Tier> {
    const map: Record<string, Tier> = {};
    const entries: [string | undefined, Tier][] = [
        [process.env.STRIPE_PRICE_PRO, "pro"],
        [process.env.STRIPE_PRICE_API_STARTER, "api_starter"],
        [process.env.STRIPE_PRICE_AGENT_STANDARD, "agent_standard"],
        [process.env.STRIPE_PRICE_AGENT_PRO, "agent_pro"],
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
    const tier = map[priceId];
    if (tier) return tier;
    // Unknown price ID — default to least-privileged tier and log so the
    // mapping can be fixed via env vars (never silently grant paid access).
    console.warn(
        `[Stripe] Unknown priceId "${priceId}" — defaulting to "free". ` +
            "Add the price ID to STRIPE_PRICE_PRO / STRIPE_PRICE_API_STARTER / STRIPE_PRICE_AGENT_STANDARD / STRIPE_PRICE_AGENT_PRO / STRIPE_PRICE_ENTERPRISE."
    );
    return "free";
}
