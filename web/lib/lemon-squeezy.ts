/**
 * LemonSqueezy client utilities.
 *
 * Uses native fetch — no SDK required for checkout creation and webhook
 * verification. The @lemonsqueezy/lemonsqueezy.js package is available but
 * we keep this thin layer consistent with the stripe.ts / coinbase patterns.
 *
 * Required env vars:
 *   LEMONSQUEEZY_API_KEY          — from LS Dashboard → Settings → API
 *   LEMONSQUEEZY_STORE_ID         — numeric store ID
 *   LEMONSQUEEZY_PRO_VARIANT_ID   — variant ID for the Pro plan
 *   LEMONSQUEEZY_AGENT_VARIANT_ID — variant ID for the Agent plan
 *   LEMONSQUEEZY_WEBHOOK_SECRET   — from LS Dashboard → Webhooks → signing secret
 */

import crypto from "crypto";

import type { Tier } from "./api-keys/tiers";

// ---------------------------------------------------------------------------
// API key guard (lazy, same pattern as stripe.ts)
// ---------------------------------------------------------------------------

function getLSApiKey(): string {
    const key = process.env.LEMONSQUEEZY_API_KEY;
    if (!key) {
        throw new Error(
            "[LemonSqueezy] LEMONSQUEEZY_API_KEY is not set. Configure it in your environment."
        );
    }
    return key;
}

// ---------------------------------------------------------------------------
// Tier mapping
// ---------------------------------------------------------------------------

/**
 * Map a LemonSqueezy variant ID to an internal tier name.
 *
 * Variant IDs are read from env vars so they work in both test and live mode
 * without code changes. Unknown variant IDs default to "free" (least-
 * privileged) — never silently grant paid access.
 */
export function tierFromVariantId(variantId: string | number | null | undefined): Tier {
    const id = String(variantId ?? "");
    if (id && id === process.env.LEMONSQUEEZY_PRO_VARIANT_ID) return "pro";
    if (id && id === process.env.LEMONSQUEEZY_AGENT_VARIANT_ID) return "agent";
    if (id) {
        console.warn(
            `[LemonSqueezy] Unknown variantId "${id}" — defaulting to "free". ` +
                "Add the variant ID to LEMONSQUEEZY_PRO_VARIANT_ID / LEMONSQUEEZY_AGENT_VARIANT_ID."
        );
    }
    return "free";
}

// ---------------------------------------------------------------------------
// Checkout creation
// ---------------------------------------------------------------------------

interface CreateCheckoutParams {
    userId: string;
    variantId: string;
    email: string | undefined;
    storeId: string;
}

/**
 * Create a LemonSqueezy hosted checkout URL.
 *
 * Returns the checkout URL to redirect the user to. The user_id is embedded
 * in custom_data so the webhook handler can attribute the subscription to the
 * correct Clerk user without relying on email matching.
 *
 * Docs: https://docs.lemonsqueezy.com/api/checkouts/create-checkout
 */
export async function createCheckout({
    userId,
    variantId,
    email,
    storeId,
}: CreateCheckoutParams): Promise<string> {
    const apiKey = getLSApiKey();
    const appUrl = process.env.NEXT_PUBLIC_APP_URL ?? "https://cap-alpha.co";

    const body = {
        data: {
            type: "checkouts",
            attributes: {
                checkout_options: {
                    embed: false,
                },
                checkout_data: {
                    email: email ?? undefined,
                    custom: {
                        user_id: userId,
                    },
                },
                product_options: {
                    redirect_url: `${appUrl}/dashboard?checkout=success`,
                },
            },
            relationships: {
                store: {
                    data: {
                        type: "stores",
                        id: storeId,
                    },
                },
                variant: {
                    data: {
                        type: "variants",
                        id: variantId,
                    },
                },
            },
        },
    };

    const res = await fetch("https://api.lemonsqueezy.com/v1/checkouts", {
        method: "POST",
        headers: {
            Authorization: `Bearer ${apiKey}`,
            Accept: "application/vnd.api+json",
            "Content-Type": "application/vnd.api+json",
        },
        body: JSON.stringify(body),
    });

    if (!res.ok) {
        const text = await res.text().catch(() => "(no body)");
        throw new Error(
            `[LemonSqueezy] createCheckout failed: HTTP ${res.status} — ${text}`
        );
    }

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const json = (await res.json()) as { data: { attributes: { url: string } } };
    const url = json?.data?.attributes?.url;

    if (!url) {
        throw new Error(
            "[LemonSqueezy] createCheckout: response did not include a checkout URL"
        );
    }

    return url;
}

// ---------------------------------------------------------------------------
// Webhook signature verification
// ---------------------------------------------------------------------------

/**
 * Verify the X-Signature header sent by LemonSqueezy.
 *
 * LemonSqueezy signs the raw request body with HMAC-SHA256 using the webhook
 * signing secret from the dashboard. We use timingSafeEqual to prevent
 * timing oracle attacks.
 *
 * Returns true if the signature is valid.
 */
export function verifyWebhookSignature(
    rawBody: string,
    signature: string,
    secret: string
): boolean {
    try {
        const expected = crypto
            .createHmac("sha256", secret)
            .update(rawBody, "utf8")
            .digest("hex");

        const expectedBuf = Buffer.from(expected, "hex");
        const receivedBuf = Buffer.from(signature, "hex");

        if (expectedBuf.length !== receivedBuf.length) return false;

        return crypto.timingSafeEqual(expectedBuf, receivedBuf);
    } catch {
        return false;
    }
}
