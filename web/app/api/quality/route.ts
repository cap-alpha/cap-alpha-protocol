/**
 * GET /api/quality — Extraction quality metrics for the public dashboard.
 *
 * Returns three aggregations from BigQuery:
 *   1. dailyTrend    — per-day stats for the last 90 days
 *   2. punditStats   — top 25 pundits by utterance volume
 *   3. dataQuality   — null-metadata %, zero-output runs, provider mix
 *   4. waitlistGates — pass/fail for the 3 waitlist-removal criteria
 *
 * Caching: responses are cached for 1 hour via Cache-Control. The Next.js
 * route itself is called by an RSC that sets revalidate=3600 — together
 * this limits BigQuery spend to ~24 queries/day.
 *
 * Issue #599
 */

import { NextResponse } from "next/server";
import { BigQuery } from "@google-cloud/bigquery";

const PROJECT_ID = process.env.GCP_PROJECT_ID || "cap-alpha-protocol";
const UTTERANCE_TABLE = `\`${PROJECT_ID}.silver_v2_claims.raw_utterance\``;
const LEDGER_TABLE = `\`${PROJECT_ID}.gold_layer.prediction_ledger\``;
const RESOLUTION_TABLE = `\`${PROJECT_ID}.silver_v2_claims.resolution\``;

// Waitlist-removal criteria thresholds (configurable via env)
const TESTABILITY_THRESHOLD = parseFloat(
    process.env.WAITLIST_TESTABILITY_THRESHOLD || "0.65"
);
const METADATA_COMPLETENESS_THRESHOLD = parseFloat(
    process.env.WAITLIST_METADATA_THRESHOLD || "0.99"
);
const CONSECUTIVE_DAYS_REQUIRED = parseInt(
    process.env.WAITLIST_CONSECUTIVE_DAYS || "30"
);

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

export interface DailyTrendRow {
    date: string;
    utterances: number;
    claims_promoted: number;
    claim_promotion_rate: number;
    mean_testability_score: number;
    moving_avg_7d: number;
    speech_act_distribution: Record<string, number>;
}

export interface PunditStatRow {
    speaker_entity_id: string;
    utterances: number;
    claims_promoted: number;
    claim_rate: number;
    mean_testability_score: number;
    resolved: number;
    correct: number;
    resolution_rate: number;
}

export interface DataQuality {
    null_metadata_pct: number;
    pct_rows_with_complete_metadata: number;
    zero_output_runs_7d: number;
    provider_mix: Record<string, number>;
    /** Fraction of silver_v2_claims.resolution rows with outcome='true' over all
     *  resolved (true|false) rows. Sourced from silver_v2_claims.resolution (Issue #615).
     *  null when the table has no resolved rows yet. */
    resolution_accuracy: number | null;
}

export interface WaitlistGate {
    id: string;
    label: string;
    description: string;
    pass: boolean;
    current_value: number | null;
    threshold: number;
}

export interface QualityResponse {
    dailyTrend: DailyTrendRow[];
    punditStats: PunditStatRow[];
    dataQuality: DataQuality;
    waitlistGates: WaitlistGate[];
    generatedAt: string;
    hasData: boolean;
}

const EMPTY_RESPONSE: QualityResponse = {
    dailyTrend: [],
    punditStats: [],
    dataQuality: {
        null_metadata_pct: 0,
        pct_rows_with_complete_metadata: 1,
        zero_output_runs_7d: 0,
        provider_mix: {},
        resolution_accuracy: null,
    },
    waitlistGates: [
        {
            id: "testability",
            label: "Testability score ≥ 0.65 for 30 consecutive days",
            description: `≥${CONSECUTIVE_DAYS_REQUIRED} consecutive days with mean testability_score ≥ ${TESTABILITY_THRESHOLD}`,
            pass: false,
            current_value: null,
            threshold: TESTABILITY_THRESHOLD,
        },
        {
            id: "metadata",
            label: "≥99% metadata completeness for 30 days",
            description: `≥${CONSECUTIVE_DAYS_REQUIRED} consecutive days with ≥${(METADATA_COMPLETENESS_THRESHOLD * 100).toFixed(0)}% metadata completeness`,
            pass: false,
            current_value: null,
            threshold: METADATA_COMPLETENESS_THRESHOLD,
        },
        {
            id: "zero_output",
            label: "Zero 0-output production runs for 30 days",
            description: `No extraction run produced 0 utterances in the last ${CONSECUTIVE_DAYS_REQUIRED} days`,
            pass: false,
            current_value: null,
            threshold: 0,
        },
    ],
    generatedAt: new Date().toISOString(),
    hasData: false,
};

