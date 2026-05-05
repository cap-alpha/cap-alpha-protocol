/**
 * POST /api/billing/lemon-squeezy
 *
 * Creates a LemonSqueezy hosted checkout session and returns the checkout URL.
 * The user is redirected to this URL to complete payment. After payment the
 * subscription_created webhook fires and grants the tier via
 * POST /api/webhooks/lemon-squeezy.
 *
 * Required env vars:
 *   LEMONSQUEEZY_API_KEY          — LS API key
 *   LEMONSQUEEZY_STORE_ID         — numeric store ID from LS dashboard
 *   LEMONSQUEEZY_PRO_VARIANT_ID   — variant ID for the Pro plan
 *   LEMONSQUEEZY_AGENT_VARIANT_ID — variant ID for the Agent plan
 */

import { NextRequest, NextResponse } from "next/server";
import { auth, clerkClient } from "@clerk/nextjs/server";

import { createCheckout } from "@/lib/lemon-squeezy";

const VARIANT_IDS: Record<string, string | undefined> = {
    pro: process.env.LEMONSQUEEZY_PRO_VARIANT_ID,
    agent: process.env.LEMONSQUEEZY_AGENT_VARIANT_ID,
};

export async function POST(req: NextRequest) {
    const { userId } = auth();
    if (!userId) {
        return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const body = await req.json().catch(() => ({})) as { plan?: string };
    const plan: string = body.plan ?? "pro";
    const variantId = VARIANT_IDS[plan];

    if (!variantId) {
        return NextResponse.json(
            { error: `Unknown plan: ${plan}` },
            { status: 400 }
        );
    }

    const storeId = process.env.LEMONSQUEEZY_STORE_ID;
    if (!storeId) {
        console.error("[LS Checkout] LEMONSQUEEZY_STORE_ID is not set");
        return NextResponse.json(
            { error: "Store not configured" },
            { status: 500 }
        );
    }

    try {
        const user = await clerkClient.users.getUser(userId);
        const email = user.emailAddresses[0]?.emailAddress;

        const checkoutUrl = await createCheckout({
            userId,
            variantId,
            email,
            storeId,
        });

        return NextResponse.json({ url: checkoutUrl });
    } catch (err) {
        console.error("[LS Checkout] Failed to create checkout:", err);
        return NextResponse.json(
            { error: "Failed to create checkout" },
            { status: 500 }
        );
    }
}
