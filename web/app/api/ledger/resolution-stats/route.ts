/**
 * GET /api/ledger/resolution-stats
 *
 * Returns aggregate resolution outcome counts and Brier scores from
 * gold_layer.prediction_resolutions. Used by the Pundit Ledger page
 * to show overall CORRECT / INCORRECT / VOID breakdown.
 *
 * Cached for 1 hour — same policy as /api/quality.
 */

import { NextResponse } from "next/server";
import { getPunditResolutionStats } from "@/app/actions";

export async function GET() {
    try {
        const stats = await getPunditResolutionStats();
        return NextResponse.json(stats, {
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
