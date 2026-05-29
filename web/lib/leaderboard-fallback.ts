/**
 * Snapshot fallback for the Pundit Leaderboard.
 *
 * When the Cloud Run backend is unavailable (e.g. billing suspended, issue #960),
 * this module serves a static JSON snapshot generated from pipeline/data/local.duckdb.
 * Data as of April 2025 — 42 predictions + 42 resolutions across 13 NFL pundits.
 */

import snapshot from "./data/leaderboard-snapshot.json";

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

    const filtered =
        !sport || sport.toUpperCase() === "ALL"
            ? allPundits
            : allPundits.filter(
                  (p) => p.sport.toUpperCase() === sport.toUpperCase()
              );

    const sorted = [...filtered].sort((a, b) => {
        const aRate = a.accuracy_rate ?? -1;
        const bRate = b.accuracy_rate ?? -1;
        if (bRate !== aRate) return bRate - aRate;
        return b.total_predictions - a.total_predictions;
    });

    return {
        pundits: sorted.slice(0, limit),
        fallback: true,
        fallback_metadata: snapshot.snapshot_metadata,
    };
}
