import { NextRequest, NextResponse } from "next/server";
import Stripe from "stripe";
import { auth, clerkClient } from "@clerk/nextjs/server";

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!, {
    apiVersion: "2026-04-22.dahlia",
});

const PRICE_IDS: Record<string, string | undefined> = {
    pro: process.env.STRIPE_PRO_PRICE_ID,
    api_starter: process.env.STRIPE_API_STARTER_PRICE_ID,
    api_growth: process.env.STRIPE_API_GROWTH_PRICE_ID,
};

export async function POST(req: NextRequest) {
    const { userId } = auth();
    if (!userId) {
        return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const body = await req.json().catch(() => ({}));
    const plan: string = body.plan ?? "pro";
    const priceId = PRICE_IDS[plan];

    if (!priceId) {
        return NextResponse.json({ error: `Unknown plan: ${plan}` }, { status: 400 });
    }

    const appUrl = process.env.NEXT_PUBLIC_APP_URL ?? "https://cap-alpha.co";

    // Look up existing Stripe customer or create one
    const user = await clerkClient.users.getUser(userId);
    let customerId = user.publicMetadata?.stripe_customer_id as string | undefined;

    if (!customerId) {
        const email = user.emailAddresses[0]?.emailAddress;
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
        subscription_data: {
            metadata: { clerk_user_id: userId },
        },
    });

    return NextResponse.json({ url: session.url });
}
