/**
 * Server-side helpers for talking to the Pundit Prediction Ledger API.
 *
 * Discovery strategy:
 *   1. `API_URL` / `NEXT_PUBLIC_API_URL` env var (explicit override; highest priority)
 *   2. Production Cloud Run URL (default for cap-alpha.co traffic)
 *   3. `http://localhost:8000`, `http://localhost:8080` (laptop fallback for local dev)
 *
 * The first candidate that returns a non-5xx response to a probe within
 * PROBE_TIMEOUT_MS wins. The resolved URL is memoized for the Node process
 * lifetime so the probe cost is paid once per cold start, not per request.
 *
 * Behavior when all candidates fail: returns the production URL so downstream
 * fetches produce a consistent error message; the client UI's error state
 * (see PunditLeaderboardPreview) surfaces it.
 *
 * Fallback behavior (issue #960): when the backend is unreachable or returns a
 * 5xx error, `fetchPunditsSSR` returns the static JSON snapshot from
 * `web/lib/data/leaderboard-snapshot.json` rather than an empty array.
 *
 * Authentication (issue #960 follow-up): when `CAP_ALPHA_INTERNAL_API_KEY` is
 * set, every backend request includes `x-api-key` so the Cloud Run router
 * (dependencies=[Depends(verify_api_key)]) accepts it and serves live data.
 * If the env var is unset, the header is omitted and the snapshot fallback
 * catches any resulting 401/422 exactly as it does for 5xx errors.
 */

import { getFallbackPundits } from "./leaderboard-fallback";

const PRODUCTION_URL = "https://pundit-ledger-api-wvhvx2muna-uc.a.run.app";
const LOCALHOST_CANDIDATES = ["http://localhost:8000", "http://localhost:8080"];
const ENV_URL = process.env.API_URL || process.env.NEXT_PUBLIC_API_URL;
const PROBE_TIMEOUT_MS = 800;
const PROBE_PATH = "/v1/pundits/?limit=1";

/**
 * Returns the `x-api-key` header object when `CAP_ALPHA_INTERNAL_API_KEY` is
 * configured, or an empty object when not set (probe / dev / missing key).
 */
export function getAuthHeader(): Record<string, string> {
    const key = process.env.CAP_ALPHA_INTERNAL_API_KEY;
    return key ? { "x-api-key": key } : {};
}

let resolvedApiUrl: string | null = null;
let resolutionInFlight: Promise<string> | null = null;

async function probeUrl(url: string): Promise<boolean> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), PROBE_TIMEOUT_MS);
    try {
        const res = await fetch(`${url}${PROBE_PATH}`, {
            signal: controller.signal,
            headers: { Accept: "application/json", ...getAuthHeader() },
        });
        // Accept any non-5xx response (including 401/422 when key is missing in dev).
        return res.status < 500;
    } catch {
        return false;
    } finally {
        clearTimeout(timer);
    }
}

async function resolveApiUrl(): Promise<string> {
    if (resolvedApiUrl) return resolvedApiUrl;
    if (resolutionInFlight) return resolutionInFlight;

    resolutionInFlight = (async () => {
        // 1. Explicit override — trust the operator, no probe needed.
        if (ENV_URL) {
            console.log(`[ledger-server] Using API_URL from env: ${ENV_URL}`);
            resolvedApiUrl = ENV_URL;
            return ENV_URL;
        }

        // 2. Production first — the common case for deployed traffic.
        if (await probeUrl(PRODUCTION_URL)) {
            console.log(`[ledger-server] Using production API: ${PRODUCTION_URL}`);
            resolvedApiUrl = PRODUCTION_URL;
            return PRODUCTION_URL;
        }

        // 3. Localhost fallback — laptop dev when production is down or offline.
        for (const candidate of LOCALHOST_CANDIDATES) {
            if (await probeUrl(candidate)) {
                console.log(`[ledger-server] Production unreachable; using local API: ${candidate}`);
                resolvedApiUrl = candidate;
                return candidate;
            }
        }

        // 4. Everything failed. Return production URL so the downstream
        // fetch produces a single consistent error; don't memoize the
        // failure — next cold-start request will retry the probe.
        console.error("[ledger-server] No API reachable — falling back to production URL for error surface");
        resolutionInFlight = null;
        return PRODUCTION_URL;
    })();

    return resolutionInFlight;
}

/**
 * Returns the resolved API base URL. First call probes candidates; subsequent
 * calls return the memoized result. Always await — never use synchronously.
 */
export async function getApiUrl(): Promise<string> {
    return resolveApiUrl();
}

/**
 * @deprecated Use `await getApiUrl()` instead. Kept as a fallback for any
 * caller that needs the constant before probing has resolved — returns the
 * production URL unconditionally, which is the right default for SSR cold
 * starts on Vercel.
 */
export const API_URL = ENV_URL || PRODUCTION_URL;

export function normalizePundit(p: Record<string, unknown>): Record<string, unknown> {
    const resolvedCount = (p.resolved_count as number | undefined) ?? 0;
    const correctCount = (p.correct_count as number | undefined) ?? 0;
    return {
        ...p,
        resolved_predictions:
            p.resolved_predictions !== undefined
                ? p.resolved_predictions
                : resolvedCount,
        correct_predictions:
            p.correct_predictions !== undefined
                ? p.correct_predictions
                : correctCount,
        incorrect_predictions:
            p.incorrect_predictions !== undefined
                ? p.incorrect_predictions
                : resolvedCount - correctCount,
    };
}

export interface SSRPunditsResult {
    pundits: Record<string, unknown>[];
    fallback: boolean;
}

export async function fetchPunditsSSR(
    sport?: string,
    limit = 20
): Promise<SSRPunditsResult> {
    try {
        const apiUrl = await getApiUrl();
        const backendUrl = new URL(`${apiUrl}/v1/pundits/`);
        backendUrl.searchParams.set("limit", String(limit));
        backendUrl.searchParams.set("sort", "accuracy");
        if (sport && sport !== "ALL") {
            backendUrl.searchParams.set("sport", sport.toLowerCase());
        }
        const res = await fetch(backendUrl.toString(), {
            headers: { Accept: "application/json", ...getAuthHeader() },
            next: { revalidate: 300 },
        });
        if (!res.ok) {
            console.error(
                `[fetchPunditsSSR] Backend returned ${res.status} — serving snapshot fallback (issue #960)`
            );
            const fallbackPayload = getFallbackPundits(sport ?? null, limit);
            return { pundits: (fallbackPayload.pundits as unknown) as Record<string, unknown>[], fallback: true };
        }
        const data = await res.json();
        return {
            pundits: (data.pundits || []).map(normalizePundit),
            fallback: false,
        };
    } catch (err) {
        console.error(
            "[fetchPunditsSSR] Network/timeout error — serving snapshot fallback (issue #960):",
            err
        );
        const fallbackPayload = getFallbackPundits(sport ?? null, limit);
        return { pundits: (fallbackPayload.pundits as unknown) as Record<string, unknown>[], fallback: true };
    }
}
