import { NextRequest } from 'next/server'
import { clerkClient } from '@clerk/nextjs/server'
import { db } from '@/db'
import { users } from '@/db/schema'
import { isNull, not, sql } from 'drizzle-orm'
import { sendResolutionAlertEmail } from '@/lib/email'
import type { ResolvedPrediction } from '@/lib/email-templates'

// Vercel cron calls this endpoint nightly at 09:00 UTC — 1h after resolve_daily.py
// finishes (08:00 UTC). Secured by CRON_SECRET bearer token (same pattern as
// onboarding-emails/route.ts).
//
// Algorithm:
// 1. Fetch all users with followed_pundits non-empty (via Clerk user listing).
// 2. For each user, query the pundit API for predictions resolved in the last 24h
//    matching their followed pundit IDs.
// 3. Bundle into a single email per user; send via Resend.
// 4. Skip users who have digest_unsubscribed_at set.
//
// Max latency on resolution notification: 24h. Acceptable for NFL cadence where
// resolutions cluster post-Sunday-games. Real-time push is Phase 2.

const API_URL =
    process.env.API_URL ||
    process.env.NEXT_PUBLIC_API_URL ||
    'https://pundit-ledger-api-wvhvx2muna-uc.a.run.app'

interface ApiPrediction {
    prediction_hash: string
    extracted_claim: string | null
    raw_assertion_text: string | null
    resolution_status: string
    resolved_at: string | null
    claim_category: string
}

interface ApiPredictionsResponse {
    predictions: ApiPrediction[]
    total: number
}

async function fetchRecentResolutions(punditId: string, since: Date): Promise<ResolvedPrediction[]> {
    try {
        // Fetch up to 20 most recent predictions and filter client-side for those
        // resolved after `since`. The API doesn't yet support a resolved_since param.
        const res = await fetch(
            `${API_URL}/v1/pundits/${encodeURIComponent(punditId)}/predictions?page=1&page_size=50&status=CORRECT`,
            { headers: { Accept: 'application/json' }, signal: AbortSignal.timeout(8000) }
        )
        if (!res.ok) return []
        const correct: ApiPredictionsResponse = await res.json()

        const incorrectRes = await fetch(
            `${API_URL}/v1/pundits/${encodeURIComponent(punditId)}/predictions?page=1&page_size=50&status=INCORRECT`,
            { headers: { Accept: 'application/json' }, signal: AbortSignal.timeout(8000) }
        )
        const incorrect: ApiPredictionsResponse = incorrectRes.ok ? await incorrectRes.json() : { predictions: [] }

        const all = [...correct.predictions, ...incorrect.predictions]
        const sinceMs = since.getTime()

        return all
            .filter((p) => {
                if (!p.resolved_at) return false
                return new Date(p.resolved_at).getTime() >= sinceMs
            })
            .map((p) => ({
                pundit_id: punditId,
                pundit_name: '', // filled by caller
                claim_text: p.extracted_claim || p.raw_assertion_text || '(no claim text)',
                outcome: p.resolution_status as 'CORRECT' | 'INCORRECT',
                resolved_at: p.resolved_at,
                category: p.claim_category,
                prediction_hash: p.prediction_hash,
            }))
    } catch (err) {
        console.error(`[resolution-notifications] fetchRecentResolutions error for ${punditId}:`, err)
        return []
    }
}

async function getPunditName(punditId: string): Promise<string> {
    try {
        const res = await fetch(
            `${API_URL}/v1/pundits/${encodeURIComponent(punditId)}`,
            { headers: { Accept: 'application/json' }, signal: AbortSignal.timeout(5000) }
        )
        if (!res.ok) return punditId
        const data = await res.json()
        return (data.pundit?.pundit_name as string | undefined) ?? punditId
    } catch {
        return punditId
    }
}

export async function GET(req: NextRequest) {
    // Authz — Bearer CRON_SECRET
    const authHeader = req.headers.get('authorization')
    if (authHeader !== `Bearer ${process.env.CRON_SECRET}`) {
        return new Response('Unauthorized', { status: 401 })
    }

    const since = new Date(Date.now() - 24 * 60 * 60 * 1000) // last 24h
    let emailsSent = 0
    let usersProcessed = 0
    let usersSkipped = 0

    try {
        // 1. Fetch all users who have NOT unsubscribed from digests and have
        //    a non-null emailUnsubscribedAt guard as well.
        //    We can't filter on Clerk metadata in DB, so fetch all non-unsubscribed
        //    users from Postgres, then check Clerk metadata per user.
        const dbUsers = await db
            .select({ email: users.email, clerkId: users.clerkId })
            .from(users)
            .where(
                isNull(users.digestUnsubscribedAt)
            )

        for (const dbUser of dbUsers) {
            try {
                const clerkUser = await clerkClient.users.getUser(dbUser.clerkId)
                const followedIds: string[] =
                    (clerkUser.publicMetadata.followed_pundits as string[] | undefined) ?? []

                if (followedIds.length === 0) {
                    usersSkipped++
                    continue
                }

                usersProcessed++

                // Fetch resolutions for each followed pundit in parallel
                // (capped at 10 concurrent to avoid API hammering)
                const chunks: string[][] = []
                for (let i = 0; i < followedIds.length; i += 10) {
                    chunks.push(followedIds.slice(i, i + 10))
                }

                const allResolutions: ResolvedPrediction[] = []
                for (const chunk of chunks) {
                    const results = await Promise.all(
                        chunk.map(async (id) => {
                            const resolutions = await fetchRecentResolutions(id, since)
                            if (resolutions.length === 0) return resolutions
                            // Fetch pundit name for email display
                            const name = await getPunditName(id)
                            return resolutions.map((r) => ({ ...r, pundit_name: name }))
                        })
                    )
                    allResolutions.push(...results.flat())
                }

                if (allResolutions.length === 0) {
                    usersSkipped++
                    continue
                }

                // Send bundled email — one per user, not per resolution
                const firstName = clerkUser.firstName ?? undefined
                await sendResolutionAlertEmail(dbUser.email, allResolutions, firstName)
                emailsSent++

                console.log(
                    `[resolution-notifications] sent to ${dbUser.email} — ${allResolutions.length} resolutions`
                )
            } catch (err) {
                console.error(`[resolution-notifications] failed for ${dbUser.email}:`, err)
            }
        }
    } catch (err) {
        console.error('[resolution-notifications] fatal error:', err)
        return Response.json({ ok: false, error: String(err) }, { status: 500 })
    }

    console.log(
        `[resolution-notifications] done: emailsSent=${emailsSent} usersProcessed=${usersProcessed} usersSkipped=${usersSkipped}`
    )
    return Response.json({ ok: true, emailsSent, usersProcessed, usersSkipped })
}
