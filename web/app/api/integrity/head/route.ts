import { NextResponse } from "next/server";

const API_URL =
    process.env.API_URL ||
    process.env.NEXT_PUBLIC_API_URL ||
    "https://pundit-ledger-api-wvhvx2muna-uc.a.run.app";

export const revalidate = 60; // Next.js route cache — 60 seconds

export async function GET(): Promise<NextResponse> {
    try {
        const res = await fetch(`${API_URL}/v1/integrity/head`, {
            headers: { Accept: "application/json" },
        });

        if (!res.ok) {
            console.error(
                `[Integrity head] Backend returned ${res.status}`,
                await res.text()
            );
            return NextResponse.json(
                {
                    chain_head_hash: null,
                    total_predictions: 0,
                    last_added_at: null,
                    chain_status: "UNKNOWN",
                },
                { status: 502 }
            );
        }

        const data = await res.json();
        return NextResponse.json(data, {
            headers: {
                "Cache-Control": "public, s-maxage=60, stale-while-revalidate=30",
            },
        });
    } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        console.error("[Integrity head] fetch error:", msg);
        return NextResponse.json(
            {
                chain_head_hash: null,
                total_predictions: 0,
                last_added_at: null,
                chain_status: "UNKNOWN",
            },
            { status: 502 }
        );
    }
}
