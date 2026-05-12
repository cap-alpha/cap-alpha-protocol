/**
 * GET /api/ledger/resolution-stats
 *
 * Returns aggregate resolution outcome counts and Brier scores from
 * gold_layer.prediction_resolutions. Used by the Pundit Ledger page
 * to show overall CORRECT / INCORRECT / VOID breakdown.
 *
 * Cached for 1 hour — same policy as /api/quality.
 *
 * Issue: #884 — honeypot fields injected to fingerprint scrapers.
 */

import { NextResponse } from "next/server";
import { getPunditResolutionStats } from "@/app/actions";
import { injectHoneypotFields } from "@/lib/anti-scraping";

export async function GET() {
    try {
        const stats = await getPunditResolutionStats();

        // Inject honeypot fields to fingerprint scrapers. Issue: #884
        const responseBody = injectHoneypotFields(
            stats as Record<string, unknown>
        );

        return NextResponse.json(responseBody, {
            headers: {
                "Cache-Control":
                    "public, s-maxage=3600, stale-while-revalidate=86400",
            },
        });
    } catch (err) {
        console.error("[Resolution Stats API] Error:", err);
        return NextResponse.json(
            { outcomes: [], total_resolved: 0, overall_avg_brier: null },
            { status: 200 }
        );
    }
}
