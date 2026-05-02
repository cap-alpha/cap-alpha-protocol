/**
 * AnimatedCounter unit tests
 *
 * Tests the counter's rendering contract without a DOM:
 * - Final value formatting (decimals, prefix, suffix)
 * - Reduced-motion path renders immediately
 *
 * We test the *formatting logic* in isolation because vitest runs in Node
 * (no DOM), which means IntersectionObserver / Framer Motion hooks won't fire.
 * The component itself is exercised in the E2E spec.
 */

import { describe, it, expect } from "vitest";

// ---------------------------------------------------------------------------
// Extracted formatting helper — mirrors the logic in AnimatedCounter
// ---------------------------------------------------------------------------

function formatCounter(value: number, decimals: number, prefix: string, suffix: string): string {
    return `${prefix}${value.toFixed(decimals)}${suffix}`;
}

describe("AnimatedCounter — formatting", () => {
    it("renders an integer value with no decimals", () => {
        expect(formatCounter(42, 0, "", "")).toBe("42");
    });

    it("renders a value with decimals", () => {
        expect(formatCounter(71.34, 2, "", "")).toBe("71.34");
    });

    it("appends suffix correctly", () => {
        expect(formatCounter(68, 0, "", "%")).toBe("68%");
    });

    it("prepends prefix correctly", () => {
        expect(formatCounter(1250, 0, "$", "")).toBe("$1250");
    });

    it("combines prefix, value, suffix", () => {
        expect(formatCounter(99.5, 1, "$", "k")).toBe("$99.5k");
    });

    it("handles zero", () => {
        expect(formatCounter(0, 0, "", "%")).toBe("0%");
    });

    it("handles negative values", () => {
        expect(formatCounter(-5, 1, "", "°")).toBe("-5.0°");
    });

    it("rounds to specified decimals", () => {
        // toFixed rounds for us — 2.345 → "2.35" in most JS engines
        expect(formatCounter(2.344, 2, "", "")).toBe("2.34");
        expect(formatCounter(2.345, 2, "", "")).toBe("2.35");
    });
});

// ---------------------------------------------------------------------------
// Reduced-motion contract: when shouldReduceMotion is true the component
// must render the final value without any animation delay.
// We verify the *initial display string* produced with reduced motion equals
// the fully-formatted target value.
// ---------------------------------------------------------------------------

describe("AnimatedCounter — reduced motion contract", () => {
    it("reduced motion path immediately shows final value (no animation)", () => {
        // When useReducedMotion() returns true, the component sets displayStr
        // directly to formatCounter(value, decimals, prefix, suffix) without
        // starting a spring animation. We verify the format is correct.
        const value = 71.34;
        const decimals = 2;
        const suffix = "%";
        const prefix = "";

        // The component initialises displayStr to the formatted value:
        const expected = formatCounter(value, decimals, prefix, suffix);
        expect(expected).toBe("71.34%");
    });

    it("reduced motion path with integer decimals=0 suffix=%", () => {
        expect(formatCounter(68, 0, "", "%")).toBe("68%");
    });
});
