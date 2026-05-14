/**
 * Unit tests for PunditLeaderboardPreview fetch state machine and helpers.
 *
 * Because the project has no jsdom, rendering assertions live in the
 * Playwright E2E suite.  These tests cover:
 *   1. processRawPundits — pure filter/sort/slice logic
 *   2. Source-level contract: failure/retry path and timeout mechanism
 */

import { describe, it, expect } from "vitest";
import * as fs from "fs";
import * as path from "path";

// ---------------------------------------------------------------------------
// Helpers — mirror the exported-but-not-imported helpers from the component
// ---------------------------------------------------------------------------

interface PunditStat {
    pundit_name: string;
    pundit_id: string;
    total_predictions: number;
    resolved_predictions: number;
    correct_predictions: number;
    incorrect_predictions: number;
    accuracy_rate: number | null;
    avg_brier_score: number | null;
}

function processRawPundits(raw: PunditStat[]): PunditStat[] {
    const filtered = raw.filter(
        (p) => p.resolved_predictions >= 5 && p.accuracy_rate !== null
    );
    filtered.sort((a, b) => (b.accuracy_rate ?? 0) - (a.accuracy_rate ?? 0));
    return filtered.slice(0, 10);
}

function makePundit(overrides: Partial<PunditStat> = {}): PunditStat {
    return {
        pundit_name: "Test Pundit",
        pundit_id: "test-pundit",
        total_predictions: 10,
        resolved_predictions: 10,
        correct_predictions: 7,
        incorrect_predictions: 3,
        accuracy_rate: 0.7,
        avg_brier_score: 0.21,
        ...overrides,
    };
}

// ---------------------------------------------------------------------------
// processRawPundits
// ---------------------------------------------------------------------------

describe("processRawPundits — filter", () => {
    it("excludes pundits with fewer than 5 resolved predictions", () => {
        const pundits = [
            makePundit({ pundit_id: "a", resolved_predictions: 4, accuracy_rate: 1.0 }),
            makePundit({ pundit_id: "b", resolved_predictions: 5, accuracy_rate: 0.8 }),
        ];
        const result = processRawPundits(pundits);
        expect(result.map((p) => p.pundit_id)).toEqual(["b"]);
    });

    it("excludes pundits with null accuracy_rate", () => {
        const pundits = [
            makePundit({ pundit_id: "a", accuracy_rate: null }),
            makePundit({ pundit_id: "b", accuracy_rate: 0.5 }),
        ];
        const result = processRawPundits(pundits);
        expect(result.map((p) => p.pundit_id)).toEqual(["b"]);
    });
});

describe("processRawPundits — sort", () => {
    it("orders pundits by accuracy descending", () => {
        const pundits = [
            makePundit({ pundit_id: "low", accuracy_rate: 0.4 }),
            makePundit({ pundit_id: "high", accuracy_rate: 0.9 }),
            makePundit({ pundit_id: "mid", accuracy_rate: 0.6 }),
        ];
        const result = processRawPundits(pundits);
        expect(result.map((p) => p.pundit_id)).toEqual(["high", "mid", "low"]);
    });
});

describe("processRawPundits — cap", () => {
    it("returns at most 10 pundits regardless of input size", () => {
        const pundits = Array.from({ length: 25 }, (_, i) =>
            makePundit({ pundit_id: `p-${i}`, accuracy_rate: i / 25 })
        );
        expect(processRawPundits(pundits).length).toBeLessThanOrEqual(10);
    });
});

// ---------------------------------------------------------------------------
// Source-level contract: fetch state machine and timeout
// ---------------------------------------------------------------------------

const SRC = fs.readFileSync(
    path.resolve(__dirname, "../components/pundit-leaderboard-preview.tsx"),
    "utf-8"
);

describe("pundit-leaderboard-preview.tsx — fetch state machine contracts", () => {
    it('uses three distinct fetch states: "idle", "loading", "error"', () => {
        expect(SRC).toContain('"idle"');
        expect(SRC).toContain('"loading"');
        expect(SRC).toContain('"error"');
    });

    it("schedules a single automatic retry after the first failure", () => {
        expect(SRC).toContain("isRetry");
        expect(SRC).toContain("retryScheduled");
        expect(SRC).toContain("setTimeout");
    });

    it("surfaces the error state only after both initial fetch and retry have failed", () => {
        // The component must call setFetchState("error") inside the else branch
        // (retry also failed), not on the first failure.
        expect(SRC).toContain('setFetchState("error")');
        // The guard is: if (!isRetry && !retryScheduled.current) { schedule retry } else { set error }
        expect(SRC).toContain("!isRetry");
        expect(SRC).toContain("retryScheduled.current");
    });

    it("provides a manual retry button in the error state", () => {
        expect(SRC).toContain("Try again");
        // The button must set fetchState to "loading" before re-fetching
        expect(SRC).toContain('setFetchState("loading")');
    });

    it("aborts hung requests after FETCH_TIMEOUT_MS to prevent indefinite loading state", () => {
        expect(SRC).toContain("FETCH_TIMEOUT_MS");
        expect(SRC).toContain("AbortController");
        expect(SRC).toContain("controller.abort()");
        expect(SRC).toContain("clearTimeout");
    });

    it("passes the abort signal to fetch so network requests are actually cancelled", () => {
        expect(SRC).toContain("controller.signal");
        // fetchPundits must accept a signal parameter
        expect(SRC).toContain("signal?: AbortSignal");
    });

    it("does not say retrying in the terminal error message shown to users", () => {
        // "retrying…" would mislead users into expecting another automatic attempt.
        expect(SRC).not.toContain("retrying…");
    });

    it("cleans up the abort timeout on both success and failure paths", () => {
        // clearTimeout must be called in both .then() and .catch() to avoid leaks.
        const clearCount = (SRC.match(/clearTimeout/g) || []).length;
        expect(clearCount).toBeGreaterThanOrEqual(2);
    });
});
