/**
 * Tests for rate limiter configuration and behavior.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock redis before importing rate-limiter
vi.mock("../redis", () => ({
    redis: null,
}));

import { getRateLimitConfig, checkRateLimit } from "../rate-limiter";

describe("getRateLimitConfig", () => {
    it("returns correct limits for free tier", () => {
        const config = getRateLimitConfig("free");
        expect(config.perMinute).toBe(100);
        expect(config.perDay).toBe(10_000);
    });

    it("returns correct limits for pro tier", () => {
        const config = getRateLimitConfig("pro");
        expect(config.perMinute).toBe(1_000);
        expect(config.perDay).toBe(100_000);
    });

    it("returns correct limits for api_starter tier", () => {
        const config = getRateLimitConfig("api_starter");
        expect(config.perMinute).toBe(10_000);
        expect(config.perDay).toBe(1_000_000);
    });

    it("returns correct limits for api_growth tier", () => {
        const config = getRateLimitConfig("api_growth");
        expect(config.perMinute).toBe(100_000);
        expect(config.perDay).toBe(10_000_000);
    });

    it("returns correct limits for enterprise tier", () => {
        const config = getRateLimitConfig("enterprise");
        expect(config.perMinute).toBe(100_000);
        expect(config.perDay).toBe(10_000_000);
    });

    it("falls back to free tier for unknown tier strings", () => {
        const config = getRateLimitConfig("unknown_tier");
        expect(config.perMinute).toBe(100);
        expect(config.perDay).toBe(10_000);
    });
});

describe("checkRateLimit (no Redis)", () => {
    it("allows all requests when Redis is unavailable", async () => {
        const result = await checkRateLimit("test-key", "free");
        expect(result.success).toBe(true);
        expect(result.limit).toBe(100);
        expect(result.remaining).toBe(100);
        expect(result.reset).toBeGreaterThan(Date.now());
    });

    it("uses correct limits for the specified tier in no-op mode", async () => {
        const result = await checkRateLimit("test-key", "pro");
        expect(result.success).toBe(true);
        expect(result.limit).toBe(1_000);
        expect(result.remaining).toBe(1_000);
    });

    it("falls back to free tier for unknown tier in no-op mode", async () => {
        const result = await checkRateLimit("test-key", "bogus");
        expect(result.success).toBe(true);
        expect(result.limit).toBe(100);
    });
});
