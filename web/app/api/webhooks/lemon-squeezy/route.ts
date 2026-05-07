/**
 * POST /api/webhooks/lemon-squeezy
 *
 * Receives LemonSqueezy webhook events, verifies the signature, and keeps
 * subscription state in sync across:
 *   - Postgres users table (ls_* columns)
 *   - Clerk publicMetadata.tier (for fast tier reads by the rate limiter)
 *
 * Idempotency: composite keys (`${event_name}:${data.id}`) are stored in
 * ls_processed_events. A UNIQUE constraint prevents duplicate processing
 * even under concurrent delivery or adversarial replay.
 *
 * Return 200 for all handled events. Return 500 on errors so LemonSqueezy
 * retries the delivery.
 *
 * Required env vars:
 *   LEMONSQUEEZY_WEBHOOK_SECRET — from LS Dashboard → Webhooks → signing secret
 */

import { clerkClient } from "@clerk/nextjs/server";
import { eq } from "drizzle-orm";

import { db } from "@/db";
import { users, lsProcessedEvents } from "@/db/schema";
import { tierFromVariantId, verifyWebhookSignature } from "@/lib/lemon-squeezy";
import type { Tier } from "@/lib/api-keys/tiers";

// ---------------------------------------------------------------------------
// Webhook payload types
// ---------------------------------------------------------------------------

interface LSSubscriptionAttributes {
    status: string;
    variant_id: number;
    customer_id: number;
    user_email: string;
    renews_at: string | null;
    ends_at: string | null;
    cancelled: boolean;
}

