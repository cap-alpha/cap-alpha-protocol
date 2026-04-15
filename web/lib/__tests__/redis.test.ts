/**
 * Tests for Redis client initialization.
 *
 * Verifies that missing env vars produce null (no crash) and that
 * the module exports the expected shape.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

describe("redis client", () => {
    const originalEnv = process.env;

    beforeEach(() => {
        vi.resetModules();
        process.env = { ...originalEnv };
    });

    afterEach(() => {
        process.env = originalEnv;
    });

    it("exports null when UPSTASH_REDIS_REST_URL is missing", async () => {
        delete process.env.UPSTASH_REDIS_REST_URL;
        delete process.env.UPSTASH_REDIS_REST_TOKEN;

        const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
        const { redis } = await import("../redis");

        expect(redis).toBeNull();
        expect(warnSpy).toHaveBeenCalledWith(
            expect.stringContaining("UPSTASH_REDIS_REST_URL")
        );
        warnSpy.mockRestore();
    });

    it("exports null when UPSTASH_REDIS_REST_TOKEN is missing", async () => {
        process.env.UPSTASH_REDIS_REST_URL = "https://example.upstash.io";
        delete process.env.UPSTASH_REDIS_REST_TOKEN;

        const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
        const { redis } = await import("../redis");

        expect(redis).toBeNull();
        warnSpy.mockRestore();
    });

    it("does not crash the app when env vars are missing", async () => {
        delete process.env.UPSTASH_REDIS_REST_URL;
        delete process.env.UPSTASH_REDIS_REST_TOKEN;

        const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});

        // Should not throw
        await expect(import("../redis")).resolves.toBeDefined();
        warnSpy.mockRestore();
    });
});
