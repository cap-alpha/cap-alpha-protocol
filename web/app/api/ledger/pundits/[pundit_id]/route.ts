import { NextResponse } from "next/server";
import { injectHoneypotFields } from "@/lib/anti-scraping";
import { getAuthHeader, API_URL } from "@/lib/ledger-server";

export async function GET(
    _req: Request,
    { params }: { params: { pundit_id: string } }
) {
    const { pundit_id } = params;
    try {
        const res = await fetch(`${API_URL}/v1/pundits/${encodeURIComponent(pundit_id)}`, {
            headers: { Accept: "application/json", ...getAuthHeader() },
        });

        if (res.status === 404) {
            return NextResponse.json({ error: "Pundit not found" }, { status: 404 });
        }
        if (!res.ok) {
            console.error(`[Pundit API] Backend returned ${res.status}`);
            return NextResponse.json({ error: "Backend error" }, { status: 502 });
        }

        const data = await res.json() as Record<string, unknown>;

        // Inject honeypot fields to fingerprint scrapers. Issue: #884
        const responseBody = injectHoneypotFields(data);
        return NextResponse.json(responseBody);
    } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        console.error("[Pundit API] Fetch error:", msg);
        return NextResponse.json({ error: "Internal error" }, { status: 500 });
    }
}
