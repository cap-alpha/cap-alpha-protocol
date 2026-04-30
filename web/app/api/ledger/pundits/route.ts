import { NextResponse } from "next/server";

// Server-only env var — non-NEXT_PUBLIC_ so it is never bundled into the client.
// Fail fast if unset so production errors are obvious rather than silently falling
// back to localhost and returning empty data.
const API_URL = process.env.INTERNAL_API_URL;

export async function GET(req: Request) {
    if (!API_URL) {
        console.error("[Ledger Pundits API] INTERNAL_API_URL is not set");
        return NextResponse.json({ error: "API URL not configured" }, { status: 500 });
    }

    const { searchParams } = new URL(req.url);
    const sport = searchParams.get("sport");

    // Build backend URL, forwarding the sport filter if provided
    const backendUrl = new URL(`${API_URL}/v1/pundits/`);
    if (sport) {
        backendUrl.searchParams.set("sport", sport);
    }

    try {
        const res = await fetch(backendUrl.toString(), {
            headers: {
                Accept: "application/json",
            },
        });

        if (!res.ok) {
            console.error(
                `[Ledger Pundits API] Backend returned ${res.status}`,
                await res.text()
            );
            return NextResponse.json({ pundits: [] }, { status: 502 });
        }

        const data = await res.json();

        // Map backend field names (total_predictions/resolved_count/correct_count)
        // to the shape the UI components expect.
        const pundits = (data.pundits || []).map((p: Record<string, unknown>) => ({
            ...p,
            // UI legacy aliases
            resolved_predictions:
                (p.resolved_count as number) ??
                (p.resolved_predictions as number) ??
                0,
            correct_predictions:
                (p.correct_count as number) ??
                (p.correct_predictions as number) ??
                0,
            incorrect_predictions:
                typeof p.resolved_count === "number" && typeof p.correct_count === "number"
                    ? p.resolved_count - p.correct_count
                    : (p.incorrect_count as number) ??
                      (p.incorrect_predictions as number) ??
                      0,
        }));

        return NextResponse.json({ pundits });
    } catch (err) {
        const errorMsg = err instanceof Error ? err.message : String(err);
        console.error("[Ledger Pundits API] Backend fetch error:", {
            error: errorMsg,
            backendUrl: API_URL,
        });
        return NextResponse.json({ pundits: [] }, { status: 502 });
    }
}
