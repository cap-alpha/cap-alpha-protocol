/**
 * GET /api/integrity/lookup?hash=<prediction_hash>
 *
 * Public endpoint — no auth required.  The SHA-256 hash is not guessable;
 * it functions as a bearer token for the specific prediction.
 *
 * Returns:
 *   - found: boolean
 *   - prediction_hash: string
 *   - chain_position: number | null
 *   - chain_hash: string | null
 *   - ingestion_timestamp: string | null
 *   - pundit_name: string | null
 *   - extracted_claim: string | null
 *   - claim_category: string | null
 *   - season_year: number | null
 *   - source_url: string | null
 *
 * Issue #768.
 */

import { NextRequest, NextResponse } from "next/server";
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

const HEX_RE = /^[0-9a-fA-F]{1,128}$/;

export async function GET(req: NextRequest) {
    const hash = req.nextUrl.searchParams.get("hash") ?? "";
    const sanitized = hash.trim();

    if (!sanitized || !HEX_RE.test(sanitized)) {
        return NextResponse.json(
            { error: "Invalid or missing hash parameter" },
            { status: 422 }
        );
    }

    try {
        const bq = getBigQuery();

        // QUALIFY filters within the window function result; available in BQ.
        const [rows] = await bq.query({
            query: `
                SELECT
                    prediction_hash,
                    chain_hash,
                    FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%SZ', ingestion_timestamp) AS ingestion_timestamp,
                    pundit_name,
                    extracted_claim,
                    claim_category,
                    season_year,
                    source_url,
                    ROW_NUMBER() OVER (ORDER BY ingestion_timestamp ASC) AS chain_position
                FROM ${LEDGER_TABLE}
                QUALIFY prediction_hash = @prediction_hash
            `,
            params: { prediction_hash: sanitized },
            types: { prediction_hash: "STRING" },
            jobTimeoutMs: 10000,
        });

        const typedRows = rows as Array<Record<string, unknown>>;

        if (!typedRows.length) {
            return NextResponse.json({ found: false, prediction_hash: sanitized });
        }

        const row = typedRows[0];
        return NextResponse.json(
            {
                found: true,
                prediction_hash: sanitized,
                chain_position: row.chain_position != null ? Number(row.chain_position) : null,
                chain_hash: row.chain_hash ? String(row.chain_hash) : null,
                ingestion_timestamp: row.ingestion_timestamp ? String(row.ingestion_timestamp) : null,
                pundit_name: row.pundit_name ? String(row.pundit_name) : null,
                extracted_claim: row.extracted_claim ? String(row.extracted_claim) : null,
                claim_category: row.claim_category ? String(row.claim_category) : null,
                season_year: row.season_year != null ? Number(row.season_year) : null,
                source_url: row.source_url ? String(row.source_url) : null,
            },
            {
                headers: {
                    // Cache hit for a specific hash for 5 min; hash is immutable once written.
                    "Cache-Control": "public, s-maxage=300, stale-while-revalidate=3600",
                },
            }
        );
    } catch (err) {
        console.error("[integrity/lookup] BigQuery error:", err);
        return NextResponse.json(
            { error: "Failed to look up prediction" },
            { status: 500 }
        );
    }
}
