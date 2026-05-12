/**
 * Unit tests for web/lib/tier.ts
 *
 * Mocks Clerk's `currentUser` to test tier resolution from publicMetadata.
 * Covers: unauthenticated, free (no metadata), pro, agent, unknown tier.
 *
 * Issue: #771 Phase 1
 */

import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock @clerk/nextjs/server before importing tier.ts so the module-level
// import is replaced by our stub.
vi.mock("@clerk/nextjs/server", () => ({
    currentUser: vi.fn(),
}));

import { currentUser } from "@clerk/nextjs/server";
import { getUserTier, isPro, FREE_PREDICTION_CAP, PAID_TIERS } from "../tier";

const mockCurrentUser = vi.mocked(currentUser);

import type { User } from "@clerk/nextjs/server";

// Helper to build a minimal Clerk user stub.
function makeUser(tier: string | undefined): User {
    return {
        publicMetadata: tier !== undefined ? { tier } : {},
    } as unknown as User;
}

beforeEach(() => {
    mockCurrentUser.mockReset();
});

// ── getUserTier ───────────────────────────────────────────────────────────────

describe("getUserTier", () => {
    it("returns 'free' when the user is not authenticated (null)", async () => {
        mockCurrentUser.mockResolvedValue(null);
        expect(await getUserTier()).toBe("free");
    });

    it("returns 'free' when publicMetadata has no tier field", async () => {
        mockCurrentUser.mockResolvedValue(makeUser(undefined));
        expect(await getUserTier()).toBe("free");
    });

    it("returns 'free' when publicMetadata.tier is an unknown string", async () => {
        mockCurrentUser.mockResolvedValue(makeUser("enterprise"));
        expect(await getUserTier()).toBe("free");
    });

    it("returns 'free' when publicMetadata.tier is 'free'", async () => {
        mockCurrentUser.mockResolvedValue(makeUser("free"));
        expect(await getUserTier()).toBe("free");
    });

    it("returns 'pro' when publicMetadata.tier is 'pro'", async () => {
        mockCurrentUser.mockResolvedValue(makeUser("pro"));
        expect(await getUserTier()).toBe("pro");
    });

    it("returns 'agent' when publicMetadata.tier is 'agent'", async () => {
        mockCurrentUser.mockResolvedValue(makeUser("agent"));
        expect(await getUserTier()).toBe("agent");
    });
});

// ── isPro ─────────────────────────────────────────────────────────────────────

describe("isPro", () => {
    it("returns false for unauthenticated users", async () => {
        mockCurrentUser.mockResolvedValue(null);
        expect(await isPro()).toBe(false);
    });

    it("returns false for free-tier users", async () => {
        mockCurrentUser.mockResolvedValue(makeUser("free"));
        expect(await isPro()).toBe(false);
    });

    it("returns true for pro-tier users", async () => {
        mockCurrentUser.mockResolvedValue(makeUser("pro"));
        expect(await isPro()).toBe(true);
    });

    it("returns true for agent-tier users", async () => {
        mockCurrentUser.mockResolvedValue(makeUser("agent"));
        expect(await isPro()).toBe(true);
    });
});

// ── constants ─────────────────────────────────────────────────────────────────

describe("FREE_PREDICTION_CAP", () => {
    it("is 15", () => {
        expect(FREE_PREDICTION_CAP).toBe(15);
    });
});

describe("PAID_TIERS", () => {
    it("includes pro and agent", () => {
        expect(PAID_TIERS.has("pro")).toBe(true);
        expect(PAID_TIERS.has("agent")).toBe(true);
    });

    it("does not include free, enterprise, api_starter, etc.", () => {
        expect(PAID_TIERS.has("free")).toBe(false);
        expect(PAID_TIERS.has("enterprise")).toBe(false);
        expect(PAID_TIERS.has("api_starter")).toBe(false);
    });
});
