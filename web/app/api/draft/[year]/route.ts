import { NextResponse } from "next/server";

// Server-only env var — fail fast if unset so production issues are not
// masked as empty-200 responses.
const API_URL = process.env.INTERNAL_API_URL;

interface Prediction {
    prediction_hash: string;
    pundit_id: string;
    pundit_name: string;
    extracted_claim: string;
    target_player_name: string | null;
    target_team: string | null;
    source_url: string | null;
    status: string;
    binary_correct: boolean | null;
    outcome_notes: string | null;
}

interface DraftData {
    draft_year: number;
    total_predictions: number;
    resolved: number;
    pending: number;
    predictions: Prediction[];
}

const emptyDraft = (year: number, status = 200): NextResponse<DraftData> =>
    NextResponse.json(
        { draft_year: year, total_predictions: 0, resolved: 0, pending: 0, predictions: [] },
        { status }
    );

export async function GET(
    req: Request,
    { params }: { params: { year: string } }
): Promise<NextResponse<DraftData>> {
    const parsed = parseInt(params.year, 10);
    const year = Number.isFinite(parsed) ? parsed : NaN;

    if (isNaN(year) || year < 1900 || year > 2100) {
        return emptyDraft(year, 400);
    }

    if (!API_URL) {
        console.error("[Draft API] INTERNAL_API_URL is not set");
        return NextResponse.json(
            { error: "API URL not configured" } as unknown as DraftData,
            { status: 500 }
        );
    }

    try {
        const res = await fetch(`${API_URL}/v1/draft/${year}`, {
            headers: {
                Accept: "application/json",
            },
        });

        if (!res.ok) {
            console.error(
                `[Draft API] Backend returned ${res.status}`,
                await res.text()
            );
            return NextResponse.json(
                {
                    draft_year: year,
                    total_predictions: 0,
                    resolved: 0,
                    pending: 0,
                    predictions: [],
                },
                { status: 502 }
            );
        }

        const data = await res.json();
        // Backend may return resolution_status; normalise to status for UI
        const predictions: Prediction[] = (data.predictions || []).map(
            (p: Record<string, unknown>) => ({
                ...p,
                status:
                    (p.status as string) ??
                    (p.resolution_status as string) ??
                    "PENDING",
            })
        );
        return NextResponse.json({
            draft_year: year,
            total_predictions: data.total ?? data.total_predictions ?? 0,
            resolved: data.resolved ?? 0,
            pending: data.pending ?? 0,
            predictions,
        });
    } catch (err) {
        const errorMsg = err instanceof Error ? err.message : String(err);
        console.error("[Draft API] Backend fetch error:", {
            error: errorMsg,
            backendUrl: API_URL,
            year,
        });
        return NextResponse.json(
            {
                draft_year: year,
                total_predictions: 0,
                resolved: 0,
                pending: 0,
                predictions: [],
            },
            { status: 502 }
        );
    }
}
