import { NextResponse } from "next/server";

const API_URL =
    process.env.NEXT_PUBLIC_API_URL ||
    "https://pundit-ledger-api-wvhvx2muna-uc.a.run.app";

export async function GET(req: Request) {
    const { searchParams } = new URL(req.url);
    const sport = searchParams.get("sport");

    const backendUrl = new URL(`${API_URL}/v1/pundits/`);
    if (sport && sport !== "ALL") {
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
                `[Ledger API] Backend returned ${res.status}`,
                await res.text()
            );
            return NextResponse.json({ pundits: [] }, { status: 502 });
        }

        const data = await res.json();
        // Backend returns resolved_count / correct_count — map to UI field names
        const mapped = (data.pundits || []).map((p: Record<string, unknown>) => ({
            ...p,
            resolved_predictions:
                (p.resolved_count as number) ??
                (p.resolved_predictions as number) ??
                0,
            correct_predictions:
                (p.correct_count as number) ??
                (p.correct_predictions as number) ??
                0,
            incorrect_predictions:
                (p.incorrect_count as number) ??
                (p.incorrect_predictions as number) ??
                0,
        }));
        return NextResponse.json({ pundits: mapped });
    } catch (err) {
        const errorMsg = err instanceof Error ? err.message : String(err);
        console.error("[Ledger API] Backend fetch error:", {
            error: errorMsg,
            backendUrl: API_URL,
        });
        return NextResponse.json({ pundits: [] }, { status: 502 });
    }
}
