import { NextResponse } from "next/server";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function GET(
    _req: Request,
    { params }: { params: { pundit_id: string } }
) {
    const { pundit_id } = params;
    try {
        const res = await fetch(`${API_URL}/v1/pundits/${encodeURIComponent(pundit_id)}`, {
            headers: { Accept: "application/json" },
        });

        if (res.status === 404) {
            return NextResponse.json({ error: "Pundit not found" }, { status: 404 });
        }
        if (!res.ok) {
            console.error(`[Pundit API] Backend returned ${res.status}`);
            return NextResponse.json({ error: "Backend error" }, { status: 502 });
        }

        const data = await res.json();
        return NextResponse.json(data);
    } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        console.error("[Pundit API] Fetch error:", msg);
        return NextResponse.json({ error: "Internal error" }, { status: 500 });
    }
}
