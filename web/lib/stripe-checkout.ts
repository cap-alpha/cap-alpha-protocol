/**
 * Stripe checkout helper.
 *
 * Extracted from app/api/billing/checkout/route.ts so the router can
 * lazy-import it only when PAYMENT_PROCESSOR=stripe. Environments that never
 * use Stripe will never hit the missing-env-var guard at module init time.
 *
 * Required env vars:
 *   STRIPE_SECRET_KEY
 *   STRIPE_PRO_PRICE_ID
 *   STRIPE_API_STARTER_PRICE_ID
 *   STRIPE_API_GROWTH_PRICE_ID
 */

import { clerkClient } from "@clerk/nextjs/server";

import { getStripe } from "@/lib/stripe";

export async function createStripeCheckout({
    userId,
    plan,
    email,
    stripeCustomerId,
}: {
    userId: string;
    plan: string;
    email: string | undefined;
    /** Pre-fetched from Clerk publicMetadata to avoid a second getUser round-trip. */
    stripeCustomerId: string | undefined;
}): Promise<string> {
    // Resolve PRICE_IDS at call time so tests can mutate process.env without
    // module-level snapshot issues, and to stay consistent with the lazy-loading
    // intent of this helper (only accessed when PAYMENT_PROCESSOR=stripe).
    const PRICE_IDS: Record<string, string | undefined> = {
        pro: process.env.STRIPE_PRO_PRICE_ID,
        api_starter: process.env.STRIPE_API_STARTER_PRICE_ID,
        api_growth: process.env.STRIPE_API_GROWTH_PRICE_ID,
    };

    const priceId = PRICE_IDS[plan];
    if (!priceId) throw new Error(`[Stripe] Unknown plan: "${plan}". Check STRIPE_*_PRICE_ID env vars.`);

    const stripe = getStripe();
    const appUrl = process.env.NEXT_PUBLIC_APP_URL ?? "https://cap-alpha.co";

    // Look up or create Stripe customer — preserve customerId across sessions.
    // stripeCustomerId is passed in from route.ts (already fetched) to avoid
    // a redundant Clerk API call.
    let customerId = stripeCustomerId;
    if (!customerId) {
        const customer = await stripe.customers.create({
            email,
            metadata: { clerk_user_id: userId },
        });
        customerId = customer.id;
        await clerkClient.users.updateUserMetadata(userId, {
            publicMetadata: { stripe_customer_id: customerId },
        });
    }

    const session = await stripe.checkout.sessions.create({
        customer: customerId,
        client_reference_id: userId,
        mode: "subscription",
        line_items: [{ price: priceId, quantity: 1 }],
        success_url: `${appUrl}/dashboard?checkout=success`,
        cancel_url: `${appUrl}/pricing?checkout=cancelled`,
        allow_promotion_codes: true,
        subscription_data: { metadata: { clerk_user_id: userId } },
    });

    if (!session.url) throw new Error("[Stripe] Checkout session returned no URL.");
    return session.url;
}
