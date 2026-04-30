import { NextResponse } from "next/server";

// Server-only env var — fail fast if unset so production issues are not
// masked as empty-200 responses.
const API_URL = process.env.INTERNAL_API_URL;

export async function GET(req: Request) {
    if (!API_URL) {
        console.error("[Ledger Recent API] INTERNAL_API_URL is not set");
        return NextResponse.json({ error: "API URL not configured" }, { status: 500 });
    }

    const { searchParams } = new URL(req.url);
    const parsed = parseInt(searchParams.get("limit") ?? "");
    // Guard against NaN (e.g. ?limit=foo) — fall back to default before clamping.
    const limit = Number.isFinite(parsed) ? Math.min(parsed, 100) : 20;
    const sport = searchParams.get("sport");
    const punditId = searchParams.get("pundit_id");

    const backendUrl = new URL(`${API_URL}/v1/predictions/recent`);
    backendUrl.searchParams.set("limit", String(limit));
    if (sport && sport !== "ALL") {
        backendUrl.searchParams.set("sport", sport);
    }
    if (punditId) backendUrl.searchParams.set("pundit_id", punditId);

    try {
        const res = await fetch(backendUrl.toString(), {
            headers: {
                Accept: "application/json",
            },
        });

        if (!res.ok) {
            console.error(
                `[Ledger Recent API] Backend returned ${res.status}`,
                await res.text()
            );
            return NextResponse.json({ predictions: [] }, { status: 502 });
        }

        const data = await res.json();
        return NextResponse.json({ predictions: data.predictions || [] });
    } catch (err) {
        const errorMsg = err instanceof Error ? err.message : String(err);
        console.error("[Ledger Recent API] Backend fetch error:", {
            error: errorMsg,
            backendUrl: API_URL,
        });
        return NextResponse.json({ predictions: [] }, { status: 502 });
    }
}
