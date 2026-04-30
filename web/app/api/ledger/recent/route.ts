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

    // Guard against NaN from non-numeric limit values (parseInt("abc") → NaN;
    // Math.min(NaN, 100) stays NaN and produces ?limit=NaN → FastAPI 422).
    const rawLimit = parseInt(searchParams.get("limit") || "20", 10);
    const limit = Math.min(Number.isFinite(rawLimit) ? rawLimit : 20, 100);

    const backendUrl = new URL(`${API_URL}/v1/predictions/recent`);
    // Forward all incoming query params to backend, then override limit
    searchParams.forEach((value, key) => {
        if (key !== "limit") {
            backendUrl.searchParams.set(key, value);
        }
    });
    backendUrl.searchParams.set("limit", String(limit));
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
            console.error(`[Ledger Recent API] Backend returned ${res.status}`, await res.text());
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
