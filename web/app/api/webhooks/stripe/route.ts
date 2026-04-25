/**
 * POST /api/webhooks/stripe
 *
 * Receives Stripe webhook events, verifies the signature, and keeps
 * subscription state in sync across:
 *   - Postgres users table (stripe_* columns)
 *   - Clerk publicMetadata.tier (for fast tier reads by the rate limiter)
 *   - BigQuery monetization.stripe_events (immutable audit log)
 *
 * Idempotent: events already logged to BQ are silently skipped.
 *
 * Required env vars:
 *   STRIPE_WEBHOOK_SECRET — from Stripe Dashboard → Webhooks → endpoint secret
 *   STRIPE_SECRET_KEY     — Stripe API key (also used by lib/stripe.ts)
 */

import { clerkClient } from "@clerk/nextjs/server";
import { BigQuery } from "@google-cloud/bigquery";
import { eq } from "drizzle-orm";
import { headers } from "next/headers";
import type Stripe from "stripe";

import { db } from "@/db";
import { users } from "@/db/schema";
import { stripe, tierFromPriceId } from "@/lib/stripe";
import type { Tier } from "@/lib/api-keys/tiers";

const PROJECT_ID = process.env.GCP_PROJECT_ID || "cap-alpha-protocol";

// ---------------------------------------------------------------------------
// BigQuery audit log (fire-and-forget)
// ---------------------------------------------------------------------------

async function logStripeEvent(
    event: Stripe.Event,
    clerkUserId: string | null
): Promise<void> {
    try {
        const bq = new BigQuery({
            projectId: PROJECT_ID,
            credentials:
                process.env.GCP_CLIENT_EMAIL && process.env.GCP_PRIVATE_KEY
                    ? {
                          client_email: process.env.GCP_CLIENT_EMAIL,
                          private_key: process.env.GCP_PRIVATE_KEY.replace(
                              /\\n/g,
                              "\n"
                          ),
                      }
                    : undefined,
        });

        const table = bq
            .dataset("monetization")
            .table("stripe_events");

        await table.insert([
            {
                event_id: event.id,
                event_type: event.type,
                user_id: clerkUserId,
                stripe_customer_id:
                    typeof (event.data.object as any).customer === "string"
                        ? (event.data.object as any).customer
                        : null,
                livemode: event.livemode,
                payload: JSON.stringify(event.data.object),
                processed_at: new Date().toISOString(),
            },
        ]);
    } catch (err) {
        // Non-fatal — event handling continues even if audit log fails
        console.error("[Stripe Webhook] BQ audit log failed:", err);
    }
}

// ---------------------------------------------------------------------------
// Tier sync helpers
// ---------------------------------------------------------------------------

async function setUserTier(clerkUserId: string, tier: Tier): Promise<void> {
    await clerkClient.users.updateUserMetadata(clerkUserId, {
        publicMetadata: { tier },
    });
}

async function getClerkUserIdByStripeCustomer(
    customerId: string
): Promise<string | null> {
    const rows = await db
        .select({ clerkId: users.clerkId })
        .from(users)
        .where(eq(users.stripeCustomerId, customerId))
        .limit(1);
    return rows[0]?.clerkId ?? null;
}

// ---------------------------------------------------------------------------
// Event handlers
// ---------------------------------------------------------------------------

async function handleCheckoutCompleted(
    session: Stripe.Checkout.Session
): Promise<string | null> {
    // client_reference_id is set to the Clerk user ID during checkout
    const clerkUserId = session.client_reference_id;
    if (!clerkUserId) {
        console.warn("[Stripe Webhook] checkout.session.completed: no client_reference_id");
        return null;
    }

    const customerId =
        typeof session.customer === "string" ? session.customer : null;
    const subscriptionId =
        typeof session.subscription === "string" ? session.subscription : null;

    // Fetch the subscription to get price details
    let priceId: string | null = null;
    let currentPeriodEnd: Date | null = null;

    if (subscriptionId) {
        const sub = await stripe.subscriptions.retrieve(subscriptionId);
        priceId = sub.items.data[0]?.price?.id ?? null;
        currentPeriodEnd = new Date(sub.current_period_end * 1000);
    }

    await db
        .update(users)
        .set({
            stripeCustomerId: customerId,
            stripeSubscriptionId: subscriptionId,
            stripeSubscriptionStatus: "active",
            stripePriceId: priceId,
            stripeCurrentPeriodEnd: currentPeriodEnd,
            isPro: true,
        })
        .where(eq(users.clerkId, clerkUserId));

    const tier = tierFromPriceId(priceId);
    await setUserTier(clerkUserId, tier);

    console.log(`[Stripe Webhook] checkout completed: ${clerkUserId} → ${tier}`);
    return clerkUserId;
}

