import { NextRequest, NextResponse } from "next/server";
import Stripe from "stripe";
import { auth, clerkClient } from "@clerk/nextjs/server";

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!, {
    apiVersion: "2026-04-22.dahlia",
});

export async function POST(req: NextRequest) {
    const { userId } = auth();
    if (!userId) {
        return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const user = await clerkClient.users.getUser(userId);
    const customerId = user.publicMetadata?.stripe_customer_id as string | undefined;

    if (!customerId) {
        return NextResponse.json(
            { error: "No billing account found. Please subscribe first." },
            { status: 404 }
        );
    }

    const appUrl = process.env.NEXT_PUBLIC_APP_URL ?? "https://cap-alpha.co";

    const session = await stripe.billingPortal.sessions.create({
        customer: customerId,
        return_url: `${appUrl}/dashboard`,
    });

    return NextResponse.json({ url: session.url });
}
