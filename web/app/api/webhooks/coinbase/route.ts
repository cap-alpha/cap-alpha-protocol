/**
 * POST /api/webhooks/coinbase — Coinbase Commerce webhook handler (#121)
 *
 * Receives Coinbase Commerce charge events, verifies the HMAC-SHA256 signature,
 * and keeps subscription state in sync across:
 *   - Postgres users table (isPro + stripeCurrentPeriodEnd reused as period end)
 *   - Clerk publicMetadata.tier (for fast tier reads by the rate limiter)
 *
 * USDC enforcement: payments that are not USDC are logged and skipped — Pro is
 * not granted for any other currency.
 *
 * Idempotency: Coinbase event IDs are stored in coinbase_processed_charges. A
 * UNIQUE constraint prevents duplicate processing under concurrent delivery.
 *
 * Required env vars:
 *   COINBASE_COMMERCE_WEBHOOK_SECRET — from Coinbase Commerce Dashboard → Webhooks
 *   COINBASE_COMMERCE_API_KEY        — from Coinbase Commerce Dashboard → API keys
 */

import { clerkClient } from "@clerk/nextjs/server";
import { eq } from "drizzle-orm";

import { db } from "@/db";
import { users, coinbaseProcessedCharges } from "@/db/schema";
import { verifyWebhookSignature } from "@/lib/coinbase-commerce";
import type { Tier } from "@/lib/api-keys/tiers";

// 31 days — slightly over a month so monthly renewals don't lapse on billing day
const PRO_DURATION_MS = 31 * 24 * 60 * 60 * 1000;

async function setUserTier(clerkUserId: string, tier: Tier): Promise<void> {
    await clerkClient.users.updateUserMetadata(clerkUserId, {
        publicMetadata: { tier },
    });
}

interface CoinbasePayment {
    value?: { crypto?: { currency?: string } };
}

interface CoinbaseEvent {
    id: string;
    type: string;
    data: {
        id: string;
        code: string;
        metadata?: Record<string, string>;
        payments?: CoinbasePayment[];
    };
}

export async function POST(req: Request): Promise<Response> {
    const secret = process.env.COINBASE_COMMERCE_WEBHOOK_SECRET;
    if (!secret) {
        console.error("[Coinbase Webhook] COINBASE_COMMERCE_WEBHOOK_SECRET not set");
        return new Response("Webhook secret not configured", { status: 500 });
    }

    const rawBody = await req.text();
    const signature = req.headers.get("x-cc-webhook-signature") ?? "";

    if (!verifyWebhookSignature(rawBody, signature, secret)) {
        console.error("[Coinbase Webhook] Signature verification failed");
        return new Response("Invalid signature", { status: 400 });
    }

    let event: CoinbaseEvent;
    try {
        event = JSON.parse(rawBody) as CoinbaseEvent;
    } catch {
        return new Response("Invalid JSON body", { status: 400 });
    }

    // Idempotency guard — deduplicate by Coinbase event ID
    try {
        const inserted = await db
            .insert(coinbaseProcessedCharges)
            .values({ coinbaseEventId: event.id, eventType: event.type })
            .onConflictDoNothing()
            .returning({ id: coinbaseProcessedCharges.id });
        if (inserted.length === 0) {
            console.log(`[Coinbase Webhook] Duplicate event ignored: ${event.id}`);
            return new Response(null, { status: 200 });
        }
    } catch (err) {
        // If the idempotency table doesn't exist yet (migration pending), log and continue
        console.warn("[Coinbase Webhook] Idempotency check failed (table may not exist yet):", err);
    }

    const clerkUserId = event.data.metadata?.userId;
    if (!clerkUserId) {
        console.warn(`[Coinbase Webhook] No userId in metadata for event ${event.id} (type=${event.type})`);
        return new Response(null, { status: 200 });
    }

    try {
        switch (event.type) {
            case "charge:confirmed":
            case "charge:resolved": {
                // USDC-only enforcement
                const payments = event.data.payments ?? [];
                if (payments.length > 0) {
                    const currency = payments[0]?.value?.crypto?.currency;
                    if (currency && currency !== "USDC") {
                        console.warn(
                            `[Coinbase Webhook] Non-USDC payment currency="${currency}" for user ${clerkUserId} — Pro not granted`
                        );
                        return new Response(null, { status: 200 });
                    }
                }

                const proExpiresAt = new Date(Date.now() + PRO_DURATION_MS);
                await db
                    .update(users)
                    .set({ isPro: true, stripeCurrentPeriodEnd: proExpiresAt })
                    .where(eq(users.clerkId, clerkUserId));
                await setUserTier(clerkUserId, "pro");
                console.log(
                    `[Coinbase Webhook] Pro granted: ${clerkUserId}, expires ${proExpiresAt.toISOString()}`
                );
                break;
            }

            case "charge:failed":
            case "charge:expired":
            case "charge:canceled": {
                await db
                    .update(users)
                    .set({ isPro: false })
                    .where(eq(users.clerkId, clerkUserId));
                await setUserTier(clerkUserId, "free");
                console.log(`[Coinbase Webhook] Pro revoked: ${clerkUserId} (${event.type})`);
                break;
            }

            default:
                // charge:created, charge:pending — no tier action needed
                break;
        }
    } catch (err) {
        console.error(`[Coinbase Webhook] Error handling ${event.type}:`, err);
        return new Response("Internal error processing webhook", { status: 500 });
    }

    return new Response(null, { status: 200 });
}
