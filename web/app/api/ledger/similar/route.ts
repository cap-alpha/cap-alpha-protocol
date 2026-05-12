import { NextResponse } from "next/server";
import {
    injectHoneypotFields,
    enforcePaginationLimit,
    logBlockedRequest,
    LEDGER_MAX_LIMIT,
} from "@/lib/anti-scraping";

const API_URL =
    process.env.API_URL ||
    process.env.NEXT_PUBLIC_API_URL ||
    "https://pundit-ledger-api-wvhvx2muna-uc.a.run.app";

export async function GET(req: Request) {
    const { searchParams } = new URL(req.url);

    const utteranceId = searchParams.get("utterance_id");
    if (!utteranceId) {
        return NextResponse.json({ similar: [] }, { status: 400 });
    }

    // Enforce pagination limit: reject requests asking for more than LEDGER_MAX_LIMIT rows.
    // Issue: #884
    const limitCheck = enforcePaginationLimit(
        searchParams.get("limit"),
        /* defaultLimit */ 10
    );
    if (!limitCheck.valid) {
        const ip =
            req.headers.get("x-real-ip") ??
            req.headers.get("x-forwarded-for")?.split(",")[0].trim() ??
            "unknown";
        logBlockedRequest({
            timestamp: new Date().toISOString(),
            ip,
            user_agent: req.headers.get("user-agent") ?? "",
            endpoint: "/api/ledger/similar",
            block_reason: "limit_exceeded",
        });
        return NextResponse.json(
            {
                error: limitCheck.error,
                max_limit: LEDGER_MAX_LIMIT,
            },
            { status: 400 }
        );
    }

    const backendUrl = new URL(`${API_URL}/v1/predictions/similar`);
    backendUrl.searchParams.set("utterance_id", utteranceId);
    backendUrl.searchParams.set("limit", String(limitCheck.limit));

    try {
        const res = await fetch(backendUrl.toString(), {
            headers: {
                Accept: "application/json",
            },
        });

        if (!res.ok) {
            console.error(
                `[Ledger Similar API] Backend returned ${res.status}`,
                await res.text()
            );
            return NextResponse.json({ similar: [] }, { status: 502 });
        }

        const data = await res.json() as { similar?: unknown[] };

        // Inject honeypot fields at the top level to fingerprint scrapers.
        // Issue: #884
        const responseBody = injectHoneypotFields({
            similar: data.similar ?? [],
        });
        return NextResponse.json(responseBody);
    } catch (err) {
        const errorMsg = err instanceof Error ? err.message : String(err);
        console.error("[Ledger Similar API] Backend fetch error:", {
            error: errorMsg,
            backendUrl: API_URL,
        });
        return NextResponse.json({ similar: [] }, { status: 502 });
    }
}
