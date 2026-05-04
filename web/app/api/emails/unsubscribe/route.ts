import { NextRequest } from 'next/server'
import { db } from '@/db'
import { users } from '@/db/schema'
import { eq } from 'drizzle-orm'
import { generateUnsubscribeToken } from '@/lib/email'
import { checkIpRateLimit, buildRateLimitHeaders } from '@/lib/rate-limit'

/**
 * GET /api/emails/unsubscribe
 *
 * Handles one-click email unsubscribe via HMAC-signed token in link.
 *
 * Security notes:
 *  - Returns 200 regardless of whether the email exists in DB (DB update is
 *    a no-op for unknown addresses) so email presence is never confirmed.
 *  - Returns 403 on invalid token. Because the token check happens before any
 *    DB query, an attacker cannot distinguish valid-email/wrong-token from
 *    invalid-email/any-token — both return the same 403 without touching the DB.
 *  - IP rate-limited (100 req/min shared with public API limiter) to prevent
 *    token brute-force and high-volume enumeration attempts.
 *
 * Issue: #497
 */

function getClientIp(request: NextRequest): string {
    const realIp = request.headers.get('x-real-ip')
    if (realIp) return realIp

    const forwarded = request.headers.get('x-forwarded-for')
    if (forwarded) return forwarded.split(',')[0].trim()

    return 'unknown'
}

export async function GET(req: NextRequest) {
    // IP rate limit — fail-open when Upstash not configured (dev / pre-provisioned)
    const ip = getClientIp(req)
    const rl = await checkIpRateLimit(ip)
    const rlHeaders = buildRateLimitHeaders(rl) as Record<string, string>

    if (!rl.success) {
        return new Response('Too many requests. Please slow down.', {
            status: 429,
            headers: {
                ...rlHeaders,
                'Content-Type': 'text/plain',
            },
        })
    }

    const { searchParams } = req.nextUrl
    const email = searchParams.get('email')
    const token = searchParams.get('token')

    if (!email || !token) {
        return new Response('Missing email or token', { status: 400 })
    }

    const expected = generateUnsubscribeToken(email)
    if (token !== expected) {
        return new Response('Invalid unsubscribe token', { status: 403 })
    }

    try {
        await db
            .update(users)
            .set({ emailUnsubscribedAt: new Date() })
            .where(eq(users.email, email))
        // rowsAffected is intentionally not checked — always 200 so callers
        // cannot determine whether this email address is in the database.
    } catch (e) {
        console.error('Unsubscribe DB error:', e)
        return new Response('Server error', { status: 500 })
    }

    return new Response(
        `<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Unsubscribed</title></head>
<body style="font-family:sans-serif;max-width:480px;margin:80px auto;text-align:center;color:#333;">
  <h1 style="font-size:24px;">You've been unsubscribed.</h1>
  <p style="color:#666;">You won't receive any more onboarding emails from Cap Alpha.</p>
  <p style="color:#666;font-size:14px;">Transactional emails (receipts, API keys) may still be sent as required.</p>
  <a href="https://cap-alpha.co" style="color:#2563eb;">Return to Cap Alpha</a>
</body></html>`,
        {
            status: 200,
            headers: {
                'Content-Type': 'text/html',
                ...rlHeaders,
            },
        }
    )
}
