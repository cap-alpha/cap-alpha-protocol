/**
 * Resolution window derivation for pending predictions.
 *
 * Phase 1: heuristic approach — no schema migration required.
 * Phase 2 will add `expected_resolution_date DATE` to prediction_ledger
 * and sort/filter server-side.
 *
 * Issue: #770
 */

import { getTradeDeadline, getDraftDeadline } from "@/lib/sport-events";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type ResolutionWindow =
    | { kind: "exact_date"; date: string; label: string }
    | { kind: "event"; eventName: string; estDate?: string }
    | { kind: "season"; year: number }
    | { kind: "fuzzy"; hint: string };

// Minimal fields we need from a prediction row
export interface PredictionResolutionInput {
    claim_category: string;
    sport: string;
    season_year: number | null;
    raw_assertion_text?: string | null;
    extracted_claim?: string | null;
    target_team?: string | null;
}

// ---------------------------------------------------------------------------
// Regex patterns for explicit dates in raw text
// ---------------------------------------------------------------------------

/**
 * Conservative date extraction patterns.
 * Only matches obvious "by <date>" / "before <date>" / "before week N" patterns.
 * We keep this narrow to avoid false positives.
 */
const EXPLICIT_DATE_PATTERNS: Array<{
    re: RegExp;
    toLabel: (m: RegExpMatchArray) => string | null;
}> = [
    // "by November 4" / "by Nov 4" / "by Nov. 4"
    {
        re: /\bby\s+(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)[.\s]+(\d{1,2})(?:\s*,?\s*(\d{4}))?/i,
        toLabel(m) {
            const month = m[1];
            const day = m[2];
            const year = m[3] || new Date().getFullYear().toString();
            const parsed = new Date(`${month} ${day}, ${year}`);
            if (isNaN(parsed.getTime())) return null;
            return parsed.toLocaleDateString("en-US", {
                month: "short",
                day: "numeric",
                year: "numeric",
            });
        },
    },
    // "before November 1" / "before the deadline Nov 4"
    {
        re: /\bbefore\s+(?:the\s+\w+\s+)?(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)[.\s]+(\d{1,2})(?:\s*,?\s*(\d{4}))?/i,
        toLabel(m) {
            const month = m[1];
            const day = m[2];
            const year = m[3] || new Date().getFullYear().toString();
            const parsed = new Date(`${month} ${day}, ${year}`);
            if (isNaN(parsed.getTime())) return null;
            return parsed.toLocaleDateString("en-US", {
                month: "short",
                day: "numeric",
                year: "numeric",
            });
        },
    },
    // "before week 10" — maps to label only (no date calc in Phase 1)
    {
        re: /\bbefore\s+week\s+(\d{1,2})\b/i,
        toLabel(m) {
            return `Before Week ${m[1]}`;
        },
    },
];

/**
 * Attempt to extract an explicit date or timeframe from raw assertion text.
 * Returns null if no clear date reference is found.
 */
function extractExplicitDate(
    rawText: string | null | undefined
): { label: string } | null {
    if (!rawText) return null;
    for (const { re, toLabel } of EXPLICIT_DATE_PATTERNS) {
        const m = rawText.match(re);
        if (m) {
            const label = toLabel(m);
            if (label) return { label };
        }
    }
    return null;
}

// ---------------------------------------------------------------------------
// Main derivation function
// ---------------------------------------------------------------------------

/**
 * Derive a ResolutionWindow from a prediction row.
 *
 * Derivation rules:
 * 1. trade → trade deadline lookup by sport + season_year
 * 2. draft_pick → draft date lookup by sport + season_year
 * 3. game_outcome → season (Phase 2: next-event API)
 * 4. player_performance / injury / contract → season or fuzzy
 * 5. Override: if raw_assertion_text contains an explicit date → exact_date
 *
 * The exact_date override runs AFTER category matching so it only surfaces
 * when a date is actually stated — otherwise we fall back to the category rule.
 */
