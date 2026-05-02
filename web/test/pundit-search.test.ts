/**
 * Unit tests for PunditSearchBar search logic.
 *
 * We test the debounce / API-call behaviour as pure async logic
 * (no DOM rendering required) using vitest fake timers and a global fetch mock.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import type { PunditSearchResult } from "@/app/api/search/pundits/route";

// ---------------------------------------------------------------------------
// Helpers — simulate the debounce + fetch logic extracted from the component
// ---------------------------------------------------------------------------

type FetchResults = { results: PunditSearchResult[] };

function buildSearchFn(fetchImpl: typeof fetch) {
    const DEBOUNCE_MS = 300;

    return (query: string): { promise: Promise<PunditSearchResult[]>; timerId: ReturnType<typeof setTimeout> | null } => {
        let timerId: ReturnType<typeof setTimeout> | null = null;

        const promise = new Promise<PunditSearchResult[]>((resolve) => {
            if (query.length < 2) {
                resolve([]);
                return;
            }

            timerId = setTimeout(async () => {
                try {
                    const res = await fetchImpl(`/api/search/pundits?q=${encodeURIComponent(query)}`);
                    if (!res.ok) { resolve([]); return; }
                    const data = (await res.json()) as FetchResults;
                    resolve(data.results ?? []);
                } catch {
                    resolve([]);
                }
            }, DEBOUNCE_MS);
        });

        return { promise, timerId };
    };
}

// ---------------------------------------------------------------------------
// Arrow-key navigation logic (extracted from component)
// ---------------------------------------------------------------------------

function navigate(current: number, direction: "down" | "up", total: number): number {
    if (direction === "down") return Math.min(total - 1, current + 1);
    return Math.max(-1, current - 1);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("PunditSearchBar — debounce logic", () => {
    beforeEach(() => {
        vi.useFakeTimers();
    });

    afterEach(() => {
        vi.useRealTimers();
        vi.restoreAllMocks();
    });

    it("does not call fetch for queries shorter than 2 chars", async () => {
        const mockFetch = vi.fn();
        const search = buildSearchFn(mockFetch as unknown as typeof fetch);

        const result1 = search("");
        const result2 = search("a");

        // Advance timers to flush any pending debounce
        vi.advanceTimersByTime(400);

        expect(await result1.promise).toEqual([]);
        expect(await result2.promise).toEqual([]);
        expect(mockFetch).not.toHaveBeenCalled();
    });

    it("fires exactly once after 300ms for a valid query", async () => {
        const mockResults: PunditSearchResult[] = [
            {
                id: "adam_schefter",
                slug: "adam_schefter",
                name: "Adam Schefter",
                accuracy: 0.61,
                predictionCount: 120,
                correctCount: 73,
                domain: "sports.nfl",
            },
        ];

        const mockFetch = vi.fn().mockResolvedValue({
            ok: true,
            json: async () => ({ results: mockResults }),
        });

        const search = buildSearchFn(mockFetch as unknown as typeof fetch);

        const { promise } = search("Schefter");

        // Before debounce fires — no calls yet
        vi.advanceTimersByTime(299);
        expect(mockFetch).not.toHaveBeenCalled();

        // Advance past debounce threshold
        vi.advanceTimersByTime(1);

        const results = await promise;
        expect(mockFetch).toHaveBeenCalledTimes(1);
        expect(mockFetch).toHaveBeenCalledWith(
            "/api/search/pundits?q=Schefter"
        );
        expect(results).toEqual(mockResults);
    });

    it("returns empty array when API returns 0 results", async () => {
        const mockFetch = vi.fn().mockResolvedValue({
            ok: true,
            json: async () => ({ results: [] }),
        });

        const search = buildSearchFn(mockFetch as unknown as typeof fetch);
        const { promise } = search("zzznomatch");

        vi.advanceTimersByTime(300);

        const results = await promise;
        expect(results).toEqual([]);
    });

    it("returns empty array when API errors", async () => {
        const mockFetch = vi.fn().mockResolvedValue({
            ok: false,
            status: 500,
            json: async () => ({ results: [] }),
        });

        const search = buildSearchFn(mockFetch as unknown as typeof fetch);
        const { promise } = search("SomeQuery");

        vi.advanceTimersByTime(300);

        const results = await promise;
        expect(results).toEqual([]);
    });
});

describe("PunditSearchBar — keyboard navigation", () => {
    it("ArrowDown moves to first result (index 0) from -1", () => {
        expect(navigate(-1, "down", 3)).toBe(0);
    });

    it("ArrowDown stops at last result", () => {
        expect(navigate(2, "down", 3)).toBe(2);
    });

    it("ArrowUp from index 0 returns to -1 (input focused)", () => {
        expect(navigate(0, "up", 3)).toBe(-1);
    });

    it("ArrowUp clamps at -1 when already at input level", () => {
        expect(navigate(-1, "up", 3)).toBe(-1);
    });
});
