/**
 * POST /api/billing/checkout
 *
 * Processor-agnostic checkout router. Delegates to the active payment
 * processor based on the PAYMENT_PROCESSOR environment variable.
 *
 * Supported values:
 *   lemonsqueezy  (default) — LemonSqueezy hosted checkout
 *   stripe                  — Stripe Checkout session
 *
 * Switching processors = one env var change + redeploy. No code changes.
 *
 * Processor helpers are lazy-imported so that environments missing one
 * processor's env vars don't blow up at module init time (only the active
 * processor's env vars are required to be present).
 */

import { NextRequest, NextResponse } from "next/server";
import { auth, clerkClient } from "@clerk/nextjs/server";

/** Known plans — validated before dispatching to avoid processor-specific 500s. */
const KNOWN_PLANS = new Set(["pro", "api_starter", "api_growth", "agent"]);

export async function POST(req: NextRequest) {
    const { userId } = auth();
    if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

    const body = await req.json().catch(() => ({})) as { plan?: string };
    const plan: string = body.plan ?? "pro";

    // Validate plan before touching any payment provider to keep 4xx/5xx clean.
    if (!KNOWN_PLANS.has(plan)) {
        return NextResponse.json({ error: `Unknown plan: "${plan}"` }, { status: 400 });
    }

    const processor = process.env.PAYMENT_PROCESSOR ?? "lemonsqueezy";

    // Warn early if PAYMENT_PROCESSOR has a typo — the default fallback is
    // silent, so without this a misconfiguration is invisible in logs.
    if (processor !== "stripe" && processor !== "lemonsqueezy") {
        console.warn(
            `[Billing] Unknown PAYMENT_PROCESSOR="${processor}", falling back to lemonsqueezy`
        );
    }

    // Fetch the Clerk user once here so processor helpers don't need to make
    // their own redundant round-trips.
    const user = await clerkClient.users.getUser(userId);
    const email = user.emailAddresses[0]?.emailAddress;

    try {
        let url: string;
        switch (processor) {
            case "stripe": {
                const stripeCustomerId = user.publicMetadata?.stripe_customer_id as string | undefined;
                const { createStripeCheckout } = await import("@/lib/stripe-checkout");
                url = await createStripeCheckout({ userId, plan, email, stripeCustomerId });
                break;
            }
            case "lemonsqueezy":
            default: {
                const { createLSCheckout } = await import("@/lib/ls-checkout");
                url = await createLSCheckout({ userId, plan, email });
                break;
            }
        }
        return NextResponse.json({ url });
    } catch (err) {
        console.error(`[Billing] ${processor} checkout failed:`, err);
        return NextResponse.json({ error: "Checkout creation failed" }, { status: 500 });
    }
}
