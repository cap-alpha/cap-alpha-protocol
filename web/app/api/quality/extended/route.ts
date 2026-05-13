/**
 * GET /api/quality/extended — Five new quality panels for the launch milestone.
 *
 * Panels:
 *   1. silverCoverage      — raw_utterance rows with a matching silver_v2_claims.claim
 *   2. provenanceComplete  — prediction_ledger rows with non-NULL llm_provider
 *   3. testabilityBuckets  — histogram of raw_utterance.testability_score in 0.2 buckets
 *   4. providerMix         — prediction_ledger rows grouped by llm_provider
 *   5. accuracyByCategory  — prediction_resolutions.binary_correct by ledger.claim_category
 *
 * All queries degrade gracefully to empty/zero when a table doesn't exist yet.
 * Cached 5 minutes via Cache-Control.
 *
 * Issue: launch milestone quality dashboard enrichment
 */

import { NextResponse } from "next/server";
import { BigQuery } from "@google-cloud/bigquery";

const PROJECT_ID = process.env.GCP_PROJECT_ID || "cap-alpha-protocol";

function getBigQuery(): BigQuery {
    return new BigQuery({
        projectId: PROJECT_ID,
        credentials:
            process.env.GCP_CLIENT_EMAIL && process.env.GCP_PRIVATE_KEY
                ? {
                      client_email: process.env.GCP_CLIENT_EMAIL,
                      private_key: process.env.GCP_PRIVATE_KEY.replace(
                          /\\n/g,
                          "\n"
                      ),
                  }
                : undefined,
    });
}

