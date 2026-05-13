import { NextResponse } from "next/server";
import {
    injectHoneypotFields,
    enforcePaginationLimit,
    logBlockedRequest,
    LEDGER_MAX_LIMIT,
} from "@/lib/anti-scraping";

const API_URL =
    process.env.API_URL ||
    process.env.NEXT_PUBLIC_API_URL ||
    "https://pundit-ledger-api-wvhvx2muna-uc.a.run.app";

// Normalize backend field names (resolved_count / correct_count) to the
// legacy web contract (resolved_predictions / correct_predictions /
// incorrect_predictions) so all frontend consumers stay consistent.
function normalizePundit(p: Record<string, unknown>): Record<string, unknown> {
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
        const backendUrl = new URL(`${API_URL}/v1/pundits/`);
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
    const backendUrl = new URL(`${API_URL}/v1/pundits/`);
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
        const res = await fetch(backendUrl.toString(), {
            headers: {
                "Accept": "application/json",
            },
        });

        if (!res.ok) {
            console.error(`[Ledger API] Backend returned ${res.status}`, await res.text());
            return NextResponse.json({ pundits: [] }, { status: 502 });
        }

        const data = await res.json();
        const pundits = (data.pundits || []).map(normalizePundit);

        // Inject honeypot fields at the top level to fingerprint scrapers.
        // Issue: #884
        const responseBody = injectHoneypotFields({ pundits });
        return NextResponse.json(responseBody);
    } catch (err) {
        const errorMsg = err instanceof Error ? err.message : String(err);
        console.error("[Ledger Pundits API] Backend fetch error:", {
            error: errorMsg,
            backendUrl: API_URL,
        });
        return NextResponse.json({ pundits: [] }, { status: 502 });
    }
}
