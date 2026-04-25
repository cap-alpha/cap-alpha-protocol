import { NextResponse } from "next/server";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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

export async function GET(
    req: Request,
    { params }: { params: { year: string } }
): Promise<NextResponse<DraftData>> {
    const year = parseInt(params.year, 10);

    if (isNaN(year) || year < 1900 || year > 2100) {
        return NextResponse.json(
            {
                draft_year: year,
                total_predictions: 0,
                resolved: 0,
                pending: 0,
                predictions: [],
            },
            { status: 400 }
        );
    }

    try {
        const res = await fetch(`${API_URL}/v1/draft/${year}`, {
            headers: {
                "Accept": "application/json",
            },
        });

        if (!res.ok) {
            console.error(`[Draft API] Backend returned ${res.status}`, await res.text());
            return NextResponse.json({
                draft_year: year,
                total_predictions: 0,
                resolved: 0,
                pending: 0,
                predictions: [],
            });
        }

        const data = await res.json();
        return NextResponse.json({
            draft_year: year,
            total_predictions: data.total || 0,
            resolved: data.resolved || 0,
            pending: data.pending || 0,
            predictions: data.predictions || [],
        });
    } catch (err) {
        const errorMsg = err instanceof Error ? err.message : String(err);
        console.error("[Draft API] Backend fetch error:", {
            error: errorMsg,
            backendUrl: API_URL,
            year,
        });
        return NextResponse.json({
            draft_year: year,
            total_predictions: 0,
            resolved: 0,
            pending: 0,
            predictions: [],
        });
    }
}
