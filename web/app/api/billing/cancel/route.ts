/**
 * POST /api/billing/cancel
 *
 * Cancels the current user's active Stripe subscription immediately.
 *
 * The subscription is cancelled at the end of the current billing period
 * (`cancel_at_period_end: false` means immediate — access revoked now).
 * Use the Stripe Customer Portal (`/api/billing/portal`) if you want
 * "cancel at period end" behaviour with a grace period.
 *
 * After this call Stripe fires `customer.subscription.deleted`, which is
 * handled by `/api/webhooks/stripe` and downgrades the user to free in both
 * Postgres and Clerk publicMetadata.
 *
 * Requires: authenticated Clerk session.
 *
 * Issue: #486
 */

import { NextRequest, NextResponse } from 'next/server'
import { auth } from '@clerk/nextjs/server'
import { eq } from 'drizzle-orm'

import { db } from '@/db'
import { users } from '@/db/schema'
import { getStripe } from '@/lib/stripe'

export async function POST(_req: NextRequest) {
    const { userId } = auth()
    if (!userId) {
        return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    // Look up the user's subscription ID from Postgres
    const rows = await db
        .select({
            stripeSubscriptionId: users.stripeSubscriptionId,
            stripeSubscriptionStatus: users.stripeSubscriptionStatus,
        })
        .from(users)
        .where(eq(users.clerkId, userId))
        .limit(1)

    const user = rows[0]

    if (!user?.stripeSubscriptionId) {
        return NextResponse.json(
            { error: 'No active subscription found.' },
            { status: 404 }
        )
    }

    if (
        user.stripeSubscriptionStatus === 'canceled' ||
        user.stripeSubscriptionStatus === 'incomplete_expired'
    ) {
        return NextResponse.json(
            { error: 'Subscription is already canceled.' },
            { status: 409 }
        )
    }

    try {
        // Cancel immediately. Stripe will fire customer.subscription.deleted
        // which the webhook handler converts to isPro=false + tier=free.
        await getStripe().subscriptions.cancel(user.stripeSubscriptionId)
    } catch (err: unknown) {
        console.error('[billing/cancel] Stripe error:', err)
        const message =
            err instanceof Error ? err.message : 'Failed to cancel subscription.'
        return NextResponse.json({ error: message }, { status: 502 })
    }

    return NextResponse.json({ canceled: true }, { status: 200 })
}
