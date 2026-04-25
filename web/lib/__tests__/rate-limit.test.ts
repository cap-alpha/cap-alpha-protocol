/**
 * Unit tests for the rate limiting utility.
 *
 * @upstash/ratelimit and @upstash/redis are mocked. Two test groups:
 *   1. Fail-open  — no UPSTASH env vars → all requests succeed, limit from tier config.
 *   2. With Upstash — env vars set → Ratelimit.limit() is called, results propagated.
 *
 * The fail-open group runs FIRST (before env vars are set) to avoid the
 * module-level Redis singleton being populated prematurely.
 */
import { describe, it, expect, vi, beforeAll, afterAll } from "vitest";

// Mock Upstash before any import of rate-limit.ts
const mockLimit = vi.fn();

vi.mock("@upstash/ratelimit", () => ({
    Ratelimit: class MockRatelimit {
        limit = mockLimit;
        constructor(_opts: unknown) {}
        static slidingWindow(_count: number, _window: string) {
            return { type: "slidingWindow", _count, _window };
        }
    },
}));

vi.mock("@upstash/redis", () => ({
    Redis: class MockRedis {
        constructor(_opts: unknown) {}
    },
}));

import {
    checkRateLimit,
    buildRateLimitHeaders,
    TIER_RATE_LIMITS,
} from "../rate-limit";

// ── Tier limit constants ──────────────────────────────────────────────────────

describe("TIER_RATE_LIMITS", () => {
    it("defines all tiers with positive per-minute limits", () => {
        const tiers = [
            "free",
            "pro",
            "api_starter",
            "api_growth",
            "enterprise",
        ] as const;
        for (const tier of tiers) {
            expect(TIER_RATE_LIMITS[tier]).toBeGreaterThan(0);
        }
    });

    it("enforces ascending order: free < pro < api_starter < api_growth < enterprise", () => {
        expect(TIER_RATE_LIMITS.free).toBeLessThan(TIER_RATE_LIMITS.pro);
        expect(TIER_RATE_LIMITS.pro).toBeLessThan(TIER_RATE_LIMITS.api_starter);
        expect(TIER_RATE_LIMITS.api_starter).toBeLessThan(
            TIER_RATE_LIMITS.api_growth
        );
        expect(TIER_RATE_LIMITS.api_growth).toBeLessThan(
            TIER_RATE_LIMITS.enterprise
        );
    });

    it("free tier allows 100 req/min", () => {
        expect(TIER_RATE_LIMITS.free).toBe(100);
    });

    it("pro tier allows 1000 req/min", () => {
        expect(TIER_RATE_LIMITS.pro).toBe(1_000);
    });

    it("api_starter tier allows 10,000 req/min", () => {
        expect(TIER_RATE_LIMITS.api_starter).toBe(10_000);
    });

    it("api_growth tier allows 100,000 req/min", () => {
        expect(TIER_RATE_LIMITS.api_growth).toBe(100_000);
    });
});

// ── Fail-open (no Upstash configured) ────────────────────────────────────────
// These must run before env vars are set so _redis singleton stays null.

describe("checkRateLimit — fail-open when UPSTASH env vars are absent", () => {
    it("returns success=true for free tier", async () => {
        const result = await checkRateLimit("capk_live_abc", "free");
        expect(result.success).toBe(true);
    });

    it("reports limit equal to tier's per-minute cap", async () => {
        const result = await checkRateLimit("capk_live_abc", "free");
        expect(result.limit).toBe(TIER_RATE_LIMITS.free);
        expect(result.remaining).toBe(TIER_RATE_LIMITS.free);
    });

    it("reports limit equal to pro tier cap", async () => {
        const result = await checkRateLimit("capk_live_pro", "pro");
        expect(result.limit).toBe(TIER_RATE_LIMITS.pro);
    });

    it("returns a reset timestamp ~60 s in the future", async () => {
        const before = Math.floor(Date.now() / 1000);
        const result = await checkRateLimit("capk_live_abc", "free");
        expect(result.reset).toBeGreaterThanOrEqual(before + 59);
        expect(result.reset).toBeLessThanOrEqual(before + 61);
    });

    it("does not set retryAfter when allowing", async () => {
        const result = await checkRateLimit("capk_live_abc", "free");
        expect(result.retryAfter).toBeUndefined();
    });

    it("never calls Ratelimit.limit() when Upstash is absent", async () => {
        await checkRateLimit("capk_live_abc", "free");
        expect(mockLimit).not.toHaveBeenCalled();
    });
});

