import { NextResponse } from "next/server";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "https://pundit-api-139200534279.us-central1.run.app";

export async function GET(req: Request) {
    try {
        const res = await fetch(`${API_URL}/v1/pundits/`, {
            headers: {
                "Accept": "application/json",
            },
        });

        if (!res.ok) {
            console.error(`[Ledger API] Backend returned ${res.status}`, await res.text());
            return NextResponse.json({ pundits: [] });
        }

        const data = await res.json();
        return NextResponse.json({ pundits: data.pundits || [] });
    } catch (err) {
        const errorMsg = err instanceof Error ? err.message : String(err);
        console.error("[Ledger API] Backend fetch error:", {
            error: errorMsg,
            backendUrl: API_URL,
        });
        return NextResponse.json({ pundits: [] });
    }
}
