import { NextRequest } from 'next/server'
import { db } from '@/db'
import { users } from '@/db/schema'
import { eq } from 'drizzle-orm'
import { generateUnsubscribeToken } from '@/lib/email'

export async function GET(req: NextRequest) {
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
            headers: { 'Content-Type': 'text/html' },
        }
    )
}