interface LSWebhookPayload {
    meta: {
        event_name: string;
        custom_data?: {
            user_id?: string;
        };
    };
    data: {
        id: string;
        attributes: LSSubscriptionAttributes;
    };
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function setUserTier(clerkUserId: string, tier: Tier): Promise<void> {
    await clerkClient.users.updateUserMetadata(clerkUserId, {
        publicMetadata: { tier },
    });
}

// ---------------------------------------------------------------------------
// Event handlers
// ---------------------------------------------------------------------------

async function handleSubscriptionCreated(
    clerkUserId: string,
    data: LSWebhookPayload["data"]
): Promise<void> {
    const attrs = data.attributes;
    const tier = tierFromVariantId(attrs.variant_id);
    const periodEnd = attrs.renews_at ? new Date(attrs.renews_at) : null;

    await db
        .update(users)
        .set({
            lsCustomerId: String(attrs.customer_id),
            lsSubscriptionId: data.id,
            lsSubscriptionStatus: attrs.status,
            lsVariantId: String(attrs.variant_id),
            lsCurrentPeriodEnd: periodEnd,
            isPro: true,
        })
        .where(eq(users.clerkId, clerkUserId));

    await setUserTier(clerkUserId, tier);

    console.warn(
        `[LS Webhook] subscription_created: ${clerkUserId} → ${tier} (sub=${data.id})`
    );
}

async function handleSubscriptionUpdated(
    clerkUserId: string,
    data: LSWebhookPayload["data"]
): Promise<void> {
    const attrs = data.attributes;
    const tier = tierFromVariantId(attrs.variant_id);
    const periodEnd = attrs.renews_at ? new Date(attrs.renews_at) : null;
    const isActive = attrs.status === "active" || attrs.status === "on_trial";

    await db
        .update(users)
        .set({
            lsSubscriptionStatus: attrs.status,
            lsVariantId: String(attrs.variant_id),
            lsCurrentPeriodEnd: periodEnd,
            isPro: isActive,
        })
        .where(eq(users.clerkId, clerkUserId));

    await setUserTier(clerkUserId, isActive ? tier : "free");

    console.warn(
        `[LS Webhook] subscription_updated: ${clerkUserId} → ${tier} (status=${attrs.status})`
    );
}

async function handleSubscriptionCancelled(
    clerkUserId: string,
    data: LSWebhookPayload["data"]
): Promise<void> {
    // Mark cancelled but do NOT downgrade yet — subscriber retains access
    // until ends_at (grace period). subscription_expired fires after ends_at.
    const attrs = data.attributes;
    const endsAt = attrs.ends_at ? new Date(attrs.ends_at) : null;

    await db
        .update(users)
        .set({
            lsSubscriptionStatus: "cancelled",
            // Keep lsCurrentPeriodEnd pointing at ends_at so the app can
            // show "access until <date>" messaging.
            lsCurrentPeriodEnd: endsAt,
        })
        .where(eq(users.clerkId, clerkUserId));

    // Tier is NOT changed here — user keeps pro access until ends_at.
    console.warn(
        `[LS Webhook] subscription_cancelled: ${clerkUserId} — access until ${endsAt?.toISOString() ?? "unknown"}`
    );
}

async function handleSubscriptionExpired(
    clerkUserId: string,
    data: LSWebhookPayload["data"]
): Promise<void> {
    await db
        .update(users)
        .set({
            lsSubscriptionStatus: "expired",
            lsCurrentPeriodEnd: null,
            isPro: false,
        })
        .where(eq(users.clerkId, clerkUserId));

    await setUserTier(clerkUserId, "free");

    console.warn(
        `[LS Webhook] subscription_expired: ${clerkUserId} → free (sub=${data.id})`
    );
}

// ---------------------------------------------------------------------------
// Route handler
// ---------------------------------------------------------------------------

export async function POST(req: Request): Promise<Response> {
    const WEBHOOK_SECRET = process.env.LEMONSQUEEZY_WEBHOOK_SECRET;
    if (!WEBHOOK_SECRET) {
        console.error("[LS Webhook] LEMONSQUEEZY_WEBHOOK_SECRET not set");
        return new Response("Webhook secret not configured", { status: 500 });
    }

    // Read raw body before anything else — signature must be verified against
    // the exact bytes LemonSqueezy signed.
    const rawBody = await req.text();

    const signature = req.headers.get("x-signature");
    if (!signature) {
        return new Response("Missing x-signature header", { status: 400 });
    }

    if (!verifyWebhookSignature(rawBody, signature, WEBHOOK_SECRET)) {
        console.error("[LS Webhook] Signature verification failed");
        return new Response("Webhook signature verification failed", { status: 400 });
    }

    let payload: LSWebhookPayload;
    try {
        payload = JSON.parse(rawBody) as LSWebhookPayload;
    } catch {
        return new Response("Invalid JSON payload", { status: 400 });
    }

    const { meta, data } = payload;
    const eventName = meta.event_name;

    // Idempotency guard — composite key prevents duplicate processing under
    // concurrent delivery or adversarial replay.
    const idempotencyKey = `${eventName}:${data.id}`;
    try {
        const inserted = await db
            .insert(lsProcessedEvents)
            .values({ lsEventId: idempotencyKey, eventType: eventName })
            .onConflictDoNothing()
            .returning({ id: lsProcessedEvents.id });

        if (inserted.length === 0) {
            console.warn(`[LS Webhook] Duplicate event ignored: ${idempotencyKey}`);
            return new Response(null, { status: 200 });
        }
    } catch (err) {
        // Non-fatal during migration window — table may not exist yet.
        console.warn(
            "[LS Webhook] Idempotency check failed (table may not exist yet):",
            err
        );
    }

    // Extract Clerk user ID from custom_data set during checkout creation.
    const clerkUserId = meta.custom_data?.user_id;

    if (!clerkUserId && eventName !== "order_created") {
        console.error(
            `[LS Webhook] ${eventName}: missing custom_data.user_id — cannot attribute event`
        );
        // Return 200 to prevent infinite retries for unattributable events.
        return new Response(null, { status: 200 });
    }

    try {
        switch (eventName) {
            case "subscription_created":
                await handleSubscriptionCreated(clerkUserId!, data);
                break;

            case "subscription_updated":
                await handleSubscriptionUpdated(clerkUserId!, data);
                break;

            case "subscription_cancelled":
                await handleSubscriptionCancelled(clerkUserId!, data);
                break;

            case "subscription_expired":
                await handleSubscriptionExpired(clerkUserId!, data);
                break;

            case "order_created":
                // Order created fires alongside subscription_created for new subs.
                // Tier is already handled by subscription_created — log only.
                console.warn(
                    `[LS Webhook] order_created: data.id=${data.id} (no tier change — subscription_created handles it)`
                );
                break;

            default:
                // Acknowledge unhandled events so LS does not retry them.
                console.warn(`[LS Webhook] Unhandled event type: ${eventName}`);
                break;
        }
    } catch (err) {
        console.error(`[LS Webhook] Error handling ${eventName}:`, err);
        // Return 500 so LemonSqueezy retries the event.
        return new Response("Internal error processing webhook", { status: 500 });
    }

    return new Response(null, { status: 200 });
}
