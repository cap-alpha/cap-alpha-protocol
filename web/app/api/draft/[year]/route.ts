import { NextResponse } from "next/server";
import { BigQuery } from "@google-cloud/bigquery";

const bigquery = new BigQuery({
    projectId: process.env.GCP_PROJECT_ID || "cap-alpha-protocol",
    credentials:
        process.env.GCP_CLIENT_EMAIL && process.env.GCP_PRIVATE_KEY
            ? {
                  client_email: process.env.GCP_CLIENT_EMAIL,
                  private_key: process.env.GCP_PRIVATE_KEY.replace(/\\n/g, "\n"),
              }
            : undefined,
});

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
        const projectId = process.env.GCP_PROJECT_ID || "cap-alpha-protocol";

        const query = `
            SELECT
                l.prediction_hash,
                l.pundit_id,
                l.pundit_name,
                l.extracted_claim,
                l.target_player_name,
                l.target_team,
                l.source_url,
                COALESCE(r.resolution_status, 'PENDING') AS status,
                r.binary_correct,
                r.outcome_notes
            FROM \`${projectId}.gold_layer.prediction_ledger\` l
            LEFT JOIN \`${projectId}.gold_layer.prediction_resolutions\` r
                ON l.prediction_hash = r.prediction_hash
            WHERE l.claim_category = 'draft_pick'
              AND COALESCE(l.season_year, EXTRACT(YEAR FROM l.ingestion_timestamp)) = @year
            ORDER BY l.ingestion_timestamp DESC
            LIMIT 1000
        `;

        const [job] = await bigquery.createQueryJob({
            query,
            params: { year },
            jobTimeoutMs: 15000,
        });
        const [rows] = await job.getQueryResults({ timeoutMs: 15000 });

        const predictions = rows as Prediction[];

        const resolved = predictions.filter(
            (p) => p.status !== "PENDING"
        ).length;
        const pending = predictions.filter((p) => p.status === "PENDING").length;

        return NextResponse.json({
            draft_year: year,
            total_predictions: predictions.length,
            resolved,
            pending,
            predictions,
        });
    } catch (err) {
        console.error("[Draft API] BigQuery error:", err);
        return NextResponse.json(
            {
                draft_year: year,
                total_predictions: 0,
                resolved: 0,
                pending: 0,
                predictions: [],
            },
            { status: 500 }
        );
    }
}
