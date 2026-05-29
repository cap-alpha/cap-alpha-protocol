/**
 * API route: GET /api/ledger/recent-resolutions
 *
 * Proxy to the backend `/v1/predictions/recent` endpoint with snapshot fallback.
 * Light public data — no honeypot injection needed (no scraping value here),
 * but we do enforce pagination limits consistent with the rest of the ledger API.
 *
 * Shape: { resolutions: Resolution[], fallback?: boolean }
 */

import { NextResponse } from "next/server";
import { enforcePaginationLimit, logBlockedRequest, LEDGER_MAX_LIMIT } from "@/lib/anti-scraping";
import { fetchRecentResolutionsSSR } from "@/lib/recent-resolutions-server";

export async function GET(req: Request) {
    const { searchParams } = new URL(req.url);

    const limitCheck = enforcePaginationLimit(
        searchParams.get("limit"),
        /* defaultLimit */ 5
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
            endpoint: "/api/ledger/recent-resolutions",
            block_reason: "limit_exceeded",
        });
        return NextResponse.json(
            { error: limitCheck.error, max_limit: LEDGER_MAX_LIMIT },
            { status: 400 }
        );
    }

    const { resolutions, fallback } = await fetchRecentResolutionsSSR(limitCheck.limit);
    return NextResponse.json({ resolutions, ...(fallback ? { fallback: true } : {}) });
}
