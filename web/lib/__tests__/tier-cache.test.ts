/**
 * Tests for tier cache: hit/miss behavior and invalidation.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

// Track mock state for redis
const mockRedisStore = new Map<string, string>();

vi.mock("../redis", () => ({
    redis: {
        get: vi.fn(async (key: string) => mockRedisStore.get(key) || null),
        set: vi.fn(async (key: string, value: string) => {
            mockRedisStore.set(key, value);
        }),
        del: vi.fn(async (key: string) => {
            mockRedisStore.delete(key);
        }),
    },
}));

import { getCachedTier, invalidateTierCache } from "../tier-cache";
import { redis } from "../redis";

describe("getCachedTier", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        mockRedisStore.clear();
    });

    it("returns cached tier on cache hit", async () => {
        mockRedisStore.set("tier:user_123", "pro");

        const tier = await getCachedTier("user_123");
        expect(tier).toBe("pro");
        expect(redis!.get).toHaveBeenCalledWith("tier:user_123");
    });

    it("falls back to Clerk and caches on cache miss", async () => {
        // No cached value -> should resolve from Clerk (stub returns 'free')
        const tier = await getCachedTier("user_456");
        expect(tier).toBe("free");

        // Should have been cached
        expect(redis!.set).toHaveBeenCalledWith(
            "tier:user_456",
            "free",
            expect.objectContaining({ ex: 300 })
        );
    });

    it("uses correct key format tier:{userId}", async () => {
        await getCachedTier("user_abc");
        expect(redis!.get).toHaveBeenCalledWith("tier:user_abc");
    });
});

describe("invalidateTierCache", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        mockRedisStore.clear();
    });

    it("deletes the cached tier entry", async () => {
        mockRedisStore.set("tier:user_123", "pro");

        await invalidateTierCache("user_123");
        expect(redis!.del).toHaveBeenCalledWith("tier:user_123");
    });
});
