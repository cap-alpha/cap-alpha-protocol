import { NextRequest, NextResponse } from "next/server";
import { auth, clerkClient } from "@clerk/nextjs/server";

import { createCharge } from "@/lib/coinbase-commerce";

const USDC_PLANS = new Set(["pro"]);

export async function POST(req: NextRequest) {
    const { userId } = auth();
    if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

    const body = await req.json().catch(() => ({}));
    const plan: string = body.plan ?? "pro";

    if (!USDC_PLANS.has(plan)) {
        return NextResponse.json(
            { error: "USDC payments are only available for the Pro plan" },
            { status: 400 }
        );
    }

    const user = await clerkClient.users.getUser(userId);
    const email = user.emailAddresses[0]?.emailAddress;

    const charge = await createCharge({ userId, plan, email });
    return NextResponse.json({ url: charge.hosted_url });
}