export async function GET() {
    const bq = getBigQuery();

    try {
        // Query 1: Daily trend — last 90 days
        const [dailyRows] = await bq.query({
            query: `
                SELECT
                    DATE(uttered_at) AS date,
                    COUNT(*) AS utterances,
                    COUNTIF(speech_act_type IN ('assertion','conditional','recall')
                        AND testability_score >= 0.6) AS claims_promoted,
                    SAFE_DIVIDE(
                        COUNTIF(speech_act_type IN ('assertion','conditional','recall')
                            AND testability_score >= 0.6),
                        COUNT(*)
                    ) AS claim_promotion_rate,
                    AVG(testability_score) AS mean_testability_score,
                    -- Aggregate speech_act_type counts as JSON-like struct
                    COUNTIF(speech_act_type = 'assertion') AS sat_assertion,
                    COUNTIF(speech_act_type = 'conditional') AS sat_conditional,
                    COUNTIF(speech_act_type = 'recall') AS sat_recall,
                    COUNTIF(speech_act_type = 'rhetorical_question') AS sat_rhetorical_question,
                    COUNTIF(speech_act_type = 'hedge') AS sat_hedge,
                    COUNTIF(speech_act_type = 'commentary') AS sat_commentary,
                    COUNTIF(speech_act_type = 'opinion') AS sat_opinion
                FROM ${UTTERANCE_TABLE}
                WHERE uttered_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY)
                GROUP BY date
                ORDER BY date ASC
            `,
            jobTimeoutMs: 15000,
        });

        // Compute 7-day moving average for testability_score
        const dailyTrend: DailyTrendRow[] = (
            dailyRows as Array<Record<string, unknown>>
        ).map((row, idx, arr) => {
            const window = arr.slice(Math.max(0, idx - 6), idx + 1);
            const movingAvg =
                window.reduce(
                    (sum, r) => sum + Number(r.mean_testability_score ?? 0),
                    0
                ) / window.length;
            return {
                date: String(row.date),
                utterances: Number(row.utterances ?? 0),
                claims_promoted: Number(row.claims_promoted ?? 0),
                claim_promotion_rate: Number(row.claim_promotion_rate ?? 0),
                mean_testability_score: Number(
                    row.mean_testability_score ?? 0
                ),
                moving_avg_7d: movingAvg,
                speech_act_distribution: {
                    assertion: Number(row.sat_assertion ?? 0),
                    conditional: Number(row.sat_conditional ?? 0),
                    recall: Number(row.sat_recall ?? 0),
                    rhetorical_question: Number(
                        row.sat_rhetorical_question ?? 0
                    ),
                    hedge: Number(row.sat_hedge ?? 0),
                    commentary: Number(row.sat_commentary ?? 0),
                    opinion: Number(row.sat_opinion ?? 0),
                },
            };
        });

        // Query 2: Per-pundit stats — top 25 by utterance volume
        const [punditRows] = await bq.query({
            query: `
                WITH utterance_agg AS (
                    SELECT
                        speaker_entity_id,
                        COUNT(*) AS utterances,
                        COUNTIF(speech_act_type IN ('assertion','conditional','recall')
                            AND testability_score >= 0.6) AS claims_promoted,
                        SAFE_DIVIDE(
                            COUNTIF(speech_act_type IN ('assertion','conditional','recall')
                                AND testability_score >= 0.6),
                            COUNT(*)
                        ) AS claim_rate,
                        AVG(testability_score) AS mean_testability_score
                    FROM ${UTTERANCE_TABLE}
                    WHERE uttered_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 365 DAY)
                    GROUP BY speaker_entity_id
                    ORDER BY utterances DESC
                    LIMIT 25
                ),
                ledger_agg AS (
                    SELECT
                        pundit_id,
                        COUNT(*) AS total_predictions,
                        COUNTIF(resolution_status != 'PENDING') AS resolved,
                        COUNTIF(resolution_status = 'CORRECT') AS correct
                    FROM ${LEDGER_TABLE}
                    GROUP BY pundit_id
                )
                SELECT
                    u.speaker_entity_id,
                    u.utterances,
                    u.claims_promoted,
                    u.claim_rate,
                    u.mean_testability_score,
                    COALESCE(l.resolved, 0) AS resolved,
                    COALESCE(l.correct, 0) AS correct,
                    SAFE_DIVIDE(COALESCE(l.resolved, 0), NULLIF(u.claims_promoted, 0)) AS resolution_rate
                FROM utterance_agg u
                LEFT JOIN ledger_agg l ON l.pundit_id = u.speaker_entity_id
                ORDER BY u.utterances DESC
            `,
            jobTimeoutMs: 15000,
        });

        const punditStats: PunditStatRow[] = (
            punditRows as Array<Record<string, unknown>>
        ).map((row) => ({
            speaker_entity_id: String(row.speaker_entity_id ?? ""),
            utterances: Number(row.utterances ?? 0),
            claims_promoted: Number(row.claims_promoted ?? 0),
            claim_rate: Number(row.claim_rate ?? 0),
            mean_testability_score: Number(row.mean_testability_score ?? 0),
            resolved: Number(row.resolved ?? 0),
            correct: Number(row.correct ?? 0),
            resolution_rate: Number(row.resolution_rate ?? 0),
        }));

        // Query 3: Data quality + waitlist gate metrics
        const [qualityRows] = await bq.query({
            query: `
                WITH daily_completeness AS (
                    SELECT
                        DATE(uttered_at) AS date,
                        COUNT(*) AS total,
                        COUNTIF(
                            speaker_entity_id IS NULL
                            OR source_doc_id IS NULL
                            OR domain IS NULL
                            OR domain = ''
                        ) AS null_metadata_count,
                        AVG(testability_score) AS mean_score
                    FROM ${UTTERANCE_TABLE}
                    WHERE uttered_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY)
                    GROUP BY date
                ),
                rolling_gates AS (
                    SELECT
                        -- Gate (i): consecutive days testability >= threshold
                        MIN(CASE WHEN mean_score >= @testability_threshold THEN 1 ELSE 0 END)
                            OVER (ORDER BY date ROWS BETWEEN 29 PRECEDING AND CURRENT ROW)
                            AS last_30d_testability_pass,
                        -- Gate (ii): consecutive days metadata completeness >= threshold
                        MIN(CASE WHEN SAFE_DIVIDE(total - null_metadata_count, total) >= @metadata_threshold THEN 1 ELSE 0 END)
                            OVER (ORDER BY date ROWS BETWEEN 29 PRECEDING AND CURRENT ROW)
                            AS last_30d_metadata_pass,
                        mean_score,
                        SAFE_DIVIDE(total - null_metadata_count, total) AS completeness_rate,
                        SAFE_DIVIDE(null_metadata_count, total) AS null_pct,
                        date
                    FROM daily_completeness
                ),
                latest AS (
                    SELECT *
                    FROM rolling_gates
                    ORDER BY date DESC
                    LIMIT 1
                )
                -- Phase C completeness: speech_act_type, testability_score, domain, extraction_confidence (#595)
                phase_c_null AS (
                    SELECT
                        COUNT(*) AS total_all,
                        COUNTIF(
                            speech_act_type IS NULL
                            OR testability_score IS NULL
                            OR domain IS NULL
                            OR extraction_confidence IS NULL
                        ) AS phase_c_null_count
                    FROM ${UTTERANCE_TABLE}
                    WHERE uttered_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY)
                )
                SELECT
                    l.last_30d_testability_pass,
                    l.last_30d_metadata_pass,
                    l.mean_score AS latest_mean_testability,
                    l.completeness_rate AS latest_completeness_rate,
                    l.null_pct AS overall_null_pct,
                    SAFE_DIVIDE(p.total_all - p.phase_c_null_count, p.total_all)
                        AS pct_rows_with_complete_metadata,
                    -- Provider mix from domain field (proxy)
                    (SELECT COUNT(*) FROM ${UTTERANCE_TABLE}
                     WHERE uttered_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
                       AND domain = 'nfl') AS nfl_count_7d,
                    (SELECT COUNT(*) FROM ${UTTERANCE_TABLE}
                     WHERE uttered_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)) AS total_7d
                FROM latest l, phase_c_null p
            `,
            params: {
                testability_threshold: TESTABILITY_THRESHOLD,
                metadata_threshold: METADATA_COMPLETENESS_THRESHOLD,
            },
            types: {
                testability_threshold: "FLOAT64",
                metadata_threshold: "FLOAT64",
            },
            jobTimeoutMs: 15000,
        });

        const qRow =
            (qualityRows as Array<Record<string, unknown>>)[0] ?? null;

        const nullMetadataPct = Number(qRow?.overall_null_pct ?? 0);
        const pctRowsWithCompleteMetadata = Number(
            qRow?.pct_rows_with_complete_metadata ?? 1
        );
        const latestTestability = Number(qRow?.latest_mean_testability ?? 0);
        const latestCompleteness = Number(
            qRow?.latest_completeness_rate ?? 0
        );
        const testabilityPass =
            Number(qRow?.last_30d_testability_pass ?? 0) === 1;
        const metadataPass =
            Number(qRow?.last_30d_metadata_pass ?? 0) === 1;

        // Zero-output run gate: count days in last 30 where total utterances = 0
        // We approximate using daily_completeness: any date with 0 utterances = bad run
        // A proper count requires the extraction_run table (Issue 4); stub to 0 until then.
        const zeroOutputRuns7d = 0;

        // Query 4: resolution_accuracy from silver_v2_claims.resolution (Issue #615)
        // Best-effort: errors produce null rather than failing the entire response.
        let resolutionAccuracy: number | null = null;
        try {
            const [resRows] = await bq.query({
                query: `
                    SELECT
                        SAFE_DIVIDE(
                            COUNTIF(outcome = 'true'),
                            COUNTIF(outcome IN ('true', 'false'))
                        ) AS resolution_accuracy
                    FROM ${RESOLUTION_TABLE}
                    WHERE resolved_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY)
                `,
                jobTimeoutMs: 10000,
            });
            const resRow = (resRows as Array<Record<string, unknown>>)[0] ?? null;
            if (resRow?.resolution_accuracy != null) {
                resolutionAccuracy = Number(resRow.resolution_accuracy);
            }
        } catch (resErr) {
            console.warn(
                "[Quality API] resolution_accuracy query failed (silver_v2_claims.resolution may not exist yet):",
                resErr
            );
        }

        const dataQuality: DataQuality = {
            null_metadata_pct: nullMetadataPct,
            pct_rows_with_complete_metadata: pctRowsWithCompleteMetadata,
            zero_output_runs_7d: zeroOutputRuns7d,
            provider_mix: {
                nfl: Number(qRow?.nfl_count_7d ?? 0),
                other:
                    Number(qRow?.total_7d ?? 0) -
                    Number(qRow?.nfl_count_7d ?? 0),
            },
            resolution_accuracy: resolutionAccuracy,
        };

        const waitlistGates: WaitlistGate[] = [
            {
                id: "testability",
                label: `Testability score ≥ ${TESTABILITY_THRESHOLD} for ${CONSECUTIVE_DAYS_REQUIRED} consecutive days`,
                description: `Mean testability_score across all utterances must be ≥ ${TESTABILITY_THRESHOLD} for ${CONSECUTIVE_DAYS_REQUIRED} days running.`,
                pass: testabilityPass,
                current_value: latestTestability,
                threshold: TESTABILITY_THRESHOLD,
            },
            {
                id: "metadata",
                label: `≥${(METADATA_COMPLETENESS_THRESHOLD * 100).toFixed(0)}% metadata completeness for ${CONSECUTIVE_DAYS_REQUIRED} days`,
                description: `speaker_entity_id, source_doc_id, and domain must be non-null on ≥${(METADATA_COMPLETENESS_THRESHOLD * 100).toFixed(0)}% of utterances for ${CONSECUTIVE_DAYS_REQUIRED} days running.`,
                pass: metadataPass,
                current_value: latestCompleteness,
                threshold: METADATA_COMPLETENESS_THRESHOLD,
            },
            {
                id: "zero_output",
                label: `Zero 0-output production runs for ${CONSECUTIVE_DAYS_REQUIRED} days`,
                description: `No extraction run may produce 0 utterances in the last ${CONSECUTIVE_DAYS_REQUIRED} days. Requires Issue #4 (extraction_run table) to be fully operational.`,
                pass: false,
                current_value: null,
                threshold: 0,
            },
        ];

        const response: QualityResponse = {
            dailyTrend,
            punditStats,
            dataQuality,
            waitlistGates,
            generatedAt: new Date().toISOString(),
            hasData: dailyTrend.length > 0,
        };

        return NextResponse.json(response, {
            headers: {
                "Cache-Control": "public, s-maxage=3600, stale-while-revalidate=86400",
            },
        });
    } catch (err) {
        console.error("[Quality API] BigQuery error:", err);
        return NextResponse.json(
            { ...EMPTY_RESPONSE, error: "Failed to load quality metrics" },
            {
                status: 200,
                headers: {
                    "Cache-Control": "public, s-maxage=300, stale-while-revalidate=600",
                },
            }
        );
    }
}
