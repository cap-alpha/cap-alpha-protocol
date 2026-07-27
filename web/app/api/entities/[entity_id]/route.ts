import { NextResponse } from "next/server";
import { API_URL } from "@/lib/ledger-server";


export async function GET(
    _req: Request,
    { params }: { params: { entity_id: string } }
) {
    const { entity_id } = params;
    try {
        const res = await fetch(
            `${API_URL}/v1/entities/${encodeURIComponent(entity_id)}`,
            { headers: { Accept: "application/json" } }
        );

        if (res.status === 404) {
            return NextResponse.json({ error: "Entity not found" }, { status: 404 });
        }
        if (!res.ok) {
            console.error(`[Entities API] Backend returned ${res.status} for entity ${entity_id}`);
            return NextResponse.json({ error: "Backend error" }, { status: 502 });
        }

        const data = await res.json();
        return NextResponse.json(data);
    } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        console.error("[Entities API] Fetch error:", msg);
        return NextResponse.json({ error: "Internal error" }, { status: 500 });
    }
}
