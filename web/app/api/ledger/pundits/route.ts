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

export async function GET(req: Request) {
    const { searchParams } = new URL(req.url);
    const sport = searchParams.get("sport");

    try {
        const projectId = process.env.GCP_PROJECT_ID || "cap-alpha-protocol";
        const sportFilter = sport
            ? `AND COALESCE(l.sport, 'NFL') = '${sport.replace(/'/g, "''")}'`
            : "";

        const query = `
            SELECT
                l.pundit_name,
                l.pundit_id,
                COALESCE(l.sport, 'NFL') AS sport,
                COUNT(DISTINCT l.prediction_hash) AS total_predictions,
                COUNT(DISTINCT r.prediction_hash) AS resolved_predictions,
                COUNTIF(r.resolution_status = 'CORRECT') AS correct_predictions,
                COUNTIF(r.resolution_status = 'INCORRECT') AS incorrect_predictions,
                ROUND(AVG(r.brier_score), 4) AS avg_brier_score,
                ROUND(AVG(r.weighted_score), 4) AS avg_weighted_score,
                ROUND(
                    SAFE_DIVIDE(
                        COUNTIF(r.resolution_status = 'CORRECT'),
                        NULLIF(COUNTIF(r.resolution_status IN ('CORRECT', 'INCORRECT')), 0)
                    ), 4
                ) AS accuracy_rate,
                COUNTIF(l.claim_category = 'game_outcome') AS game_outcome_count,
                COUNTIF(l.claim_category = 'player_performance') AS player_performance_count,
                COUNTIF(l.claim_category = 'trade') AS trade_count,
                COUNTIF(l.claim_category = 'injury') AS injury_count,
                COUNTIF(l.claim_category = 'contract') AS contract_count,
                COUNTIF(l.claim_category = 'draft_pick') AS draft_pick_count,
                FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%SZ', MIN(l.ingestion_timestamp)) AS first_seen,
                FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%SZ', MAX(l.ingestion_timestamp)) AS last_seen
            FROM \`${projectId}.gold_layer.prediction_ledger\` l
            LEFT JOIN \`${projectId}.gold_layer.prediction_resolutions\` r
                ON l.prediction_hash = r.prediction_hash
            WHERE 1=1 ${sportFilter}
            GROUP BY l.pundit_name, l.pundit_id, sport
            ORDER BY
                avg_weighted_score ASC NULLS LAST,
                accuracy_rate DESC NULLS LAST,
                total_predictions DESC
        `;

        const [job] = await bigquery.createQueryJob({ query, jobTimeoutMs: 15000 });
        const [rows] = await job.getQueryResults({ timeoutMs: 15000 });

        return NextResponse.json({ pundits: rows });
    } catch (err) {
        console.error("[Ledger API] BigQuery error:", err);
        return NextResponse.json({ pundits: [] });
    }
}
