/**
 * Server-side helper for fetching recent resolved predictions.
 *
 * Mirrors the pattern from ledger-server.ts / leaderboard-fallback.ts.
 * Tries the backend API first; falls back to the static JSON snapshot
 * when the backend is unavailable (issue #960).
 */

import { getApiUrl, getAuthHeader } from "./ledger-server";
import snapshot from "./data/recent-resolutions-snapshot.json";

export interface Resolution {
    pundit_name: string;
    pundit_id: string;
    extracted_claim: string;
    binary_correct: boolean;
    resolved_at: string;
    brier_score: number | null;
}

export interface SSRResolutionsResult {
    resolutions: Resolution[];
    fallback: boolean;
}

function getFallbackResolutions(limit: number): SSRResolutionsResult {
    return {
        resolutions: (snapshot.resolutions as Resolution[]).slice(0, limit),
        fallback: true,
    };
}

/**
 * Fetches the most recent resolved predictions server-side.
 *
 * - Tries `${API_URL}/v1/predictions/recent?limit=${limit}` (5-minute revalidate).
 * - Falls back to snapshot on any non-2xx response or network error.
 *
 * @param limit - Number of resolutions to return (default 5).
 */
export async function fetchRecentResolutionsSSR(
    limit = 5
): Promise<SSRResolutionsResult> {
    try {
        const apiUrl = await getApiUrl();
        const backendUrl = new URL(`${apiUrl}/v1/predictions/recent`);
        backendUrl.searchParams.set("limit", String(limit));

        const res = await fetch(backendUrl.toString(), {
            headers: { Accept: "application/json", ...getAuthHeader() },
            next: { revalidate: 300 }, // 5-minute revalidate window
        });

        if (!res.ok) {
            console.error(
                `[fetchRecentResolutionsSSR] Backend returned ${res.status} — serving snapshot fallback (issue #960)`
            );
            return getFallbackResolutions(limit);
        }

        const data = await res.json();
        const resolutions: Resolution[] = (data.resolutions ?? data.items ?? []).map(
            (r: Record<string, unknown>) => ({
                pundit_name: String(r.pundit_name ?? ""),
                pundit_id: String(r.pundit_id ?? ""),
                extracted_claim: String(r.extracted_claim ?? r.claim ?? ""),
                binary_correct: Boolean(r.binary_correct),
                resolved_at: String(r.resolved_at ?? ""),
                brier_score: r.brier_score != null ? Number(r.brier_score) : null,
            })
        );

        return { resolutions, fallback: false };
    } catch (err) {
        console.error(
            "[fetchRecentResolutionsSSR] Network/timeout error — serving snapshot fallback (issue #960):",
            err
        );
        return getFallbackResolutions(limit);
    }
}
