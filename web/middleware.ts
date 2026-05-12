import { NextResponse, type NextRequest } from "next/server";
import {
    checkIpRateLimit,
    checkLedgerIpRateLimit,
    checkBotIpRateLimit,
    buildRateLimitHeaders,
} from "@/lib/rate-limit";
import { isBotUserAgent, logBlockedRequest } from "@/lib/anti-scraping";

/**
 * /api/ledger/* prefixes are subject to the tighter 10 req/min ledger limit
 * (or 1 req/min for detected bots). All other public-data routes use the
 * broader 100 req/min anonymous limit.
 *
 * Issue: #884 (anti-scraping hardening)
 * Issue: #478 (original anonymous rate limit)
 */
const LEDGER_PREFIXES = ["/api/ledger/"];

const OTHER_RATE_LIMITED_PREFIXES = [
    "/api/draft/",
    "/api/search-index",
    "/api/misses",
    "/api/predictions",
    "/api/personalization",
];

function isLedgerRoute(pathname: string): boolean {
    return LEDGER_PREFIXES.some((prefix) => pathname.startsWith(prefix));
}

function isOtherRateLimited(pathname: string): boolean {
    return OTHER_RATE_LIMITED_PREFIXES.some((prefix) =>
        pathname.startsWith(prefix)
    );
}

function getClientIp(request: NextRequest): string {
    // Vercel sets x-real-ip; fall back to x-forwarded-for first element.
    const realIp = request.headers.get("x-real-ip");
    if (realIp) return realIp;

    const forwarded = request.headers.get("x-forwarded-for");
    if (forwarded) return forwarded.split(",")[0].trim();

    return "unknown";
}

export async function middleware(request: NextRequest) {
    const requestHeaders = new Headers(request.headers);
    requestHeaders.set("x-forwarded-proto", "https");

    const { pathname } = request.nextUrl;
    const ip = getClientIp(request);
    const userAgent = request.headers.get("user-agent") ?? "";
    const isBot = isBotUserAgent(userAgent);

    // ------------------------------------------------------------------
    // Ledger routes: tighter limits + bot fingerprinting
    // ------------------------------------------------------------------
    if (isLedgerRoute(pathname)) {
        let result;

        if (isBot) {
            // Bot traffic: 1 req/min
            result = await checkBotIpRateLimit(ip);
        } else {
            // Human traffic: 10 req/min on ledger endpoints
            result = await checkLedgerIpRateLimit(ip);
        }

        const rlHeaders = buildRateLimitHeaders(result);

        if (!result.success) {
            logBlockedRequest({
                timestamp: new Date().toISOString(),
                ip,
                user_agent: userAgent,
                endpoint: pathname,
                block_reason: isBot ? "bot_rate_limited" : "rate_limited",
            });

            return NextResponse.json(
                {
                    error: "Too many requests. Please slow down.",
                    retryAfter: result.retryAfter,
                },
                {
                    status: 429,
                    headers: {
                        ...rlHeaders,
                        "Content-Type": "application/json",
                    },
                }
            );
        }

        // Allowed — forward rate-limit headers so clients can self-throttle.
        const response = NextResponse.next({
            request: { headers: requestHeaders },
        });
        const rlHeadersRecord = rlHeaders as Record<string, string>;
        for (const [key, value] of Object.entries(rlHeadersRecord)) {
            response.headers.set(key, value);
        }
        return response;
    }

    // ------------------------------------------------------------------
    // Other public routes: standard 100 req/min anonymous limit
    // ------------------------------------------------------------------
    if (isOtherRateLimited(pathname)) {
        const result = await checkIpRateLimit(ip);
        const rlHeaders = buildRateLimitHeaders(result);

        if (!result.success) {
            return NextResponse.json(
                {
                    error: "Too many requests. Please slow down.",
                    retryAfter: result.retryAfter,
                },
                {
                    status: 429,
                    headers: {
                        ...rlHeaders,
                        "Content-Type": "application/json",
                    },
                }
            );
        }

        // Forward rate-limit headers on allowed responses so clients can self-throttle.
        const response = NextResponse.next({
            request: { headers: requestHeaders },
        });
        const rlHeadersRecord = rlHeaders as Record<string, string>;
        for (const [key, value] of Object.entries(rlHeadersRecord)) {
            response.headers.set(key, value);
        }
        return response;
    }

    return NextResponse.next({
        request: {
            headers: requestHeaders,
        },
    });
}

export const config = {
    matcher: ["/((?!.*\\..*|_next).*)", "/", "/(api|trpc)(.*)"],
};
