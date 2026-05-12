/**
 * Static lookup table for known sports calendar deadlines.
 * Used by resolution-window.ts for Phase 1 heuristic derivation.
 *
 * Phase 2 will replace this with server-side SportsDataIO lookups.
 */

export interface SportDeadline {
    eventName: string;
    /** ISO date string, e.g. "2025-11-04" */
    date: string;
    sport: string;
    year: number;
}

/**
 * NFL / NBA / MLB / NHL known deadlines for resolution derivation.
 *
 * Trade deadlines, draft dates, and season end dates.
 * Covers 2025 and 2026 seasons.
 */
export const SPORT_DEADLINES: SportDeadline[] = [
    // NFL
    { sport: "NFL", year: 2025, eventName: "Trade Deadline", date: "2025-11-04" },
    { sport: "NFL", year: 2025, eventName: "NFL Draft", date: "2026-04-23" },
    { sport: "NFL", year: 2026, eventName: "Trade Deadline", date: "2026-11-03" },
    { sport: "NFL", year: 2026, eventName: "NFL Draft", date: "2027-04-22" },

    // NBA
    { sport: "NBA", year: 2025, eventName: "Trade Deadline", date: "2026-02-05" },
    { sport: "NBA", year: 2025, eventName: "NBA Draft", date: "2026-06-25" },
    { sport: "NBA", year: 2024, eventName: "Trade Deadline", date: "2025-02-06" },

    // MLB
    { sport: "MLB", year: 2025, eventName: "Trade Deadline", date: "2025-07-31" },
    { sport: "MLB", year: 2026, eventName: "Trade Deadline", date: "2026-07-31" },

    // NHL
    { sport: "NHL", year: 2025, eventName: "Trade Deadline", date: "2025-03-07" },
    { sport: "NHL", year: 2026, eventName: "Trade Deadline", date: "2026-03-06" },
];

/**
 * Look up the trade deadline for a given sport + season year.
 * Returns undefined if not found in the static table.
 */
export function getTradeDeadline(
    sport: string,
    seasonYear: number
): SportDeadline | undefined {
    return SPORT_DEADLINES.find(
        (d) =>
            d.sport.toUpperCase() === sport.toUpperCase() &&
            d.year === seasonYear &&
            d.eventName === "Trade Deadline"
    );
}

/**
 * Look up the draft date for a given sport + season year.
 * Returns undefined if not found in the static table.
 */
export function getDraftDeadline(
    sport: string,
    seasonYear: number
): SportDeadline | undefined {
    return SPORT_DEADLINES.find(
        (d) =>
            d.sport.toUpperCase() === sport.toUpperCase() &&
            d.year === seasonYear &&
            d.eventName.includes("Draft")
    );
}