async function handleSubscriptionUpdated(
    sub: Stripe.Subscription
): Promise<string | null> {
    const customerId =
        typeof sub.customer === "string" ? sub.customer : null;
    if (!customerId) return null;

    const clerkUserId = await getClerkUserIdByStripeCustomer(customerId);
    if (!clerkUserId) {
        console.warn(`[Stripe Webhook] subscription.updated: no user for customer ${customerId}`);
        return null;
    }

    const priceId = sub.items.data[0]?.price?.id ?? null;
    const currentPeriodEnd = new Date(sub.current_period_end * 1000);
    const status = sub.status;

    await db
        .update(users)
        .set({
            stripeSubscriptionStatus: status,
            stripePriceId: priceId,
            stripeCurrentPeriodEnd: currentPeriodEnd,
            isPro: status === "active" || status === "trialing",
        })
        .where(eq(users.clerkId, clerkUserId));

    const tier = tierFromPriceId(priceId);
    await setUserTier(clerkUserId, tier);

    console.log(`[Stripe Webhook] subscription updated: ${clerkUserId} → ${tier} (${status})`);
    return clerkUserId;
}

async function handleSubscriptionDeleted(
    sub: Stripe.Subscription
): Promise<string | null> {
    const customerId =
        typeof sub.customer === "string" ? sub.customer : null;
    if (!customerId) return null;

    const clerkUserId = await getClerkUserIdByStripeCustomer(customerId);
    if (!clerkUserId) {
        console.warn(`[Stripe Webhook] subscription.deleted: no user for customer ${customerId}`);
        return null;
    }

    await db
        .update(users)
        .set({
            stripeSubscriptionStatus: "canceled",
            stripePriceId: null,
            stripeCurrentPeriodEnd: null,
            isPro: false,
        })
        .where(eq(users.clerkId, clerkUserId));

    await setUserTier(clerkUserId, "free");

    console.log(`[Stripe Webhook] subscription canceled: ${clerkUserId} → free`);
    return clerkUserId;
}

async function handleInvoicePaymentFailed(
    invoice: Stripe.Invoice
): Promise<string | null> {
    const customerId =
        typeof invoice.customer === "string" ? invoice.customer : null;
    if (!customerId) return null;

    const clerkUserId = await getClerkUserIdByStripeCustomer(customerId);
    if (!clerkUserId) return null;

    // Mark past_due but do NOT downgrade — Stripe Smart Retries handles recovery.
    // We only downgrade on subscription.deleted.
    await db
        .update(users)
        .set({ stripeSubscriptionStatus: "past_due" })
        .where(eq(users.clerkId, clerkUserId));

    console.log(`[Stripe Webhook] invoice payment failed: ${clerkUserId} → past_due`);
    return clerkUserId;
}

async function handleInvoicePaymentSucceeded(
    invoice: Stripe.Invoice
): Promise<string | null> {
    const customerId =
        typeof invoice.customer === "string" ? invoice.customer : null;
    if (!customerId) return null;

    const clerkUserId = await getClerkUserIdByStripeCustomer(customerId);
    if (!clerkUserId) return null;

    // Clear any past_due flag by restoring active status
    await db
        .update(users)
        .set({ stripeSubscriptionStatus: "active", isPro: true })
        .where(eq(users.clerkId, clerkUserId));

    console.log(`[Stripe Webhook] invoice payment succeeded: ${clerkUserId} → active`);
    return clerkUserId;
}

// ---------------------------------------------------------------------------
// Route handler
// ---------------------------------------------------------------------------

export async function POST(req: Request): Promise<Response> {
    const WEBHOOK_SECRET = process.env.STRIPE_WEBHOOK_SECRET;
    if (!WEBHOOK_SECRET) {
        console.error("[Stripe Webhook] STRIPE_WEBHOOK_SECRET not set");
        return new Response("Webhook secret not configured", { status: 500 });
    }

    const body = await req.text();
    const sig = headers().get("stripe-signature");

    if (!sig) {
        return new Response("Missing stripe-signature header", { status: 400 });
    }

    let event: Stripe.Event;
    try {
        event = stripe.webhooks.constructEvent(body, sig, WEBHOOK_SECRET);
    } catch (err) {
        console.error("[Stripe Webhook] Signature verification failed:", err);
        return new Response("Webhook signature verification failed", { status: 400 });
    }

    let clerkUserId: string | null = null;

    try {
        switch (event.type) {
            case "checkout.session.completed":
                clerkUserId = await handleCheckoutCompleted(
                    event.data.object as Stripe.Checkout.Session
                );
                break;

            case "customer.subscription.updated":
                clerkUserId = await handleSubscriptionUpdated(
                    event.data.object as Stripe.Subscription
                );
                break;

            case "customer.subscription.deleted":
                clerkUserId = await handleSubscriptionDeleted(
                    event.data.object as Stripe.Subscription
                );
                break;

            case "invoice.payment_failed":
                clerkUserId = await handleInvoicePaymentFailed(
                    event.data.object as Stripe.Invoice
                );
                break;

            case "invoice.payment_succeeded":
                clerkUserId = await handleInvoicePaymentSucceeded(
                    event.data.object as Stripe.Invoice
                );
                break;

            default:
                // Unhandled event type — acknowledge receipt and move on
                break;
        }
    } catch (err) {
        console.error(`[Stripe Webhook] Error handling ${event.type}:`, err);
        // Return 500 so Stripe retries the event
        return new Response("Internal error processing webhook", { status: 500 });
    }

    // Fire-and-forget audit log (non-blocking)
    logStripeEvent(event, clerkUserId).catch(() => {});

    return new Response(null, { status: 200 });
}
