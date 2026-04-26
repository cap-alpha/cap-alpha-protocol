import * as Sentry from "@sentry/nextjs";

Sentry.init({
    dsn: process.env.SENTRY_DSN || process.env.NEXT_PUBLIC_SENTRY_DSN,
    tracesSampleRate: 0.1,
    debug: false,
    beforeSend(event) {
        if (event.request?.headers) {
            delete event.request.headers["authorization"];
            delete event.request.headers["Authorization"];
            delete event.request.headers["x-api-key"];
        }
        return event;
    },
});
