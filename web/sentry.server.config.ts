import * as Sentry from "@sentry/nextjs";

Sentry.init({
    dsn: process.env.SENTRY_DSN || process.env.NEXT_PUBLIC_SENTRY_DSN,
    tracesSampleRate: 0.1,
    debug: false,
    beforeSend(event) {
        // Scrub Authorization header — never log API keys or Bearer tokens
        if (event.request?.headers) {
            delete event.request.headers["authorization"];
            delete event.request.headers["Authorization"];
            delete event.request.headers["x-api-key"];
        }
        // Redact api_key query param
        if (event.request?.query_string && typeof event.request.query_string === "string") {
            event.request.query_string = event.request.query_string.replace(
                /api_key=[^&]*/g,
                "api_key=REDACTED"
            );
        }
        // Drop Stripe webhook payload bodies entirely — they contain card/PII data
        if (event.request?.url?.includes("/api/webhooks/stripe")) {
            if (event.request.data) {
                event.request.data = "[STRIPE WEBHOOK — REDACTED]";
            }
        }
        return event;
    },
});
