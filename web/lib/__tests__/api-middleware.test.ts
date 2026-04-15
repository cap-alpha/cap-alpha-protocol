/**
 * Tests for API middleware: key extraction, 429 response format.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { NextRequest, NextResponse } from "next/server";

// Mock dependencies
vi.mock("../redis", () => ({
    redis: null,
}));

vi.mock("../api-keys/index", () => ({
    hashApiKey: vi.fn((key: string) => ({
        hash: `hashed_${key}`,
        pepperVersion: 1,
    })),
}));

vi.mock("../api-keys/repository", () => ({
    verifyKey: vi.fn(),
}));

vi.mock("../tier-cache", () => ({
    getCachedTier: vi.fn().mockResolvedValue("free"),
}));

vi.mock("../rate-limiter", () => ({
    checkRateLimit: vi.fn().mockResolvedValue({
        success: true,
        limit: 100,
        remaining: 99,
        reset: Date.now() + 60_000,
    }),
}));

import { withApiAuth, _extractApiKey } from "../api-middleware";
import { verifyKey } from "../api-keys/repository";
import { checkRateLimit } from "../rate-limiter";

function makeRequest(headers: Record<string, string> = {}): NextRequest {
    const req = new NextRequest("https://example.com/api/v1/test", {
        headers,
    });
    return req;
}

describe("extractApiKey", () => {
    it("extracts a valid capk_ token from Authorization header", () => {
        const req = makeRequest({
            authorization: "Bearer capk_live_abc123",
        });
        const key = _extractApiKey(req);
        expect(key).toBe("capk_live_abc123");
    });

    it("returns null when Authorization header is missing", () => {
        const req = makeRequest({});
        const key = _extractApiKey(req);
        expect(key).toBeNull();
    });

    it("returns null for non-Bearer auth", () => {
        const req = makeRequest({ authorization: "Basic abc123" });
        const key = _extractApiKey(req);
        expect(key).toBeNull();
    });

    it("returns null for non-capk_ tokens", () => {
        const req = makeRequest({ authorization: "Bearer sk_live_abc" });
        const key = _extractApiKey(req);
        expect(key).toBeNull();
    });

    it("returns null for malformed Bearer header", () => {
        const req = makeRequest({ authorization: "Bearer" });
        const key = _extractApiKey(req);
        expect(key).toBeNull();
    });
});

describe("withApiAuth", () => {
    const mockHandler = vi.fn().mockImplementation(async (_req, ctx) => {
        return NextResponse.json({ ok: true, tier: ctx.tier });
    });

    beforeEach(() => {
        vi.clearAllMocks();
        mockHandler.mockImplementation(async (_req, ctx) => {
            return NextResponse.json({ ok: true, tier: ctx.tier });
        });
    });

    it("returns 401 when no Authorization header is present", async () => {
        const wrapped = withApiAuth(mockHandler);
        const response = await wrapped(makeRequest());

        expect(response.status).toBe(401);
        const body = await response.json();
        expect(body.error).toBe("unauthorized");
    });

    it("returns 401 when API key is invalid", async () => {
        (verifyKey as any).mockResolvedValueOnce(null);

        const wrapped = withApiAuth(mockHandler);
        const response = await wrapped(
            makeRequest({ authorization: "Bearer capk_live_abc123" })
        );

        expect(response.status).toBe(401);
        const body = await response.json();
        expect(body.error).toBe("unauthorized");
        expect(body.message).toBe("Invalid API key.");
    });

    it("returns 401 when API key is revoked", async () => {
        (verifyKey as any).mockResolvedValueOnce({
            keyId: "capk_live_abc",
            userId: "user_123",
            status: "revoked",
        });

        const wrapped = withApiAuth(mockHandler);
        const response = await wrapped(
            makeRequest({ authorization: "Bearer capk_live_abc123" })
        );

        expect(response.status).toBe(401);
        const body = await response.json();
        expect(body.message).toContain("revoked");
    });

    it("returns 429 with correct body when rate limited", async () => {
        (verifyKey as any).mockResolvedValueOnce({
            keyId: "capk_live_abc",
            userId: "user_123",
            status: "active",
        });

        const resetTime = Date.now() + 30_000;
        (checkRateLimit as any).mockResolvedValueOnce({
            success: false,
            limit: 100,
            remaining: 0,
            reset: resetTime,
        });

        const wrapped = withApiAuth(mockHandler);
        const response = await wrapped(
            makeRequest({ authorization: "Bearer capk_live_abc123" })
        );

        expect(response.status).toBe(429);
        const body = await response.json();
        expect(body.error).toBe("rate_limit_exceeded");
        expect(body.message).toContain("Rate limit exceeded");
        expect(body.retry_after).toBeGreaterThan(0);
        expect(body.limit).toBe(100);
        expect(body.reset).toBe(resetTime);
        expect(response.headers.get("Retry-After")).toBeTruthy();
        expect(response.headers.get("X-RateLimit-Limit")).toBe("100");
        expect(response.headers.get("X-RateLimit-Remaining")).toBe("0");
    });

    it("calls handler and sets rate-limit headers on success", async () => {
        (verifyKey as any).mockResolvedValueOnce({
            keyId: "capk_live_abc",
            userId: "user_123",
            status: "active",
        });

        const wrapped = withApiAuth(mockHandler);
        const response = await wrapped(
            makeRequest({ authorization: "Bearer capk_live_abc123" })
        );

        expect(response.status).toBe(200);
        const body = await response.json();
        expect(body.ok).toBe(true);
        expect(body.tier).toBe("free");
        expect(response.headers.get("X-RateLimit-Limit")).toBeTruthy();
        expect(response.headers.get("X-RateLimit-Remaining")).toBeTruthy();
        expect(response.headers.get("X-RateLimit-Reset")).toBeTruthy();
        expect(mockHandler).toHaveBeenCalledTimes(1);
    });
});
