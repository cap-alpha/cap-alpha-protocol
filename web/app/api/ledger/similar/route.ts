import { NextResponse } from "next/server";

const API_URL =
    process.env.API_URL ||
    process.env.NEXT_PUBLIC_API_URL ||
    "https://pundit-ledger-api-wvhvx2muna-uc.a.run.app";

export async function GET(req: Request) {
    const { searchParams } = new URL(req.url);

    const utteranceId = searchParams.get("utterance_id");
    if (!utteranceId) {
        return NextResponse.json({ similar: [] }, { status: 400 });
    }

    const rawLimit = parseInt(searchParams.get("limit") || "10", 10);
    const limit = Math.min(Number.isFinite(rawLimit) ? rawLimit : 10, 50);

    const backendUrl = new URL(`${API_URL}/v1/predictions/similar`);
    backendUrl.searchParams.set("utterance_id", utteranceId);
    backendUrl.searchParams.set("limit", String(limit));

    try {
        const res = await fetch(backendUrl.toString(), {
            headers: {
                Accept: "application/json",
            },
        });

        if (!res.ok) {
            console.error(
                `[Ledger Similar API] Backend returned ${res.status}`,
                await res.text()
            );
            return NextResponse.json({ similar: [] }, { status: 502 });
        }

        const data = await res.json() as { similar?: unknown[] };
        return NextResponse.json({ similar: data.similar ?? [] });
    } catch (err) {
        const errorMsg = err instanceof Error ? err.message : String(err);
        console.error("[Ledger Similar API] Backend fetch error:", {
            error: errorMsg,
            backendUrl: API_URL,
        });
        return NextResponse.json({ similar: [] }, { status: 502 });
    }
}
