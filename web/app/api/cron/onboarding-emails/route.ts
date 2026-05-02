import { NextRequest } from 'next/server'
import { db } from '@/db'
import { users } from '@/db/schema'
import { and, eq, isNull, lte, gte, sql } from 'drizzle-orm'
import { sendOnboardingDay3Email, sendOnboardingDay7Email } from '@/lib/email'

// Vercel cron calls this endpoint. Secured by CRON_SECRET.
export async function GET(req: NextRequest) {
    const authHeader = req.headers.get('authorization')
    if (authHeader !== `Bearer ${process.env.CRON_SECRET}`) {
        return new Response('Unauthorized', { status: 401 })
    }

    const now = new Date()
    const day3Threshold = new Date(now.getTime() - 3 * 24 * 60 * 60 * 1000)
    const day7Threshold = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000)

    let day3Sent = 0
    let day7Sent = 0

    // Day 3: welcome sent (step=1), signed up ≥3 days ago, not unsubscribed
    const day3Candidates = await db
        .select({ email: users.email, clerkId: users.clerkId })
        .from(users)
        .where(
            and(
                eq(users.onboardingStep, 1),
                isNull(users.emailUnsubscribedAt),
                lte(users.createdAt, day3Threshold),
            )
        )

    for (const user of day3Candidates) {
        try {
            await sendOnboardingDay3Email(user.email)
            await db
                .update(users)
                .set({ onboardingStep: 2 })
                .where(eq(users.clerkId, user.clerkId))
            day3Sent++
        } catch (e) {
            console.error(`Day-3 email failed for ${user.email}:`, e)
        }
    }

    // Day 7: day-3 sent (step=2), signed up ≥7 days ago, not unsubscribed
    const day7Candidates = await db
        .select({ email: users.email, clerkId: users.clerkId })
        .from(users)
        .where(
            and(
                eq(users.onboardingStep, 2),
                isNull(users.emailUnsubscribedAt),
                lte(users.createdAt, day7Threshold),
            )
        )

    for (const user of day7Candidates) {
        try {
            await sendOnboardingDay7Email(user.email)
            await db
                .update(users)
                .set({ onboardingStep: 3 })
                .where(eq(users.clerkId, user.clerkId))
            day7Sent++
        } catch (e) {
            console.error(`Day-7 email failed for ${user.email}:`, e)
        }
    }

    console.log(`Onboarding cron: day3=${day3Sent} day7=${day7Sent}`)
    return Response.json({ ok: true, day3Sent, day7Sent })
}
