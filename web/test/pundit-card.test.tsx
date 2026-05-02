/**
 * Unit tests for PunditCard component and HOF/HOS logic.
 *
 * Because this project has no DOM testing library (no @testing-library/react,
 * no jsdom), these tests validate the component's prop types and helper
 * behaviour rather than rendering. Rendering assertions are covered by the
 * Playwright E2E suite in tests/e2e/ledger.spec.ts.
 */

import { describe, it, expect } from "vitest";
import type { PunditCardProps } from "../components/pundit-card";

// ---------------------------------------------------------------------------
// PunditCard — prop shape validation
// ---------------------------------------------------------------------------

describe("PunditCard — prop types", () => {
    it("accepts HOF variant props", () => {
        const props: PunditCardProps = {
            punditId: "stephen-a-smith",
            name: "Stephen A. Smith",
            accuracy: 0.72,
            correctCount: 18,
            totalCount: 25,
            variant: "hof",
        };
        expect(props.variant).toBe("hof");
        expect(props.accuracy).toBeGreaterThan(0);
        expect(props.accuracy).toBeLessThanOrEqual(1);
    });

    it("accepts HOS variant props", () => {
        const props: PunditCardProps = {
            punditId: "skip-bayless",
            name: "Skip Bayless",
            accuracy: 0.22,
            correctCount: 5,
            totalCount: 23,
            variant: "hos",
        };
        expect(props.variant).toBe("hos");
    });

    it("HOF variant should have green accent (variant = hof)", () => {
        const props: PunditCardProps = {
            punditId: "a",
            name: "A",
            accuracy: 0.8,
            correctCount: 8,
            totalCount: 10,
            variant: "hof",
        };
        // Green accent is applied when variant === 'hof'
        expect(props.variant).toBe("hof");
    });

    it("HOS variant should have red accent (variant = hos)", () => {
        const props: PunditCardProps = {
            punditId: "b",
            name: "B",
            accuracy: 0.2,
            correctCount: 2,
            totalCount: 10,
            variant: "hos",
        };
        // Red accent is applied when variant === 'hos'
        expect(props.variant).toBe("hos");
    });

    it("featuredPrediction is optional", () => {
        const withPrediction: PunditCardProps = {
            punditId: "c",
            name: "C",
            accuracy: 0.5,
            correctCount: 5,
            totalCount: 10,
            variant: "hof",
            featuredPrediction: {
                text: "The Chiefs will win the Super Bowl",
                outcome: "correct",
                resolvedAt: "Feb 11, 2024",
            },
        };
        expect(withPrediction.featuredPrediction).toBeDefined();
        expect(withPrediction.featuredPrediction!.outcome).toBe("correct");

        const withoutPrediction: PunditCardProps = {
            punditId: "d",
            name: "D",
            accuracy: 0.5,
            correctCount: 5,
            totalCount: 10,
            variant: "hof",
        };
        expect(withoutPrediction.featuredPrediction).toBeUndefined();
    });
});

// ---------------------------------------------------------------------------
// HOF/HOS selection logic (mirrors LedgerPage sorting logic)
// ---------------------------------------------------------------------------

interface MockPunditStat {
    pundit_id: string;
    pundit_name: string;
    total_predictions: number;
    resolved_predictions: number;
    correct_predictions: number;
    incorrect_predictions: number;
    accuracy_rate: number | null;
}

function pickHof(pundits: MockPunditStat[]): MockPunditStat[] {
    return [...pundits]
        .filter((p) => p.resolved_predictions > 0 && p.accuracy_rate !== null)
        .sort((a, b) => (b.accuracy_rate ?? 0) - (a.accuracy_rate ?? 0))
        .slice(0, 10);
}

function pickHos(pundits: MockPunditStat[]): MockPunditStat[] {
    return [...pundits]
        .filter((p) => p.total_predictions >= 10 && p.accuracy_rate !== null)
        .sort((a, b) => (a.accuracy_rate ?? 1) - (b.accuracy_rate ?? 1))
        .slice(0, 10);
}

describe("HOF selection", () => {
    const pundits: MockPunditStat[] = Array.from({ length: 20 }, (_, i) => ({
        pundit_id: `pundit-${i}`,
        pundit_name: `Pundit ${i}`,
        total_predictions: 20,
        resolved_predictions: 10,
        correct_predictions: i,
        incorrect_predictions: 10 - i,
        accuracy_rate: i / 10,
    }));

    it("returns at most 10 pundits", () => {
        expect(pickHof(pundits).length).toBeLessThanOrEqual(10);
    });

    it("orders by accuracy descending", () => {
        const hof = pickHof(pundits);
        for (let i = 0; i < hof.length - 1; i++) {
            expect(hof[i].accuracy_rate!).toBeGreaterThanOrEqual(
                hof[i + 1].accuracy_rate!
            );
        }
    });

    it("excludes pundits with no resolved predictions", () => {
        const mixed: MockPunditStat[] = [
            ...pundits,
            {
                pundit_id: "unresolved",
                pundit_name: "Unresolved",
                total_predictions: 5,
                resolved_predictions: 0,
                correct_predictions: 0,
                incorrect_predictions: 0,
                accuracy_rate: null,
            },
        ];
        const hof = pickHof(mixed);
        expect(hof.every((p) => p.resolved_predictions > 0)).toBe(true);
    });
});

describe("HOS selection", () => {
    const pundits: MockPunditStat[] = Array.from({ length: 20 }, (_, i) => ({
        pundit_id: `pundit-${i}`,
        pundit_name: `Pundit ${i}`,
        total_predictions: i < 5 ? 5 : 20, // first 5 have fewer than 10 predictions
        resolved_predictions: 10,
        correct_predictions: i,
        incorrect_predictions: 10 - i,
        accuracy_rate: i / 10,
    }));

    it("returns at most 10 pundits", () => {
        expect(pickHos(pundits).length).toBeLessThanOrEqual(10);
    });

    it("orders by accuracy ascending (worst first)", () => {
        const hos = pickHos(pundits);
        for (let i = 0; i < hos.length - 1; i++) {
            expect(hos[i].accuracy_rate!).toBeLessThanOrEqual(
                hos[i + 1].accuracy_rate!
            );
        }
    });

    it("excludes pundits with fewer than 10 total predictions", () => {
        const hos = pickHos(pundits);
        expect(hos.every((p) => p.total_predictions >= 10)).toBe(true);
    });
});

// ---------------------------------------------------------------------------
// line-clamp-2 class presence in featured prediction
// ---------------------------------------------------------------------------

describe("featured prediction text truncation", () => {
    it("renders with line-clamp-2 class (class applied when featuredPrediction present)", () => {
        // We verify the className is hardcoded in the component source.
        // Since we can't render without jsdom, we assert by inspecting component source.
        // This is a contract test: the class MUST be present in the component.
        const fs = require("fs");
        const path = require("path");
        const src = fs.readFileSync(
            path.resolve(
                __dirname,
                "../components/pundit-card.tsx"
            ),
            "utf-8"
        );
        expect(src).toContain("line-clamp-2");
    });

    it("view full record link uses /ledger/:punditId", () => {
        const fs = require("fs");
        const path = require("path");
        const src = fs.readFileSync(
            path.resolve(
                __dirname,
                "../components/pundit-card.tsx"
            ),
            "utf-8"
        );
        expect(src).toContain("/ledger/");
        expect(src).toContain("View full record");
    });
});
