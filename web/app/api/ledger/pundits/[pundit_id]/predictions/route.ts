import { NextResponse } from "next/server";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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
            headers: { Accept: "application/json" },
        });

        if (res.status === 404) {
            return NextResponse.json({ error: "Pundit not found" }, { status: 404 });
        }
        if (!res.ok) {
            console.error(`[Pundit Predictions API] Backend returned ${res.status}`);
            return NextResponse.json({ predictions: [], total: 0, pages: 1, page: 1 });
        }

        const data = await res.json();
        return NextResponse.json(data);
    } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        console.error("[Pundit Predictions API] Fetch error:", msg);
        return NextResponse.json({ predictions: [], total: 0, pages: 1, page: 1 });
    }
}
