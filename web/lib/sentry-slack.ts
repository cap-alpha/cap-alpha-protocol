/**
 * Slack alerting helpers for operational incidents.
 *
 * All functions are fire-and-forget — they never throw and never block the
 * request that triggered the alert. Wire SLACK_WEBHOOK_URL in Vercel env vars.
 *
 * Alert rules configured here (code-level):
 *   - Stripe webhook exception → immediate Slack ping
 *   - Auth-bypass attempt on sensitive endpoint → immediate Slack ping
 *
 * Rate-based rules (5xx > 1% over 5 min) are configured in Sentry UI:
 *   Alerts → Create Alert → Issue Alert or Metric Alert on error rate.
 */

import * as Sentry from "@sentry/nextjs";

async function _post(text: string): Promise<void> {
    const url = process.env.SLACK_WEBHOOK_URL;
    if (!url) return;
    try {
        await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text }),
        });
    } catch {
        // Swallow — alerting must never break the main request path
    }
}

/**
 * Alert on an unhandled exception inside the Stripe webhook handler.
 * Posts immediately to Slack and captures in Sentry.
 */
export async function alertStripeWebhookException(
    err: unknown,
    stripeEventType: string
): Promise<void> {
    const message = err instanceof Error ? err.message : String(err);
    Sentry.captureException(err, {
        tags: { alert_type: "stripe_webhook_exception", stripe_event: stripeEventType },
    });
    await _post(
        `:rotating_light: *Stripe webhook exception*\n` +
        `Event: \`${stripeEventType}\`\n` +
        `Error: ${message}\n` +
        `Action: check Sentry for stack trace; verify webhook secret in Vercel env`
    );
}

/**
 * Alert on an auth-bypass attempt: a request that used an invalid/missing API
 * key to reach a sensitive (paid-tier) endpoint.
 */
export async function alertAuthBypass(endpoint: string, reason: string): Promise<void> {
    Sentry.captureMessage(`Auth-bypass attempt: ${endpoint}`, {
        level: "warning",
        tags: { alert_type: "auth_bypass" },
        extra: { endpoint, reason },
    });
    await _post(
        `:warning: *Auth-bypass attempt*\n` +
        `Endpoint: \`${endpoint}\`\n` +
        `Reason: ${reason}\n` +
        `Action: review API key validation logic if this recurs`
    );
}

/**
 * Generic operational alert. Use for one-off situations not covered above.
 */
export async function alertOps(text: string): Promise<void> {
    await _post(`:bell: ${text}`);
}