export function deriveResolutionWindow(
    prediction: PredictionResolutionInput
): ResolutionWindow {
    const { claim_category, season_year, raw_assertion_text } = prediction;
    // Defensive: a transient backend blip can produce rows with a missing or
    // null `sport` field. Coerce to "" so the .toUpperCase() calls below (and
    // in getTradeDeadline/getDraftDeadline) never throw during render — an
    // unguarded throw here bubbles to the full-page error boundary instead of
    // degrading gracefully within the In-Play tab.
    const sport = prediction.sport || "";

    // --- Override: explicit date in text (conservative regex) ---
    const explicit = extractExplicitDate(raw_assertion_text);

    if (claim_category === "trade") {
        if (season_year) {
            const deadline = getTradeDeadline(sport, season_year);
            if (deadline) {
                if (explicit) {
                    return {
                        kind: "exact_date",
                        date: deadline.date,
                        label: explicit.label,
                    };
                }
                return {
                    kind: "event",
                    eventName: `${sport.toUpperCase()} Trade Deadline`,
                    estDate: deadline.date,
                };
            }
        }
        if (explicit) {
            return { kind: "exact_date", date: "", label: explicit.label };
        }
        return { kind: "fuzzy", hint: "By trade deadline" };
    }

    if (claim_category === "draft_pick") {
        if (season_year) {
            const draft = getDraftDeadline(sport, season_year);
            if (draft) {
                if (explicit) {
                    return { kind: "exact_date", date: draft.date, label: explicit.label };
                }
                return {
                    kind: "event",
                    eventName: draft.eventName,
                    estDate: draft.date,
                };
            }
        }
        if (explicit) {
            return { kind: "exact_date", date: "", label: explicit.label };
        }
        return { kind: "fuzzy", hint: "By draft" };
    }

    if (claim_category === "game_outcome") {
        if (explicit) {
            return { kind: "exact_date", date: "", label: explicit.label };
        }
        if (season_year) {
            return { kind: "season", year: season_year };
        }
        return { kind: "fuzzy", hint: "TBD" };
    }

    // player_performance, injury, contract — season or fuzzy
    if (explicit) {
        return { kind: "exact_date", date: "", label: explicit.label };
    }
    if (season_year) {
        return { kind: "season", year: season_year };
    }
    return { kind: "fuzzy", hint: "TBD" };
}

// ---------------------------------------------------------------------------
// Helpers for sorting / filtering by window proximity
// ---------------------------------------------------------------------------

/**
 * Convert a ResolutionWindow to an approximate Date for sorting.
 * Falls back to far-future date so fuzzy windows sort last.
 */
export function windowToSortDate(window: ResolutionWindow): Date {
    switch (window.kind) {
        case "exact_date":
            if (window.date) {
                const d = new Date(window.date);
                if (!isNaN(d.getTime())) return d;
            }
            // Label-only exact dates sort near-future (30 days)
            return new Date(Date.now() + 30 * 24 * 60 * 60 * 1000);
        case "event":
            if (window.estDate) {
                const d = new Date(window.estDate);
                if (!isNaN(d.getTime())) return d;
            }
            return new Date(Date.now() + 60 * 24 * 60 * 60 * 1000);
        case "season":
            return new Date(`${window.year}-12-31`);
        case "fuzzy":
            return new Date(Date.now() + 365 * 24 * 60 * 60 * 1000);
    }
}

/**
 * Resolution window bucket for UI filter pills.
 * Client-side only in Phase 1.
 */
export type WindowBucket = "week" | "month" | "season" | "all";

export function windowMatchesBucket(
    window: ResolutionWindow,
    bucket: WindowBucket
): boolean {
    if (bucket === "all") return true;
    const sortDate = windowToSortDate(window);
    const now = Date.now();
    const diff = sortDate.getTime() - now;
    const day = 24 * 60 * 60 * 1000;
    switch (bucket) {
        case "week":
            return diff <= 7 * day && diff >= -day;
        case "month":
            return diff <= 30 * day && diff >= -day;
        case "season":
            return diff <= 365 * day;
        default:
            return true;
    }
}