// ── With Upstash configured ───────────────────────────────────────────────────

describe("checkRateLimit — with Upstash", () => {
    const originalUrl = process.env.UPSTASH_REDIS_REST_URL;
    const originalToken = process.env.UPSTASH_REDIS_REST_TOKEN;

    beforeAll(() => {
        process.env.UPSTASH_REDIS_REST_URL = "https://test.upstash.io";
        process.env.UPSTASH_REDIS_REST_TOKEN = "test-token";
        mockLimit.mockReset();
    });

    afterAll(() => {
        process.env.UPSTASH_REDIS_REST_URL = originalUrl;
        process.env.UPSTASH_REDIS_REST_TOKEN = originalToken;
    });

    it("returns success=true and remaining count when under the limit", async () => {
        const resetMs = (Math.floor(Date.now() / 1000) + 60) * 1000;
        mockLimit.mockResolvedValueOnce({
            success: true,
            limit: 100,
            remaining: 75,
            reset: resetMs,
        });

        const result = await checkRateLimit("capk_live_abc", "free");
        expect(result.success).toBe(true);
        expect(result.remaining).toBe(75);
        expect(result.retryAfter).toBeUndefined();
    });

    it("returns success=false with retryAfter when the limit is exceeded", async () => {
        const resetMs = (Math.floor(Date.now() / 1000) + 30) * 1000;
        mockLimit.mockResolvedValueOnce({
            success: false,
            limit: 100,
            remaining: 0,
            reset: resetMs,
        });

        const result = await checkRateLimit("capk_live_abc", "free");
        expect(result.success).toBe(false);
        expect(result.remaining).toBe(0);
        expect(result.retryAfter).toBeGreaterThan(0);
        expect(result.retryAfter).toBeLessThanOrEqual(30);
    });

    it("sets retryAfter=0 when reset is in the past (clock skew)", async () => {
        const resetMs = (Math.floor(Date.now() / 1000) - 5) * 1000;
        mockLimit.mockResolvedValueOnce({
            success: false,
            limit: 100,
            remaining: 0,
            reset: resetMs,
        });

        const result = await checkRateLimit("capk_live_abc", "free");
        expect(result.retryAfter).toBe(0);
    });

    it("forwards the keyId to Ratelimit.limit()", async () => {
        const resetMs = (Math.floor(Date.now() / 1000) + 60) * 1000;
        mockLimit.mockResolvedValueOnce({
            success: true,
            limit: 1000,
            remaining: 999,
            reset: resetMs,
        });

        await checkRateLimit("capk_live_mykey", "pro");
        expect(mockLimit).toHaveBeenCalledWith("capk_live_mykey");
    });
});

// ── buildRateLimitHeaders ─────────────────────────────────────────────────────

describe("buildRateLimitHeaders", () => {
    it("includes X-RateLimit-Limit, Remaining, and Reset on success", () => {
        const headers = buildRateLimitHeaders({
            success: true,
            limit: 100,
            remaining: 50,
            reset: 1_700_000_000,
        }) as Record<string, string>;

        expect(headers["X-RateLimit-Limit"]).toBe("100");
        expect(headers["X-RateLimit-Remaining"]).toBe("50");
        expect(headers["X-RateLimit-Reset"]).toBe("1700000000");
        expect(headers["Retry-After"]).toBeUndefined();
    });

    it("includes Retry-After when retryAfter is set", () => {
        const headers = buildRateLimitHeaders({
            success: false,
            limit: 100,
            remaining: 0,
            reset: 1_700_000_030,
            retryAfter: 30,
        }) as Record<string, string>;

        expect(headers["Retry-After"]).toBe("30");
    });

    it("Retry-After is 0 when retryAfter=0", () => {
        const headers = buildRateLimitHeaders({
            success: false,
            limit: 100,
            remaining: 0,
            reset: 1_700_000_000,
            retryAfter: 0,
        }) as Record<string, string>;

        expect(headers["Retry-After"]).toBe("0");
    });

    it("all header values are strings", () => {
        const headers = buildRateLimitHeaders({
            success: true,
            limit: 1000,
            remaining: 999,
            reset: 1_700_000_000,
        }) as Record<string, string>;

        for (const val of Object.values(headers)) {
            expect(typeof val).toBe("string");
        }
    });
});
