/**
 * Anti-scraping utilities for the Pundit Prediction Ledger API.
 *
 * Implements:
 *  - Bot/crawler User-Agent fingerprinting
 *  - Honeypot field injection for API responses
 *  - Pagination enforcement (max 100 rows; HTTP 400 if limit > 100)
 *  - BigQuery logging of blocked requests for trend analysis
 *
 * Design principles:
 *  - Never block legitimate humans (Lighthouse, mobile on slow connections).
 *  - Fail-open for logging — a BQ write failure must not affect the response.
 *  - Environment-scoped: dev is lax (limits relaxed), production is strict.
 *
 * Issue: #884
 */

/** Maximum rows returned per page on any /api/ledger endpoint. */
export const LEDGER_MAX_LIMIT = 100;

/**
 * Well-known bot / scraper User-Agent substrings.
 * Case-insensitive match — see `isBotUserAgent`.
 *
 * Includes headless browsers, CLI download tools, and popular scraping
 * frameworks. Excludes Googlebot / Bingbot intentionally (legitimate crawlers
 * we never want to block on the public ledger).
 */
const BOT_UA_PATTERNS = [
    "curl",
    "wget",
    "python-requests",
    "python-httpx",
    "scrapy",
    "selenium",
    "puppeteer",
    "playwright",
    "phantomjs",
    "httpie",
    "java/",
    "okhttp",
    "axios",
    "node-fetch",
    "go-http-client",
    "libwww-perl",
    "lwp-trivial",
    "mechanize",
    "aiohttp",
    "httpunit",
];

/**
 * Returns true if the User-Agent string matches a known bot/scraper pattern.
 * In development, always returns false so local testing is unaffected.
 */
export function isBotUserAgent(userAgent: string | null): boolean {
    if (!userAgent) return false;
    if (process.env.NODE_ENV !== "production" && process.env.VERCEL_ENV !== "production") {
        return false;
    }
    const ua = userAgent.toLowerCase();
    return BOT_UA_PATTERNS.some((pattern) => ua.includes(pattern));
}

/**
 * Honeypot field names injected into every /api/ledger response.
 *
 * These fields look plausible but carry no real data. A scraper that
 * indexes or forwards them reveals itself (they can be matched against
 * downstream usage). They are NOT to be consumed by the frontend.
 */
const HONEYPOT_FIELD_NAMES = ["internal_id", "source_hash"] as const;

/** Generate stable but opaque honeypot values. */
function honeypotValue(field: string): string {
    // Simple deterministic hash to avoid leaking server state.
    // Scrapers that use these values as real data will get nonsense.
    const seed = `${field}:${Date.now().toString(36)}`;
    let hash = 0;
    for (let i = 0; i < seed.length; i++) {
        hash = (hash * 31 + seed.charCodeAt(i)) >>> 0;
    }
    return hash.toString(16).padStart(8, "0");
}

/**
 * Inject honeypot fields into the top-level API response object.
 * Returns a new object; does not mutate the original.
 */
export function injectHoneypotFields(
    response: Record<string, unknown>
): Record<string, unknown> {
    const honeypot: Record<string, string> = {};
    for (const field of HONEYPOT_FIELD_NAMES) {
        honeypot[field] = honeypotValue(field);
    }
    return { ...response, ...honeypot };
}

/**
 * Enforce pagination limits on incoming requests.
 *
 * @param rawLimit - The raw limit string from query params (may be undefined/null)
 * @param defaultLimit - Default limit when the param is absent
 * @returns { valid: true, limit } | { valid: false, error }
 */
export function enforcePaginationLimit(
    rawLimit: string | null | undefined,
    defaultLimit = 20
):
    | { valid: true; limit: number }
    | { valid: false; error: string } {
    if (rawLimit === null || rawLimit === undefined) {
        return { valid: true, limit: defaultLimit };
    }

    const parsed = parseInt(rawLimit, 10);
    if (!Number.isFinite(parsed) || parsed < 1) {
        return { valid: true, limit: defaultLimit };
    }

    if (parsed > LEDGER_MAX_LIMIT) {
        return {
            valid: false,
            error: `limit must be ≤ ${LEDGER_MAX_LIMIT}. Use page/cursor parameters for pagination.`,
        };
    }

    return { valid: true, limit: parsed };
}

/** Shape of a blocked-request log entry written to BigQuery. */
export interface BlockedRequestLog {
    timestamp: string;
    ip: string;
    user_agent: string;
    endpoint: string;
    block_reason: "rate_limited" | "bot_rate_limited" | "limit_exceeded";
}

/**
 * Log a blocked request to BigQuery for trend analysis.
 *
 * Fire-and-forget — failures are caught and console.error'd so they never
 * affect the response path. The BQ write goes through the FastAPI backend
 * (/v1/metrics/blocked-request) which is the only service with BQ credentials.
 *
 * In non-production environments the write is skipped entirely.
 */
export function logBlockedRequest(entry: BlockedRequestLog): void {
    // Skip in dev/preview — don't pollute metrics tables.
    if (
        process.env.NODE_ENV !== "production" &&
        process.env.VERCEL_ENV !== "production"
    ) {
        return;
    }

    const apiUrl =
        process.env.API_URL ||
        process.env.NEXT_PUBLIC_API_URL ||
        "https://pundit-ledger-api-wvhvx2muna-uc.a.run.app";

    // Fire-and-forget: do not await. Use void to suppress eslint.
    void fetch(`${apiUrl}/v1/metrics/blocked-request`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(entry),
    }).catch((err: unknown) => {
        const msg = err instanceof Error ? err.message : String(err);
        console.error("[anti-scraping] BQ log write failed:", msg);
    });
}
