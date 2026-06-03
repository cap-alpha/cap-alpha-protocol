/**
 * Snapshot fallback for the Pundit Leaderboard.
 *
 * When the Cloud Run backend is unavailable (e.g. billing suspended, issue #960),
 * this module serves a static JSON snapshot generated from pipeline/data/local.duckdb.
 * Data as of April 2025 — 42 predictions + 42 resolutions across 13 NFL pundits.
 */

import snapshot from "./data/leaderboard-snapshot.json";
import { wilsonLowerBound } from "./wilson";

export interface PunditRecord {
    pundit_id: string;
    pundit_name: string;
    total_predictions: number;
    resolved_predictions: number;
    correct_predictions: number;
    incorrect_predictions: number;
    accuracy_rate: number | null;
    avg_brier_score: number | null;
    sport: string;
}

export interface PunditApiPayload {
    pundits: PunditRecord[];
    fallback: true;
    fallback_metadata: {
        generated_at: string;
        source: string;
        note: string;
    };
}

/**
 * Returns a snapshot-backed pundit list shaped like the live backend response.
 *
 * @param sport - Sport filter: "NFL" | "NBA" | "MLB" | "ALL" | null. Null or "ALL" returns all.
 * @param limit - Maximum number of records to return.
 */
export function getFallbackPundits(
    sport: string | null,
    limit: number
): PunditApiPayload {
    const allPundits = snapshot.pundits as PunditRecord[];

    // The snapshot only contains NFL pundits. Return empty for any other sport
    // so NBA/MLB tabs don't incorrectly show NFL names.
    const normalizedSport = sport ? sport.toUpperCase() : "ALL";
    if (normalizedSport !== "ALL" && normalizedSport !== "NFL") {
        return {
            pundits: [],
            fallback: true,
            fallback_metadata: snapshot.snapshot_metadata,
        };
    }

    const filtered =
        normalizedSport === "ALL"
            ? allPundits
            : allPundits.filter(
                  (p) => p.sport.toUpperCase() === normalizedSport
              );

    // Sort by Wilson score lower bound (95% CI) — not raw accuracy_rate.
    // A pundit with 1/1 (Wilson ≈ 0.025) ranks far below 9/10 (Wilson ≈ 0.55).
    const sorted = [...filtered].sort((a, b) => {
        const wbA = wilsonLowerBound(a.correct_predictions, a.resolved_predictions);
        const wbB = wilsonLowerBound(b.correct_predictions, b.resolved_predictions);
        return wbB - wbA;
    });

    return {
        pundits: sorted.slice(0, limit),
        fallback: true,
        fallback_metadata: snapshot.snapshot_metadata,
    };
}
