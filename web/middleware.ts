import { NextResponse, type NextRequest } from "next/server";
import { checkIpRateLimit, buildRateLimitHeaders } from "@/lib/rate-limit";

/**
 * Public API routes that are rate-limited per source IP.
 *
 * These routes return publicly readable data with no auth requirement.
 * Without rate limiting they could be scraped aggressively.
 *
 * Limit: 100 req/min per IP (same as free authenticated tier).
 * Fail-open when Upstash env vars are absent (dev / pre-provisioned envs).
 *
 * Issue: #478
 */
const PUBLIC_RATE_LIMITED_PREFIXES = [
    "/api/ledger/",
    "/api/draft/",
    "/api/search-index",
    "/api/misses",
    "/api/predictions",
    "/api/personalization",
];

function isPublicRateLimited(pathname: string): boolean {
    return PUBLIC_RATE_LIMITED_PREFIXES.some((prefix) =>
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

    if (isPublicRateLimited(pathname)) {
        const ip = getClientIp(request);
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
