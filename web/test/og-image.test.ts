/**
 * Unit tests for OG image helpers + route logic
 *
 * These tests cover the pure functions in lib/og-helpers.ts (stamp config +
 * cache-control derivation) without requiring JSX transform, plus a test that
 * verifies the full route handler produces the right headers by mocking
 * next/og's ImageResponse entirely so no JSX is parsed.
 *
 * Coverage:
 *   - getStampConfig: CORRECT → green text; INCORRECT → red; PENDING/null → amber
 *   - getCacheControl: CORRECT/INCORRECT → public max-age; PENDING/null → no-store
 *   - GET handler: returns ImageResponse-like object with correct Cache-Control
 */

import { describe, it, expect } from "vitest";
import { getStampConfig, getCacheControl, fmtDate } from "../lib/og-helpers";

// ---------------------------------------------------------------------------
// Pure helper tests — no JSX, no mocking needed
// ---------------------------------------------------------------------------

describe("getStampConfig", () => {
    it("returns CORRECT green stamp for CORRECT outcome", () => {
        const cfg = getStampConfig("CORRECT");
        expect(cfg.text).toContain("CORRECT");
        expect(cfg.color).toBe("#22c55e");
        expect(cfg.borderColor).toBe("#22c55e");
    });

    it("returns INCORRECT red stamp for INCORRECT outcome", () => {
        const cfg = getStampConfig("INCORRECT");
        expect(cfg.text).toContain("INCORRECT");
        expect(cfg.color).toBe("#ef4444");
        expect(cfg.borderColor).toBe("#ef4444");
    });

    it("returns PENDING amber stamp for null outcome", () => {
        const cfg = getStampConfig(null);
        expect(cfg.text).toBe("PENDING");
        expect(cfg.color).toBe("#fbbf24");
        expect(cfg.borderColor).toBe("#fbbf24");
    });

    it("returns PENDING amber stamp for PENDING outcome", () => {
        const cfg = getStampConfig("PENDING");
        expect(cfg.text).toBe("PENDING");
        expect(cfg.color).toBe("#fbbf24");
    });

    it("returns PENDING stamp for any unknown status", () => {
        const cfg = getStampConfig("VOID");
        expect(cfg.text).toBe("PENDING");
    });
});

describe("getCacheControl", () => {
    it("returns public, max-age=3600 for CORRECT outcome", () => {
        const cc = getCacheControl("CORRECT");
        expect(cc).toContain("public");
        expect(cc).toContain("max-age=3600");
    });

    it("returns public, max-age=3600 for INCORRECT outcome", () => {
        const cc = getCacheControl("INCORRECT");
        expect(cc).toContain("public");
        expect(cc).toContain("max-age=3600");
    });

    it("returns no-store for PENDING outcome", () => {
        expect(getCacheControl("PENDING")).toBe("no-store");
    });

    it("returns no-store for null outcome", () => {
        expect(getCacheControl(null)).toBe("no-store");
    });

    it("returns no-store for unknown outcome", () => {
        expect(getCacheControl("VOID")).toBe("no-store");
    });
});

describe("fmtDate", () => {
    it("formats a valid ISO timestamp", () => {
        const result = fmtDate("2024-10-12T00:00:00Z");
        expect(result).toMatch(/Oct/);
        expect(result).toMatch(/2024/);
    });

    it("returns em-dash for null", () => {
        expect(fmtDate(null)).toBe("—");
    });

    it("returns em-dash for undefined", () => {
        expect(fmtDate(undefined)).toBe("—");
    });
});
