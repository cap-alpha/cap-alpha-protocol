/**
 * Tests for tier configuration and resolution.
 */
import { describe, it, expect } from "vitest";

import { getUserTier, getMaxKeysForTier, getTierConfig } from "../tiers";
import type { Tier } from "../tiers";

describe("getMaxKeysForTier", () => {
    it("returns 1 for free tier", () => {
        expect(getMaxKeysForTier("free")).toBe(1);
    });

    it("returns 3 for pro tier", () => {
        expect(getMaxKeysForTier("pro")).toBe(3);
    });

    it("returns 10 for api_starter tier", () => {
        expect(getMaxKeysForTier("api_starter")).toBe(10);
    });

    it("returns 25 for api_growth tier", () => {
        expect(getMaxKeysForTier("api_growth")).toBe(25);
    });

    it("returns 25 for enterprise tier", () => {
        expect(getMaxKeysForTier("enterprise")).toBe(25);
    });
});

describe("getTierConfig", () => {
    it("returns config objects with maxKeys", () => {
        const tiers: Tier[] = ["free", "pro", "api_starter", "api_growth", "enterprise"];
        for (const tier of tiers) {
            const config = getTierConfig(tier);
            expect(config).toHaveProperty("maxKeys");
            expect(typeof config.maxKeys).toBe("number");
            expect(config.maxKeys).toBeGreaterThan(0);
        }
    });
});

describe("getUserTier", () => {
    it("returns 'free' as default for any user (stub)", async () => {
        const tier = await getUserTier("user_abc123");
        expect(tier).toBe("free");
    });

    it("returns 'free' for unknown users (stub)", async () => {
        const tier = await getUserTier("user_unknown");
        expect(tier).toBe("free");
    });
});
