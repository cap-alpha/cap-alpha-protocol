/**
 * LemonSqueezy checkout helper.
 *
 * Extracted so the router can lazy-import it only when
 * PAYMENT_PROCESSOR=lemonsqueezy (the default). Depends on
 * web/lib/lemon-squeezy.ts which ships with PR #666.
 *
 * Required env vars:
 *   LEMONSQUEEZY_API_KEY
 *   LEMONSQUEEZY_STORE_ID
 *   LEMONSQUEEZY_PRO_VARIANT_ID
 *   LEMONSQUEEZY_AGENT_VARIANT_ID
 */

import { createCheckout } from "@/lib/lemon-squeezy";

const VARIANT_IDS: Record<string, string | undefined> = {
    pro: process.env.LEMONSQUEEZY_PRO_VARIANT_ID,
    agent: process.env.LEMONSQUEEZY_AGENT_VARIANT_ID,
};

export async function createLSCheckout({
    userId,
    plan,
    email,
}: {
    userId: string;
    plan: string;
    email: string | undefined;
}): Promise<string> {
    const variantId = VARIANT_IDS[plan];
    if (!variantId) {
        throw new Error(
            `[LemonSqueezy] Unknown plan: "${plan}". Check LEMONSQUEEZY_*_VARIANT_ID env vars.`
        );
    }

    const storeId = process.env.LEMONSQUEEZY_STORE_ID;
    if (!storeId) throw new Error("[LemonSqueezy] LEMONSQUEEZY_STORE_ID is not set.");

    return createCheckout({ userId, variantId, email, storeId });
}