function t(table: string): string {
    return `\`${PROJECT_ID}.${table}\``;
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface SilverCoverage {
    total_utterances: number;
    promoted_utterances: number;
    coverage_pct: number;
}

export interface ProvenanceCompleteness {
    total_ledger: number;
    with_provider: number;
    completeness_pct: number;
}

export interface TestabilityBucket {
    bucket: string; // e.g. "0.0–0.2"
    count: number;
}

export interface ProviderMixItem {
    provider: string;
    count: number;
    pct: number;
}

export interface AccuracyByCategoryItem {
    category: string;
    total: number;
    correct: number;
    accuracy_pct: number | null;
}

export interface QualityExtendedResponse {
    silverCoverage: SilverCoverage;
    provenanceCompleteness: ProvenanceCompleteness;
    testabilityBuckets: TestabilityBucket[];
    providerMix: ProviderMixItem[];
    accuracyByCategory: AccuracyByCategoryItem[];
    generatedAt: string;
}

const EMPTY: QualityExtendedResponse = {
    silverCoverage: { total_utterances: 0, promoted_utterances: 0, coverage_pct: 0 },
    provenanceCompleteness: { total_ledger: 0, with_provider: 0, completeness_pct: 0 },
    testabilityBuckets: [],
    providerMix: [],
    accuracyByCategory: [],
    generatedAt: new Date().toISOString(),
};

// ---------------------------------------------------------------------------
// Individual query helpers — each returns a partial result or empty fallback
// ---------------------------------------------------------------------------

async function querySilverCoverage(bq: BigQuery): Promise<SilverCoverage> {
    try {
        const [rows] = await bq.query({
            query: `
                SELECT
                    COUNT(DISTINCT u.utterance_id) AS total_utterances,
                    COUNT(DISTINCT c.utterance_id) AS promoted_utterances
                FROM ${t("silver_v2_claims.raw_utterance")} u
                LEFT JOIN ${t("silver_v2_claims.claim")} c
                    ON c.utterance_id = u.utterance_id
            `,
            jobTimeoutMs: 20000,
        });
        const r = (rows as Array<Record<string, unknown>>)[0] ?? null;
        const total = Number(r?.total_utterances ?? 0);
        const promoted = Number(r?.promoted_utterances ?? 0);
        return {
            total_utterances: total,
            promoted_utterances: promoted,
            coverage_pct: total > 0 ? Math.round((promoted / total) * 1000) / 10 : 0,
        };
    } catch {
        return EMPTY.silverCoverage;
    }
}

async function queryProvenanceCompleteness(bq: BigQuery): Promise<ProvenanceCompleteness> {
    try {
        const [rows] = await bq.query({
            query: `
                SELECT
                    COUNT(*) AS total_ledger,
                    COUNTIF(llm_provider IS NOT NULL) AS with_provider
                FROM ${t("gold_layer.prediction_ledger")}
            `,
            jobTimeoutMs: 20000,
        });
        const r = (rows as Array<Record<string, unknown>>)[0] ?? null;
        const total = Number(r?.total_ledger ?? 0);
        const withProv = Number(r?.with_provider ?? 0);
        return {
            total_ledger: total,
            with_provider: withProv,
            completeness_pct: total > 0 ? Math.round((withProv / total) * 1000) / 10 : 0,
        };
    } catch {
        return EMPTY.provenanceCompleteness;
    }
}

async function queryTestabilityBuckets(bq: BigQuery): Promise<TestabilityBucket[]> {
    try {
        const [rows] = await bq.query({
            query: `
                SELECT
                    CASE
                        WHEN testability_score < 0.2  THEN '0.0\u20130.2'
                        WHEN testability_score < 0.4  THEN '0.2\u20130.4'
                        WHEN testability_score < 0.6  THEN '0.4\u20130.6'
                        WHEN testability_score < 0.8  THEN '0.6\u20130.8'
                        ELSE '0.8\u20131.0'
                    END AS bucket,
                    COUNT(*) AS count
                FROM ${t("silver_v2_claims.raw_utterance")}
                WHERE testability_score IS NOT NULL
                GROUP BY bucket
                ORDER BY bucket ASC
            `,
            jobTimeoutMs: 20000,
        });
        const BUCKET_ORDER = [
            "0.0\u20130.2",
            "0.2\u20130.4",
            "0.4\u20130.6",
            "0.6\u20130.8",
            "0.8\u20131.0",
        ];
        const resultMap = new Map<string, number>();
        for (const row of rows as Array<Record<string, unknown>>) {
            resultMap.set(String(row.bucket), Number(row.count ?? 0));
        }
        return BUCKET_ORDER.map((bucket) => ({
            bucket,
            count: resultMap.get(bucket) ?? 0,
        }));
    } catch {
        return [];
    }
}

async function queryProviderMix(bq: BigQuery): Promise<ProviderMixItem[]> {
    try {
        const [rows] = await bq.query({
            query: `
                SELECT
                    COALESCE(llm_provider, 'unset') AS provider,
                    COUNT(*) AS count
                FROM ${t("gold_layer.prediction_ledger")}
                GROUP BY provider
                ORDER BY count DESC
            `,
            jobTimeoutMs: 20000,
        });
        const typed = rows as Array<Record<string, unknown>>;
        const total = typed.reduce((s, r) => s + Number(r.count ?? 0), 0);
        return typed.map((r) => {
            const count = Number(r.count ?? 0);
            return {
                provider: String(r.provider ?? "unknown"),
                count,
                pct: total > 0 ? Math.round((count / total) * 1000) / 10 : 0,
            };
        });
    } catch {
        return [];
    }
}

async function queryAccuracyByCategory(bq: BigQuery): Promise<AccuracyByCategoryItem[]> {
    try {
        const [rows] = await bq.query({
            query: `
                SELECT
                    l.claim_category AS category,
                    COUNT(r.prediction_hash) AS total,
                    COUNTIF(r.binary_correct = TRUE) AS correct
                FROM ${t("gold_layer.prediction_ledger")} l
                JOIN ${t("gold_layer.prediction_resolutions")} r
                    ON r.prediction_hash = l.prediction_hash
                WHERE l.claim_category IS NOT NULL
                  AND r.binary_correct IS NOT NULL
                GROUP BY category
                ORDER BY total DESC
            `,
            jobTimeoutMs: 20000,
        });
        return (rows as Array<Record<string, unknown>>).map((r) => {
            const total = Number(r.total ?? 0);
            const correct = Number(r.correct ?? 0);
            return {
                category: String(r.category ?? "unknown"),
                total,
                correct,
                accuracy_pct: total > 0 ? Math.round((correct / total) * 1000) / 10 : null,
            };
        });
    } catch {
        return [];
    }
}

// ---------------------------------------------------------------------------
// Route handler
// ---------------------------------------------------------------------------

export async function GET() {
    const bq = getBigQuery();

    try {
        const [
            silverCoverage,
            provenanceCompleteness,
            testabilityBuckets,
            providerMix,
            accuracyByCategory,
        ] = await Promise.all([
            querySilverCoverage(bq),
            queryProvenanceCompleteness(bq),
            queryTestabilityBuckets(bq),
            queryProviderMix(bq),
            queryAccuracyByCategory(bq),
        ]);

        const response: QualityExtendedResponse = {
            silverCoverage,
            provenanceCompleteness,
            testabilityBuckets,
            providerMix,
            accuracyByCategory,
            generatedAt: new Date().toISOString(),
        };

        return NextResponse.json(response, {
            headers: {
                "Cache-Control": "public, s-maxage=300, stale-while-revalidate=600",
            },
        });
    } catch (err) {
        console.error("[Quality Extended API] error:", err);
        return NextResponse.json(
            { ...EMPTY, generatedAt: new Date().toISOString() },
            {
                status: 200,
                headers: {
                    "Cache-Control": "public, s-maxage=60, stale-while-revalidate=120",
                },
            }
        );
    }
}
