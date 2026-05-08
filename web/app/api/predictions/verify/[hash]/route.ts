import { NextResponse } from "next/server";

const API_URL =
    process.env.API_URL ||
    process.env.NEXT_PUBLIC_API_URL ||
    "https://pundit-ledger-api-wvhvx2muna-uc.a.run.app";

export async function GET(
    _req: Request,
    { params }: { params: { hash: string } }
): Promise<NextResponse> {
    const { hash } = params;

    if (!hash || hash.length < 8) {
        return NextResponse.json(
            { found: false, error: "Hash too short" },
            { status: 400 }
        );
    }

    try {
        const res = await fetch(
            `${API_URL}/v1/predictions/${encodeURIComponent(hash)}/verify`,
            { headers: { Accept: "application/json" } }
        );

        if (!res.ok) {
            console.error(
                `[Predict verify] Backend returned ${res.status}`,
                await res.text()
            );
            return NextResponse.json({ found: false }, { status: 502 });
        }

        const data = await res.json();
        return NextResponse.json(data);
    } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        console.error("[Predict verify] fetch error:", msg);
        return NextResponse.json({ found: false }, { status: 502 });
    }
}
