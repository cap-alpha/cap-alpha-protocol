import { NextResponse } from "next/server";
import { API_URL } from "@/lib/ledger-server";


export async function GET(
    req: Request,
    { params }: { params: { entity_id: string } }
) {
    const { entity_id } = params;
    const { searchParams } = new URL(req.url);
    const page = searchParams.get("page") ?? "1";
    const page_size = searchParams.get("page_size") ?? "50";
    const status = searchParams.get("status");

    let url = `${API_URL}/v1/entities/${encodeURIComponent(entity_id)}/claims?page=${page}&page_size=${page_size}`;
    if (status) url += `&status=${encodeURIComponent(status)}`;

    try {
        const res = await fetch(url, {
            headers: { Accept: "application/json" },
        });

        if (res.status === 404) {
            return NextResponse.json({ claims: [] }, { status: 404 });
        }
        if (!res.ok) {
            console.error(`[Entity Claims API] Backend returned ${res.status} for entity ${entity_id}`);
            return NextResponse.json({ claims: [] }, { status: 502 });
        }

        const data = await res.json();
        return NextResponse.json(data);
    } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        console.error("[Entity Claims API] Fetch error:", msg);
        return NextResponse.json({ claims: [] }, { status: 500 });
    }
}
