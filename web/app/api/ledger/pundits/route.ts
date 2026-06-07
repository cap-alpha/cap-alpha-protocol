import { NextResponse } from "next/server";
import {
    injectHoneypotFields,
    enforcePaginationLimit,
    logBlockedRequest,
    LEDGER_MAX_LIMIT,
} from "@/lib/anti-scraping";
import { getApiUrl, normalizePundit } from "@/lib/ledger-server";
import { getFallbackPundits } from "@/lib/leaderboard-fallback";

// Include x-api-key when the internal key is configured so the Cloud Run
// backend (dependencies=[Depends(verify_api_key)]) accepts the request and
// serves live data. Omitting it gracefully falls back to snapshot.
function getBackendHeaders(): Record<string, string> {
    const key = process.env.CAP_ALPHA_INTERNAL_API_KEY;
    return key
        ? { Accept: "application/json", "x-api-key": key }
        : { Accept: "application/json" };
}

/**
 * Server-side helper for SSR — fetches top pundits directly from the backend
 * without going through the anti-scraping proxy layer.  Used by app/page.tsx
 * to populate `initialPundits` so the homepage renders real data on the first
 * HTML response (no blank spinner on FCP).
 *
 * @param sport - sport filter ("nfl" | "nba" | "mlb") or undefined for all
 * @param limit - maximum rows to return (default 20)
 */
export async function fetchPunditsSSR(
    sport?: string,
    limit = 20
): Promise<Record<string, unknown>[]> {
    try {
        const backendUrl = new URL(`${getApiUrl()}/v1/pundits/`);
        backendUrl.searchParams.set("limit", String(limit));
        backendUrl.searchParams.set("sort", "accuracy");
        if (sport && sport !== "ALL") {
            backendUrl.searchParams.set("sport", sport.toLowerCase());
        }
        const res = await fetch(backendUrl.toString(), {
            headers: { Accept: "application/json" },
            next: { revalidate: 300 }, // 5-minute ISR — matches page.tsx revalidate
        });
        if (!res.ok) {
            console.error(`[fetchPunditsSSR] Backend returned ${res.status}`);
            return [];
        }
        const data = await res.json();
        return (data.pundits || []).map(normalizePundit);
    } catch (err) {
        console.error("[fetchPunditsSSR] Error:", err);
        return [];
    }
}

export async function GET(req: Request) {
    const { searchParams } = new URL(req.url);

    // Enforce pagination limit: reject requests asking for more than LEDGER_MAX_LIMIT rows.
    // Issue: #884
    const limitCheck = enforcePaginationLimit(
        searchParams.get("limit"),
        /* defaultLimit */ 20
    );
    if (!limitCheck.valid) {
        const ip =
            req.headers.get("x-real-ip") ??
            req.headers.get("x-forwarded-for")?.split(",")[0].trim() ??
            "unknown";
        logBlockedRequest({
            timestamp: new Date().toISOString(),
            ip,
            user_agent: req.headers.get("user-agent") ?? "",
            endpoint: "/api/ledger/pundits",
            block_reason: "limit_exceeded",
        });
        return NextResponse.json(
            {
                error: limitCheck.error,
                max_limit: LEDGER_MAX_LIMIT,
            },
            { status: 400 }
        );
    }

    // Build backend URL, forwarding all query params
    const apiUrl = await getApiUrl();
    const backendUrl = new URL(`${apiUrl}/v1/pundits/`);
    // Forward all incoming query params to backend (with enforced limit)
    searchParams.forEach((value, key) => {
        if (key !== "limit") {
            backendUrl.searchParams.set(key, value);
        }
    });
    backendUrl.searchParams.set("limit", String(limitCheck.limit));
    // Remove ALL sentinel so backend receives no sport filter
    if (backendUrl.searchParams.get("sport") === "ALL") {
        backendUrl.searchParams.delete("sport");
    }

    try {
        // Cache the backend fetch for 5 min so the expensive upstream call is
        // deduplicated across requests, while the response stays uncached at the
        // edge.  We cannot use s-maxage here: injectHoneypotFields is time-seeded
        // (see web/lib/anti-scraping.ts), so caching the response body would serve
        // identical honeypot values to every visitor, defeating per-request
        // fingerprinting.
        const res = await fetch(backendUrl.toString(), {
            headers: getBackendHeaders(),
            next: { revalidate: 300 },
        });

        if (!res.ok) {
            console.error(
                `[Ledger API] Backend returned ${res.status} — serving snapshot fallback (issue #960)`,
                await res.text()
            );
            const sport = searchParams.get("sport");
            const fallbackPayload = getFallbackPundits(sport, limitCheck.limit);
            const pundits = fallbackPayload.pundits.map(normalizePundit as (p: unknown) => Record<string, unknown>);
            const responseBody = injectHoneypotFields({ pundits, fallback: true });
            return NextResponse.json(responseBody);
        }

        const data = await res.json();
        const pundits = (data.pundits || []).map(normalizePundit);

        // Inject honeypot fields at the top level to fingerprint scrapers.
        // Issue: #884
        const responseBody = injectHoneypotFields({ pundits });

        return NextResponse.json(responseBody);
    } catch (err) {
        const errorMsg = err instanceof Error ? err.message : String(err);
        console.error("[Ledger Pundits API] Backend fetch error — serving snapshot fallback (issue #960):", {
            error: errorMsg,
            backendUrl: apiUrl,
        });
        const sport = searchParams.get("sport");
        const fallbackPayload = getFallbackPundits(sport, limitCheck.limit);
        const pundits = fallbackPayload.pundits.map(normalizePundit as (p: unknown) => Record<string, unknown>);
        const responseBody = injectHoneypotFields({ pundits, fallback: true });
        return NextResponse.json(responseBody);
    }
}
