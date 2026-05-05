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

import Stripe from "stripe";
import { clerkClient } from "@clerk/nextjs/server";

const PRICE_IDS: Record<string, string | undefined> = {
    pro: process.env.STRIPE_PRO_PRICE_ID,
    api_starter: process.env.STRIPE_API_STARTER_PRICE_ID,
    api_growth: process.env.STRIPE_API_GROWTH_PRICE_ID,
};

function getStripeClient(): Stripe {
    const key = process.env.STRIPE_SECRET_KEY;
    if (!key) throw new Error("[Stripe] STRIPE_SECRET_KEY is not set. Configure it in your environment.");
    return new Stripe(key, { apiVersion: "2026-04-22.dahlia" });
}

export async function createStripeCheckout({
    userId,
    plan,
    email,
}: {
    userId: string;
    plan: string;
    email: string | undefined;
}): Promise<string> {
    const priceId = PRICE_IDS[plan];
    if (!priceId) throw new Error(`[Stripe] Unknown plan: "${plan}". Check STRIPE_*_PRICE_ID env vars.`);

    const stripe = getStripeClient();
    const appUrl = process.env.NEXT_PUBLIC_APP_URL ?? "https://cap-alpha.co";

    // Look up or create Stripe customer — preserve customerId across sessions
    const user = await clerkClient.users.getUser(userId);
    let customerId = user.publicMetadata?.stripe_customer_id as string | undefined;
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
