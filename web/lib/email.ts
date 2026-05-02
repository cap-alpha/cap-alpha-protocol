import { Resend } from 'resend'
import { createHmac } from 'crypto'

const resend = new Resend(process.env.RESEND_API_KEY)

export const FROM_ADDRESS = 'Cap Alpha <noreply@cap-alpha.co>'
export const REPLY_TO = 'support@cap-alpha.co'
export const BASE_URL = process.env.NEXT_PUBLIC_APP_URL ?? 'https://cap-alpha.co'

export function generateUnsubscribeToken(email: string): string {
    const secret = process.env.EMAIL_UNSUBSCRIBE_SECRET ?? 'changeme'
    return createHmac('sha256', secret).update(email).digest('hex')
}

export function unsubscribeUrl(email: string): string {
    const token = generateUnsubscribeToken(email)
    return `${BASE_URL}/api/emails/unsubscribe?email=${encodeURIComponent(email)}&token=${token}`
}

export async function sendWelcomeEmail(email: string, firstName?: string): Promise<void> {
    const { renderWelcomeEmail } = await import('./email-templates')
    await resend.emails.send({
        from: FROM_ADDRESS,
        replyTo: REPLY_TO,
        to: email,
        subject: 'Welcome to Cap Alpha — the NFL pundit scorecard',
        html: renderWelcomeEmail({ email, firstName }),
    })
}

export async function sendOnboardingDay3Email(email: string, firstName?: string): Promise<void> {
    const { renderDay3Email } = await import('./email-templates')
    await resend.emails.send({
        from: FROM_ADDRESS,
        replyTo: REPLY_TO,
        to: email,
        subject: 'Did you know we track 500+ NFL predictions?',
        html: renderDay3Email({ email, firstName }),
    })
}

export async function sendOnboardingDay7Email(email: string, firstName?: string): Promise<void> {
    const { renderDay7Email } = await import('./email-templates')
    await resend.emails.send({
        from: FROM_ADDRESS,
        replyTo: REPLY_TO,
        to: email,
        subject: 'Upgrade to Pro — see which pundits actually know football',
        html: renderDay7Email({ email, firstName }),
    })
}
