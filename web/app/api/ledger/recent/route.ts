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
    const punditId = searchParams.get("pundit_id");
    const sport = searchParams.get("sport");
    const limit = Math.min(parseInt(searchParams.get("limit") || "20"), 50);

    try {
        const projectId = process.env.GCP_PROJECT_ID || "cap-alpha-protocol";
        const conditions: string[] = [];
        if (punditId) conditions.push(`l.pundit_id = '${punditId.replace(/'/g, "''")}'`);
        if (sport) conditions.push(`COALESCE(l.sport, 'NFL') = '${sport.replace(/'/g, "''")}'`);
        const whereClause = conditions.length > 0 ? `WHERE ${conditions.join(" AND ")}` : "";

        const query = `
            SELECT
                l.pundit_name,
                l.pundit_id,
                l.extracted_claim,
                l.claim_category,
                l.season_year,
                l.target_player_id,
                l.target_team,
                COALESCE(l.sport, 'NFL') AS sport,
                SUBSTR(l.prediction_hash, 1, 12) AS prediction_hash_short,
                FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%SZ', l.ingestion_timestamp) AS ingestion_timestamp,
                r.resolution_status,
                ROUND(r.brier_score, 4) AS brier_score,
                ROUND(r.weighted_score, 4) AS weighted_score
            FROM \`${projectId}.gold_layer.prediction_ledger\` l
            LEFT JOIN \`${projectId}.gold_layer.prediction_resolutions\` r
                ON l.prediction_hash = r.prediction_hash
            ${whereClause}
            ORDER BY l.ingestion_timestamp DESC
            LIMIT ${limit}
        `;

        const [job] = await bigquery.createQueryJob({ query, jobTimeoutMs: 15000 });
        const [rows] = await job.getQueryResults({ timeoutMs: 15000 });

        return NextResponse.json({ predictions: rows });
    } catch (err) {
        console.error("[Ledger Recent API] BigQuery error:", err);
        return NextResponse.json({ predictions: [] });
    }
}
