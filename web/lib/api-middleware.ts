/**
 * Reusable API middleware for authenticated, rate-limited routes.
 *
 * Wraps a Next.js route handler with:
 *   1. API key extraction from `Authorization: Bearer capk_...`
 *   2. Key verification (Redis cache -> BigQuery fallback)
 *   3. Tier resolution (Redis-cached)
 *   4. Rate limiting (Upstash sliding window)
 *   5. Standard rate-limit response headers
 */
import { NextRequest, NextResponse } from "next/server";
import { hashApiKey } from "./api-keys/index";
import { verifyKey } from "./api-keys/repository";
import { getCachedTier } from "./tier-cache";
import { checkRateLimit } from "./rate-limiter";
import { redis } from "./redis";

/** Shape of the verified request context passed to the inner handler. */
export interface ApiContext {
    userId: string;
    keyId: string;
    tier: string;
}

/** Inner handler signature. */
export type ApiHandler = (
    req: NextRequest,
    ctx: ApiContext
) => Promise<NextResponse>;

/**
 * Redis-cached key verification.
 *
 * On cache hit we return the cached result (avoiding BigQuery).
 * On cache miss we call verifyKey() against BigQuery and cache the result.
 *
 * Cache key format: `apikey:{hash}` with a 10-minute TTL.
 */
async function verifyKeyWithCache(
    plaintextKey: string
): Promise<{ keyId: string; userId: string; status: string } | null> {
    const { hash } = hashApiKey(plaintextKey);
    const cacheKey = `apikey:${hash}`;

    // Try Redis cache first
    if (redis) {
        try {
            const cached = await redis.get<string>(cacheKey);
            if (cached) {
                const parsed = JSON.parse(cached);
                return parsed;
            }
        } catch (error) {
            console.warn("[api-middleware] Redis cache read error, falling back to BigQuery:", error);
        }
    }

    // Cache miss or Redis unavailable -- fall back to BigQuery
    const result = await verifyKey(plaintextKey);

    // Cache the result (even null to prevent repeated BigQuery lookups for invalid keys)
    if (redis && result) {
        try {
            await redis.set(cacheKey, JSON.stringify(result), { ex: 600 }); // 10 min TTL
        } catch (error) {
            console.warn("[api-middleware] Redis cache write error:", error);
        }
    }

    return result;
}

/**
 * Extract the Bearer token from the Authorization header.
 *
 * Expects format: `Authorization: Bearer capk_...`
 */
function extractApiKey(req: NextRequest): string | null {
    const authHeader = req.headers.get("authorization");
    if (!authHeader) return null;

    const parts = authHeader.split(" ");
    if (parts.length !== 2 || parts[0] !== "Bearer") return null;

    const token = parts[1];
    if (!token.startsWith("capk_")) return null;

    return token;
}

/**
 * Wrap a route handler with API authentication and rate limiting.
 *
 * Usage:
 * ```ts
 * export const GET = withApiAuth(async (req, ctx) => {
 *     return NextResponse.json({ status: "ok", tier: ctx.tier });
 * });
 * ```
 */
export function withApiAuth(handler: ApiHandler) {
    return async (req: NextRequest): Promise<NextResponse> => {
        // 1. Extract API key
        const apiKey = extractApiKey(req);
        if (!apiKey) {
            return NextResponse.json(
                {
                    error: "unauthorized",
                    message: "Missing or malformed API key. Use Authorization: Bearer capk_...",
                },
                { status: 401 }
            );
        }

        // 2. Verify API key
        let keyResult: { keyId: string; userId: string; status: string } | null;
        try {
            keyResult = await verifyKeyWithCache(apiKey);
        } catch (error) {
            console.error("[api-middleware] Key verification error:", error);
            return NextResponse.json(
                { error: "internal_error", message: "Failed to verify API key." },
                { status: 500 }
            );
        }

        if (!keyResult) {
            return NextResponse.json(
                { error: "unauthorized", message: "Invalid API key." },
                { status: 401 }
            );
        }

        if (keyResult.status === "revoked") {
            return NextResponse.json(
                {
                    error: "unauthorized",
                    message: "API key has been revoked.",
                },
                { status: 401 }
            );
        }

        // 3. Resolve user tier (cached)
        const tier = await getCachedTier(keyResult.userId);

        // 4. Check rate limit
        const { hash } = hashApiKey(apiKey);
        const rateLimitResult = await checkRateLimit(hash, tier);

        // Build rate-limit headers
        const rateLimitHeaders: Record<string, string> = {
            "X-RateLimit-Limit": String(rateLimitResult.limit),
            "X-RateLimit-Remaining": String(rateLimitResult.remaining),
            "X-RateLimit-Reset": String(rateLimitResult.reset),
        };

        if (!rateLimitResult.success) {
            const retryAfter = Math.max(
                1,
                Math.ceil((rateLimitResult.reset - Date.now()) / 1000)
            );

            return NextResponse.json(
                {
                    error: "rate_limit_exceeded",
                    message: "Rate limit exceeded. Upgrade your plan for higher limits.",
                    retry_after: retryAfter,
                    limit: rateLimitResult.limit,
                    reset: rateLimitResult.reset,
                },
                {
                    status: 429,
                    headers: {
                        ...rateLimitHeaders,
                        "Retry-After": String(retryAfter),
                    },
                }
            );
        }

        // 5. Call the actual handler
        const response = await handler(req, {
            userId: keyResult.userId,
            keyId: keyResult.keyId,
            tier,
        });

        // Attach rate-limit headers to successful responses
        for (const [key, value] of Object.entries(rateLimitHeaders)) {
            response.headers.set(key, value);
        }

        return response;
    };
}

// Re-export extractApiKey for testing
export { extractApiKey as _extractApiKey };
