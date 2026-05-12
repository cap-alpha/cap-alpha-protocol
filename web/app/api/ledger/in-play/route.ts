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

/**
 * GET /api/ledger/in-play
 *
 * Returns predictions that are currently PENDING or recently resolved
 * (within the last 24 hours — "just resolved" window).
 *
 * Proxies to /v1/predictions/?status=PENDING on the FastAPI backend,
 * with OR on recently-resolved predictions for the "just resolved" UX.
 *
 * Cache: s-maxage=300, stale-while-revalidate=900 (5 min fresh, 15 min stale).
 *
 * Query params forwarded to backend:
 *   - sport: "NFL" | "NBA" | "MLB" etc.
 *   - category: "game_outcome" | "trade" | "draft_pick" | etc.
 *   - pundit_name: substring filter
 *   - limit: max rows (default 50, max 100)
 *   - count_only: "1" → return { count: N } only (for navbar badge)
 *
 * Issue: #770
 */
export async function GET(req: Request) {
    const { searchParams } = new URL(req.url);

    // count_only shortcut for navbar badge — no pagination needed
    const countOnly = searchParams.get("count_only") === "1";

    const limitCheck = enforcePaginationLimit(
        searchParams.get("limit"),
        /* defaultLimit */ 50
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
            endpoint: "/api/ledger/in-play",
            block_reason: "limit_exceeded",
        });
        return NextResponse.json(
            { error: limitCheck.error, max_limit: LEDGER_MAX_LIMIT },
            { status: 400 }
        );
    }

    // Build backend URL for PENDING predictions
    const backendUrl = new URL(`${API_URL}/v1/predictions/`);
    backendUrl.searchParams.set("status", "PENDING");
    backendUrl.searchParams.set("limit", String(limitCheck.limit));

    // Forward filters
    const sport = searchParams.get("sport");
    if (sport && sport !== "ALL") {
        backendUrl.searchParams.set("sport", sport);
    }
    const category = searchParams.get("category");
    if (category) {
        backendUrl.searchParams.set("category", category);
    }
    const punditName = searchParams.get("pundit_name");
    if (punditName) {
        backendUrl.searchParams.set("pundit_name", punditName);
    }

    try {
        const res = await fetch(backendUrl.toString(), {
            headers: { Accept: "application/json" },
            // Revalidate every 5 minutes at the edge
            next: { revalidate: 300 },
        } as RequestInit);

        if (!res.ok) {
            console.error(
                `[Ledger In-Play API] Backend returned ${res.status}`,
                await res.text().catch(() => "")
            );
            return NextResponse.json(
                { predictions: [], count: 0 },
                { status: 502 }
            );
        }

        const data = (await res.json()) as { predictions?: unknown[] };
        const predictions = data.predictions || [];

        if (countOnly) {
            return NextResponse.json(
                { count: predictions.length },
                {
                    headers: {
                        "Cache-Control": "public, s-maxage=300, stale-while-revalidate=900",
                    },
                }
            );
        }

        const responseBody = injectHoneypotFields({
            predictions,
        });

        return NextResponse.json(responseBody, {
            headers: {
                "Cache-Control": "public, s-maxage=300, stale-while-revalidate=900",
            },
        });
    } catch (err) {
        const errorMsg = err instanceof Error ? err.message : String(err);
        console.error("[Ledger In-Play API] Backend fetch error:", {
            error: errorMsg,
            backendUrl: API_URL,
        });
        return NextResponse.json({ predictions: [], count: 0 }, { status: 502 });
    }
}
