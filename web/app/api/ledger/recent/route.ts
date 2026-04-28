import { NextResponse } from "next/server";

const API_URL =
    process.env.NEXT_PUBLIC_API_URL ||
    "https://pundit-ledger-api-wvhvx2muna-uc.a.run.app";

export async function GET(req: Request) {
    const { searchParams } = new URL(req.url);
    const parsed = parseInt(searchParams.get("limit") ?? "");
    const limit = Number.isFinite(parsed) ? Math.min(parsed, 100) : 20;

    try {
        const res = await fetch(
            `${API_URL}/v1/predictions/recent?limit=${limit}`,
            {
                headers: {
                    Accept: "application/json",
                },
            }
        );

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
