/**
 * Coinbase Commerce REST client — charge creation + webhook signature verification.
 *
 * USDC-only: enforced at the webhook layer (payments[0].value.crypto.currency).
 * Lazy API key access so environments without COINBASE_COMMERCE_API_KEY do not
 * fail at module import time before the handler can return a controlled error.
 *
 * Required env vars:
 *   COINBASE_COMMERCE_API_KEY         — from Coinbase Commerce Dashboard → API keys
 *   COINBASE_COMMERCE_WEBHOOK_SECRET  — from Coinbase Commerce Dashboard → Webhooks
 */

import crypto from "node:crypto";

const API_BASE = "https://api.commerce.coinbase.com";
const API_VERSION = "2018-03-22";

function getApiKey(): string {
    const key = process.env.COINBASE_COMMERCE_API_KEY;
    if (!key) throw new Error("[Coinbase] COINBASE_COMMERCE_API_KEY is not set.");
    return key;
}

// Plan → USD price. Only "pro" is available via USDC for now.
const PLAN_AMOUNTS: Record<string, string> = {
    pro: "9.00",
};

export interface CoinbaseCharge {
    id: string;
    code: string;
    hosted_url: string;
    expires_at: string;
    metadata: Record<string, string>;
}

export async function createCharge({
    userId,
    plan,
    email,
}: {
    userId: string;
    plan: string;
    email?: string;
}): Promise<CoinbaseCharge> {
    const apiKey = getApiKey();
    const appUrl = process.env.NEXT_PUBLIC_APP_URL ?? "https://cap-alpha.co";

    const amount = PLAN_AMOUNTS[plan];
    if (!amount) throw new Error(`[Coinbase] No price configured for plan "${plan}"`);

    const res = await fetch(`${API_BASE}/charges`, {
        method: "POST",
        headers: {
            "X-CC-Api-Key": apiKey,
            "X-CC-Version": API_VERSION,
            "Content-Type": "application/json",
        },
        body: JSON.stringify({
            name: "Cap Alpha Pro",
            description: "Monthly Pro subscription — USDC only",
            local_price: { amount, currency: "USD" },
            pricing_type: "fixed_price",
            metadata: { userId, plan, ...(email ? { email } : {}) },
            redirect_url: `${appUrl}/dashboard?checkout=success&method=crypto`,
            cancel_url: `${appUrl}/pricing?checkout=cancelled`,
        }),
    });

    if (!res.ok) {
        const err = await res.text();
        throw new Error(`[Coinbase] Failed to create charge (${res.status}): ${err}`);
    }

    const json = (await res.json()) as { data: CoinbaseCharge };
    return json.data;
}

export function verifyWebhookSignature(
    rawBody: string,
    signature: string,
    secret: string
): boolean {
    const expected = crypto
        .createHmac("sha256", secret)
        .update(rawBody, "utf8")
        .digest("hex");
    try {
        return crypto.timingSafeEqual(
            Buffer.from(expected, "hex"),
            Buffer.from(signature.toLowerCase(), "hex")
        );
    } catch {
        return false;
    }
}
