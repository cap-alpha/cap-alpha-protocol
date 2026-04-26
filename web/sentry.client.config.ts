import * as Sentry from "@sentry/nextjs";

Sentry.init({
    dsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
    tracesSampleRate: 0.1,
    debug: false,
    beforeSend(event) {
        // Scrub Authorization header from all events
        if (event.request?.headers) {
            delete event.request.headers["authorization"];
            delete event.request.headers["Authorization"];
        }
        // Redact api_key from query strings
        if (event.request?.query_string && typeof event.request.query_string === "string") {
            event.request.query_string = event.request.query_string.replace(
                /api_key=[^&]*/g,
                "api_key=REDACTED"
            );
        }
        return event;
    },
});
