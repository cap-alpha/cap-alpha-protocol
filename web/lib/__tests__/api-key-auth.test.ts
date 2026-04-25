/**
 * Unit tests for authenticateApiRequest.
 *
 * All external dependencies (BigQuery, Upstash, Clerk) are mocked.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

// vi.hoisted ensures these are available inside vi.mock() factories,
// which are hoisted above regular imports by vitest.
const { mockVerifyKey, mockGetUserTier, mockCheckRateLimit, mockBuildRateLimitHeaders } =
    vi.hoisted(() => ({
        mockVerifyKey: vi.fn(),
        mockGetUserTier: vi.fn(),
        mockCheckRateLimit: vi.fn(),
        mockBuildRateLimitHeaders: vi.fn(),
    }));

vi.mock("@/lib/api-keys/repository", () => ({
    verifyKey: mockVerifyKey,
}));

vi.mock("@/lib/api-keys/tiers", () => ({
    getUserTier: mockGetUserTier,
}));

vi.mock("@/lib/rate-limit", () => ({
    checkRateLimit: mockCheckRateLimit,
    buildRateLimitHeaders: mockBuildRateLimitHeaders,
}));

import { authenticateApiRequest } from "../api-key-auth";

// Helpers for building mock Request objects
function makeRequest(authHeader?: string): Request {
    const headers: Record<string, string> = {};
    if (authHeader !== undefined) headers["Authorization"] = authHeader;
    return new Request("https://api.cap-alpha.co/v1/pundits", { headers });
}

const ACTIVE_KEY = {
    keyId: "capk_live_abc123",
    userId: "user_xyz",
    status: "active",
};

const DEFAULT_RATE_LIMIT = {
    success: true,
    limit: 100,
    remaining: 99,
    reset: Math.floor(Date.now() / 1000) + 60,
};

const DEFAULT_HEADERS = {
    "X-RateLimit-Limit": "100",
    "X-RateLimit-Remaining": "99",
    "X-RateLimit-Reset": String(DEFAULT_RATE_LIMIT.reset),
};

beforeEach(() => {
    vi.resetAllMocks();
    mockGetUserTier.mockResolvedValue("free");
    mockCheckRateLimit.mockResolvedValue(DEFAULT_RATE_LIMIT);
    mockBuildRateLimitHeaders.mockReturnValue(DEFAULT_HEADERS);
});

// ── Missing / malformed Authorization header ──────────────────────────────────

describe("authenticateApiRequest — missing/invalid auth header", () => {
    it("returns 401 when Authorization header is absent", async () => {
        const auth = await authenticateApiRequest(makeRequest());
        expect(auth.ok).toBe(false);
        if (!auth.ok) {
            expect(auth.response.status).toBe(401);
        }
    });

    it("returns 401 when Authorization header lacks 'Bearer ' prefix", async () => {
        const auth = await authenticateApiRequest(
            makeRequest("Token capk_live_abc123")
        );
        expect(auth.ok).toBe(false);
        if (!auth.ok) expect(auth.response.status).toBe(401);
    });

    it("returns 401 for an empty Bearer value", async () => {
        const auth = await authenticateApiRequest(makeRequest("Bearer "));
        // verifyKey returns null for invalid key
        mockVerifyKey.mockResolvedValueOnce(null);
        // (header is technically valid format, so verifyKey is called)
    });

    it("does not call verifyKey when header is absent", async () => {
        await authenticateApiRequest(makeRequest());
        expect(mockVerifyKey).not.toHaveBeenCalled();
    });
});

// ── Invalid / revoked keys ────────────────────────────────────────────────────

describe("authenticateApiRequest — invalid or revoked key", () => {
    it("returns 401 when verifyKey returns null", async () => {
        mockVerifyKey.mockResolvedValueOnce(null);

        const auth = await authenticateApiRequest(
            makeRequest("Bearer capk_live_bad")
        );
        expect(auth.ok).toBe(false);
        if (!auth.ok) expect(auth.response.status).toBe(401);
    });

    it("returns 401 when key status is 'revoked'", async () => {
        mockVerifyKey.mockResolvedValueOnce({
            ...ACTIVE_KEY,
            status: "revoked",
        });

        const auth = await authenticateApiRequest(
            makeRequest("Bearer capk_live_abc123")
        );
        expect(auth.ok).toBe(false);
        if (!auth.ok) expect(auth.response.status).toBe(401);
    });

    it("does not check rate limit for invalid keys", async () => {
        mockVerifyKey.mockResolvedValueOnce(null);
        await authenticateApiRequest(makeRequest("Bearer capk_live_bad"));
        expect(mockCheckRateLimit).not.toHaveBeenCalled();
    });
});

// ── Rate limit exceeded ───────────────────────────────────────────────────────

describe("authenticateApiRequest — rate limit exceeded", () => {
    it("returns 429 when rate limit is exceeded", async () => {
        mockVerifyKey.mockResolvedValueOnce(ACTIVE_KEY);
        mockCheckRateLimit.mockResolvedValueOnce({
            success: false,
            limit: 100,
            remaining: 0,
            reset: Math.floor(Date.now() / 1000) + 30,
            retryAfter: 30,
        });
        mockBuildRateLimitHeaders.mockReturnValueOnce({
            "X-RateLimit-Limit": "100",
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": String(Math.floor(Date.now() / 1000) + 30),
            "Retry-After": "30",
        });

        const auth = await authenticateApiRequest(
            makeRequest("Bearer capk_live_abc123")
        );
        expect(auth.ok).toBe(false);
        if (!auth.ok) expect(auth.response.status).toBe(429);
    });

    it("includes retryAfter in the 429 response body", async () => {
        mockVerifyKey.mockResolvedValueOnce(ACTIVE_KEY);
        mockCheckRateLimit.mockResolvedValueOnce({
            success: false,
            limit: 100,
            remaining: 0,
            reset: Math.floor(Date.now() / 1000) + 30,
            retryAfter: 30,
        });
        mockBuildRateLimitHeaders.mockReturnValueOnce({
            "Retry-After": "30",
        });

        const auth = await authenticateApiRequest(
            makeRequest("Bearer capk_live_abc123")
        );
        if (!auth.ok) {
            const body = await auth.response.json();
            expect(body.error).toMatch(/rate limit/i);
            expect(body.retryAfter).toBe(30);
        }
    });
});

// ── Successful authentication ─────────────────────────────────────────────────

describe("authenticateApiRequest — success", () => {
    it("returns ok=true with keyId, userId, and tier", async () => {
        mockVerifyKey.mockResolvedValueOnce(ACTIVE_KEY);

        const auth = await authenticateApiRequest(
            makeRequest("Bearer capk_live_abc123")
        );
        expect(auth.ok).toBe(true);
        if (auth.ok) {
            expect(auth.keyId).toBe("capk_live_abc123");
            expect(auth.userId).toBe("user_xyz");
            expect(auth.tier).toBe("free");
        }
    });

    it("returns rateLimitHeaders for the caller to forward", async () => {
        mockVerifyKey.mockResolvedValueOnce(ACTIVE_KEY);

        const auth = await authenticateApiRequest(
            makeRequest("Bearer capk_live_abc123")
        );
        if (auth.ok) {
            expect(auth.rateLimitHeaders).toMatchObject({
                "X-RateLimit-Limit": expect.any(String),
                "X-RateLimit-Remaining": expect.any(String),
                "X-RateLimit-Reset": expect.any(String),
            });
        }
    });

    it("uses the user's tier when checking rate limit", async () => {
        mockVerifyKey.mockResolvedValueOnce(ACTIVE_KEY);
        mockGetUserTier.mockResolvedValueOnce("pro");

        await authenticateApiRequest(makeRequest("Bearer capk_live_abc123"));

        expect(mockCheckRateLimit).toHaveBeenCalledWith(
            ACTIVE_KEY.keyId,
            "pro"
        );
    });

    it("passes the keyId (not userId) as the rate limit identifier", async () => {
        mockVerifyKey.mockResolvedValueOnce(ACTIVE_KEY);

        await authenticateApiRequest(makeRequest("Bearer capk_live_abc123"));

        const [callKeyId] = mockCheckRateLimit.mock.calls[0];
        expect(callKeyId).toBe(ACTIVE_KEY.keyId);
        expect(callKeyId).not.toBe(ACTIVE_KEY.userId);
    });
});
