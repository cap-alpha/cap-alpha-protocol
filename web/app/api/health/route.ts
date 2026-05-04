/**
 * GET /api/health — Machine-readable health check for uptime monitors.
 *
 * Returns 200 {"status":"ok"} when the API is reachable.
 * Does not exercise BigQuery or external dependencies — those have their
 * own checks below. Uptime monitors (UptimeRobot, Vercel) ping this route.
 *
 * Issue #491
 */

export const runtime = "edge";
export const dynamic = "force-dynamic";

export async function GET() {
    return Response.json(
        {
            status: "ok",
            timestamp: new Date().toISOString(),
            version: process.env.NEXT_PUBLIC_COMMIT_SHA?.substring(0, 7) || "local",
        },
        {
            status: 200,
            headers: {
                "Cache-Control": "no-store",
                "X-Robots-Tag": "noindex",
            },
        }
    );
}
