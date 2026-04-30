import { NextResponse } from "next/server";

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

export async function GET(req: Request) {
    const { searchParams } = new URL(req.url);

    // Build backend URL, forwarding all query params
    const backendUrl = new URL(`${API_URL}/v1/pundits/`);
    // Forward all incoming query params to backend
    searchParams.forEach((value, key) => {
        backendUrl.searchParams.set(key, value);
    });
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
