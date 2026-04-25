/**
 * API key authentication + rate limiting for public API routes.
 *
 * Usage in a Next.js API route handler:
 *
 *   import { authenticateApiRequest } from "@/lib/api-key-auth";
 *
 *   export async function GET(req: Request) {
 *     const auth = await authenticateApiRequest(req);
 *     if (!auth.ok) return auth.response;
 *     // auth.userId, auth.keyId, auth.tier, auth.rateLimitHeaders are available
 *     const data = await fetchData(auth.userId);
 *     return NextResponse.json(data, { headers: auth.rateLimitHeaders });
 *   }
 */
import { NextResponse } from "next/server";
import { verifyKey } from "@/lib/api-keys/repository";
import { getUserTier } from "@/lib/api-keys/tiers";
import { checkRateLimit, buildRateLimitHeaders } from "@/lib/rate-limit";
import type { Tier } from "@/lib/api-keys/tiers";

export interface AuthSuccess {
    ok: true;
    keyId: string;
    userId: string;
    tier: Tier;
    /** Include these headers on the successful response. */
    rateLimitHeaders: HeadersInit;
}

export interface AuthFailure {
    ok: false;
    /** Return this response directly to the client. */
    response: NextResponse;
}

export type AuthResult = AuthSuccess | AuthFailure;

/**
 * Authenticate an API request using a Bearer token.
 *
 * Steps:
 *   1. Extract `Authorization: Bearer <key>` from the request.
 *   2. Verify the key against BigQuery.
 *   3. Look up the user's subscription tier.
 *   4. Check the sliding-window rate limit via Upstash.
 *   5. Return the authenticated context or an appropriate error response.
 */
export async function authenticateApiRequest(
    req: Request
): Promise<AuthResult> {
    const authHeader = req.headers.get("Authorization");
    if (!authHeader?.startsWith("Bearer ")) {
        return {
            ok: false,
            response: NextResponse.json(
                {
                    error: "Missing or invalid Authorization header.",
                    hint: "Use: Authorization: Bearer <api-key>",
                },
                { status: 401 }
            ),
        };
    }

    const plaintextKey = authHeader.slice(7); // strip "Bearer "

    const keyData = await verifyKey(plaintextKey);
    if (!keyData || keyData.status !== "active") {
        return {
            ok: false,
            response: NextResponse.json(
                { error: "Invalid or revoked API key." },
                { status: 401 }
            ),
        };
    }

    const tier = await getUserTier(keyData.userId);
    const rateLimitResult = await checkRateLimit(keyData.keyId, tier);
    const rateLimitHeaders = buildRateLimitHeaders(rateLimitResult);

    if (!rateLimitResult.success) {
        return {
            ok: false,
            response: NextResponse.json(
                {
                    error: "Rate limit exceeded.",
                    limit: rateLimitResult.limit,
                    remaining: 0,
                    reset: rateLimitResult.reset,
                    retryAfter: rateLimitResult.retryAfter,
                },
                { status: 429, headers: rateLimitHeaders }
            ),
        };
    }

    return {
        ok: true,
        keyId: keyData.keyId,
        userId: keyData.userId,
        tier,
        rateLimitHeaders,
    };
}
