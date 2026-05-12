/**
 * Unit tests for resolution window derivation.
 *
 * Covers:
 *  - deriveResolutionWindow: correct kind for each claim_category
 *  - Regex explicit-date override
 *  - Trade deadline + draft lookups from static table
 *  - windowToSortDate: sort ordering
 *  - windowMatchesBucket: bucket filter logic
 *
 * Issue: #770
 */

import { describe, it, expect } from "vitest";
import {
    deriveResolutionWindow,
    windowToSortDate,
    windowMatchesBucket,
    type PredictionResolutionInput,
} from "../resolution-window";

const base: PredictionResolutionInput = {
    claim_category: "trade",
    sport: "NFL",
    season_year: 2025,
    raw_assertion_text: null,
};

describe("deriveResolutionWindow", () => {
    describe("trade category", () => {
        it("returns event with trade deadline for NFL 2025", () => {
            const w = deriveResolutionWindow({ ...base });
            expect(w.kind).toBe("event");
            if (w.kind === "event") {
                expect(w.eventName).toContain("Trade Deadline");
                expect(w.estDate).toBe("2025-11-04");
            }
        });

        it("returns fuzzy when no season_year", () => {
            const w = deriveResolutionWindow({ ...base, season_year: null });
            expect(w.kind).toBe("fuzzy");
        });

        it("returns fuzzy for unknown sport+year combo", () => {
            const w = deriveResolutionWindow({ ...base, sport: "CFL", season_year: 2025 });
            expect(w.kind).toBe("fuzzy");
        });
    });

    describe("draft_pick category", () => {
        it("returns event for NFL draft 2025", () => {
            const w = deriveResolutionWindow({
                ...base,
                claim_category: "draft_pick",
            });
            expect(w.kind).toBe("event");
            if (w.kind === "event") {
                expect(w.eventName).toContain("Draft");
            }
        });
    });

    describe("game_outcome category", () => {
        it("returns season when season_year is known", () => {
            const w = deriveResolutionWindow({
                ...base,
                claim_category: "game_outcome",
                season_year: 2025,
            });
            expect(w.kind).toBe("season");
            if (w.kind === "season") {
                expect(w.year).toBe(2025);
            }
        });

        it("returns fuzzy when no season_year", () => {
            const w = deriveResolutionWindow({
                ...base,
                claim_category: "game_outcome",
                season_year: null,
            });
            expect(w.kind).toBe("fuzzy");
        });
    });

    describe("player_performance category", () => {
        it("returns season when season_year known", () => {
            const w = deriveResolutionWindow({
                ...base,
                claim_category: "player_performance",
                season_year: 2025,
            });
            expect(w.kind).toBe("season");
        });

        it("returns fuzzy when no season_year", () => {
            const w = deriveResolutionWindow({
                ...base,
                claim_category: "player_performance",
                season_year: null,
            });
            expect(w.kind).toBe("fuzzy");
        });
    });

    describe("explicit date override", () => {
        it("extracts 'by November 4' from raw text", () => {
            const w = deriveResolutionWindow({
                ...base,
                raw_assertion_text: "Adams will be traded by November 4, 2025.",
            });
            // For trade category with a known deadline: prefers exact_date when explicit found
            expect(w.kind).toBe("exact_date");
            if (w.kind === "exact_date") {
                expect(w.label).toContain("Nov");
            }
        });

        it("extracts 'before week 10' from raw text", () => {
            const w = deriveResolutionWindow({
                ...base,
                claim_category: "game_outcome",
                raw_assertion_text: "The Chiefs will lose before week 10.",
            });
            expect(w.kind).toBe("exact_date");
            if (w.kind === "exact_date") {
                expect(w.label).toBe("Before Week 10");
            }
        });

        it("does not match 'November 4' without leading by/before keyword", () => {
            const w = deriveResolutionWindow({
                ...base,
                claim_category: "game_outcome",
                raw_assertion_text: "On November 4 the Chiefs will win.",
                season_year: 2025,
            });
            // No explicit date override — falls back to season
            expect(w.kind).toBe("season");
        });
    });
});

describe("windowToSortDate", () => {
    it("exact_date with ISO date sorts before season", () => {
        const exactDate = windowToSortDate({
            kind: "exact_date",
            date: "2025-11-04",
            label: "Nov 4, 2025",
        });
        const season = windowToSortDate({ kind: "season", year: 2025 });
        expect(exactDate.getTime()).toBeLessThan(season.getTime());
    });

    it("fuzzy sorts after season", () => {
        const fuzzy = windowToSortDate({ kind: "fuzzy", hint: "TBD" });
        const season = windowToSortDate({ kind: "season", year: 2025 });
        expect(fuzzy.getTime()).toBeGreaterThan(season.getTime());
    });
});

describe("windowMatchesBucket", () => {
    it("'all' bucket always matches", () => {
        expect(
            windowMatchesBucket({ kind: "fuzzy", hint: "TBD" }, "all")
        ).toBe(true);
    });

    it("season window matches 'season' bucket", () => {
        const currentYear = new Date().getFullYear();
        expect(
            windowMatchesBucket({ kind: "season", year: currentYear }, "season")
        ).toBe(true);
    });

    it("past dates do not match 'week' bucket", () => {
        expect(
            windowMatchesBucket(
                { kind: "exact_date", date: "2020-01-01", label: "Jan 1, 2020" },
                "week"
            )
        ).toBe(false);
    });
});
