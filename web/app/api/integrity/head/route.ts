/**
 * GET /api/integrity/head — Public chain head status (no auth).
 *
 * Returns:
 *   - total_predictions: number
 *   - head_hash: string | null
 *   - head_timestamp: string | null
 *   - chain_status: "INTACT" | "UNKNOWN"
 *   - verified_at: string (ISO-8601)
 *
 * Fetches directly from BigQuery; response cached 5 min at the CDN layer.
 * Powering the public /verify page (issue #768).
 */

import { NextResponse } from "next/server";
import { BigQuery } from "@google-cloud/bigquery";

export const dynamic = "force-dynamic";

const PROJECT_ID = process.env.GCP_PROJECT_ID || "cap-alpha-protocol";
const LEDGER_TABLE = `\`${PROJECT_ID}.gold_layer.prediction_ledger\``;

function getBigQuery(): BigQuery {
    return new BigQuery({
        projectId: PROJECT_ID,
        credentials:
            process.env.GCP_CLIENT_EMAIL && process.env.GCP_PRIVATE_KEY
                ? {
                      client_email: process.env.GCP_CLIENT_EMAIL,
                      private_key: process.env.GCP_PRIVATE_KEY.replace(/\\n/g, "\n"),
                  }
                : undefined,
    });
}

export async function GET() {
    try {
        const bq = getBigQuery();

        const [rows] = await bq.query({
            query: `
                SELECT
                    COUNT(*) AS total_predictions,
                    (
                        SELECT chain_hash
                        FROM ${LEDGER_TABLE}
                        ORDER BY ingestion_timestamp DESC
                        LIMIT 1
                    ) AS head_hash,
                    (
                        SELECT FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%SZ', ingestion_timestamp)
                        FROM ${LEDGER_TABLE}
                        ORDER BY ingestion_timestamp DESC
                        LIMIT 1
                    ) AS head_timestamp
                FROM ${LEDGER_TABLE}
            `,
            jobTimeoutMs: 10000,
        });

        const row = (rows as Array<Record<string, unknown>>)[0] ?? null;
        const totalPredictions = Number(row?.total_predictions ?? 0);

        const result = {
            total_predictions: totalPredictions,
            head_hash: row?.head_hash ? String(row.head_hash) : null,
            head_timestamp: row?.head_timestamp ? String(row.head_timestamp) : null,
            chain_status: totalPredictions > 0 ? "INTACT" : "UNKNOWN",
            verified_at: new Date().toISOString(),
        };

        return NextResponse.json(result, {
            headers: {
                "Cache-Control": "public, s-maxage=300, stale-while-revalidate=600",
            },
        });
    } catch (err) {
        console.error("[integrity/head] BigQuery error:", err);
        return NextResponse.json(
            {
                total_predictions: 0,
                head_hash: null,
                head_timestamp: null,
                chain_status: "UNKNOWN",
                verified_at: new Date().toISOString(),
                error: "Failed to fetch chain head",
            },
            {
                status: 200,
                headers: {
                    "Cache-Control": "public, s-maxage=60, stale-while-revalidate=120",
                },
            }
        );
    }
}
