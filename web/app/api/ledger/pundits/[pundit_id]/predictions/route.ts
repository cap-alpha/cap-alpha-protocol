import { NextResponse } from "next/server";
import { isPro, FREE_PREDICTION_CAP } from "@/lib/tier";
import { getAuthHeader, API_URL } from "@/lib/ledger-server";


export async function GET(
    req: Request,
    { params }: { params: { pundit_id: string } }
) {
    const { pundit_id } = params;
    const { searchParams } = new URL(req.url);
    const page = searchParams.get("page") ?? "1";
    const page_size = searchParams.get("page_size") ?? "20";
    const status = searchParams.get("status");

    let url = `${API_URL}/v1/pundits/${encodeURIComponent(pundit_id)}/predictions?page=${page}&page_size=${page_size}`;
    if (status) url += `&status=${encodeURIComponent(status)}`;

    try {
        const res = await fetch(url, {
            headers: { Accept: "application/json", ...getAuthHeader() },
        });

        if (res.status === 404) {
            return NextResponse.json({ error: "Pundit not found" }, { status: 404 });
        }
        if (!res.ok) {
            console.error(`[Pundit Predictions API] Backend returned ${res.status}`);
            return NextResponse.json({ predictions: [], total: 0, pages: 1, page: 1 });
        }

        const data = await res.json();

        // Apply free-tier prediction cap — silently return at most FREE_PREDICTION_CAP
        // rows and signal to the client via header + meta field so the UI can render
        // the blur/upgrade prompt. Pro users receive the full list.
        // Issue: #771 Phase 1
        const proUser = await isPro();
        if (!proUser && Array.isArray(data.predictions) && data.predictions.length > FREE_PREDICTION_CAP) {
            const cappedData = {
                ...data,
                predictions: data.predictions.slice(0, FREE_PREDICTION_CAP),
                meta: {
                    ...(data.meta ?? {}),
                    capped: true,
                    cap_limit: FREE_PREDICTION_CAP,
                },
            };
            return NextResponse.json(cappedData, {
                headers: { "X-Predictions-Capped": "true" },
            });
        }

        return NextResponse.json(data);
    } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        console.error("[Pundit Predictions API] Fetch error:", msg);
        return NextResponse.json({ predictions: [], total: 0, pages: 1, page: 1 });
    }
}
