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

async function handleStripe(userId: string, plan: string, email: string | undefined): Promise<string> {
    const { createStripeCheckout } = await import("@/lib/stripe-checkout");
    return createStripeCheckout({ userId, plan, email });
}

async function handleLemonSqueezy(userId: string, plan: string, email: string | undefined): Promise<string> {
    const { createLSCheckout } = await import("@/lib/ls-checkout");
    return createLSCheckout({ userId, plan, email });
}

export async function POST(req: NextRequest) {
    const { userId } = auth();
    if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

    const body = await req.json().catch(() => ({})) as { plan?: string };
    const plan: string = body.plan ?? "pro";

    const processor = process.env.PAYMENT_PROCESSOR ?? "lemonsqueezy";

    const user = await clerkClient.users.getUser(userId);
    const email = user.emailAddresses[0]?.emailAddress;

    try {
        let url: string;
        switch (processor) {
            case "stripe":
                url = await handleStripe(userId, plan, email);
                break;
            case "lemonsqueezy":
            default:
                url = await handleLemonSqueezy(userId, plan, email);
                break;
        }
        return NextResponse.json({ url });
    } catch (err) {
        console.error(`[Billing] ${processor} checkout failed:`, err);
        return NextResponse.json({ error: "Checkout creation failed" }, { status: 500 });
    }
}
