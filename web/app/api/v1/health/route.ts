/**
 * GET /api/v1/health
 *
 * Authenticated health-check endpoint demonstrating the full
 * API key -> tier resolution -> rate limiting flow.
 */
import { NextRequest, NextResponse } from "next/server";
import { withApiAuth } from "@/lib/api-middleware";

export const GET = withApiAuth(async (_req: NextRequest, ctx) => {
    return NextResponse.json({
        status: "ok",
        tier: ctx.tier,
        timestamp: new Date().toISOString(),
    });
});

export const runtime = "edge";
