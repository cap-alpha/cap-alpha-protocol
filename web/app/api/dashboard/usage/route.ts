/**
 * GET /api/dashboard/usage — Fetch user's API usage metrics
 *
 * Returns:
 * - currentTier: user's subscription tier
 * - tierName: human-readable tier name
 * - monthlyQuota: request limit for the month
 * - renewalDate: when the quota resets
 * - dailyRequests: 30-day breakdown [{ date, count_2xx, count_4xx, count_5xx }]
 * - topEndpoints: most-called endpoints [{ endpoint_path, count, pct }]
 * - rateLimitStatus: current minute/day usage
 *
 * All data is queried from monetization.api_requests (30-day TTL).
 */

import { auth } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";
import { BigQuery } from "@google-cloud/bigquery";
import { getUserTier, type Tier } from "@/lib/api-keys/tiers";

const PROJECT_ID = process.env.GCP_PROJECT_ID || "cap-alpha-protocol";
const DATASET = "monetization";

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

interface DailyRequest {
    date: string;
    count_2xx: number;
    count_4xx: number;
    count_5xx: number;
}

interface TopEndpoint {
    endpoint_path: string;
    count: number;
    pct: number;
}

interface RateLimitStatus {
    minute_current: number;
    minute_limit: number;
    day_current: number;
    day_limit: number;
}

interface UsageResponse {
    currentTier: string;
    tierName: string;
    monthlyQuota: number;
    renewalDate: string | null;
    dailyRequests: DailyRequest[];
    topEndpoints: TopEndpoint[];
    rateLimitStatus: RateLimitStatus;
    emptyState: boolean;
}

// Keyed by canonical Tier type from tiers.ts — keeps them in sync.
const TIER_CONFIG: Record<Tier, { name: string; monthlyQuota: number | null }> =
    {
        free: { name: "Free", monthlyQuota: 10000 },
        pro: { name: "Pro", monthlyQuota: 100000 },
        agent: { name: "Agent", monthlyQuota: 1000000 },
        api_starter: { name: "API Starter", monthlyQuota: 1000000 },
        api_growth: { name: "API Growth", monthlyQuota: 10000000 },
        agent_standard: { name: "Agent Standard", monthlyQuota: 300000 },   // 10,000 calls/day × 30
        agent_pro: { name: "Agent Pro", monthlyQuota: 1500000 },             // 50,000 calls/day × 30
        enterprise: { name: "Enterprise", monthlyQuota: null },
    };

// Extended rate-limit table (includes tiers not yet in the Tier union)
const RATE_LIMITS: Record<string, { minute: number; day: number }> = {
    free: { minute: 100, day: 10000 },
    pro: { minute: 1000, day: 100000 },
    api_starter: { minute: 10000, day: 1000000 },
    api_growth: { minute: 100000, day: 10000000 },
    agent_standard: { minute: 10000, day: 300000 },    // 10,000 calls/day
    agent_pro: { minute: 50000, day: 1500000 },        // 50,000 calls/day
    enterprise: { minute: 999999, day: 999999999 },
};

export async function GET(req: Request) {
    const { userId } = auth();
    if (!userId) {
        return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    try {
        const tier = await getUserTier(userId);
        const tierConfig = TIER_CONFIG[tier] ?? TIER_CONFIG.free;
        const bq = getBigQuery();

        // Fetch 30-day daily breakdown (2xx/4xx/5xx counts)
        const dailyQuery = `
            SELECT
                FORMAT_DATE('%Y-%m-%d', DATE(ts)) as date,
                COUNTIF(status_code >= 200 AND status_code < 300) as count_2xx,
                COUNTIF(status_code >= 400 AND status_code < 500) as count_4xx,
                COUNTIF(status_code >= 500) as count_5xx
            FROM \`${PROJECT_ID}.${DATASET}.api_requests\`
            WHERE user_id = @userId
                AND ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
            GROUP BY date
            ORDER BY date DESC
        `;

        const [dailyJob] = await bq.createQueryJob({
            query: dailyQuery,
            params: { userId },
            types: { userId: "STRING" },
            jobTimeoutMs: 10000,
        });
        const [dailyRows] = await dailyJob.getQueryResults({
            timeoutMs: 10000,
        });

        // BigQuery COUNTIF results may come back as Int wrappers; coerce to number.
        const dailyRequests: DailyRequest[] = (
            dailyRows as Array<{
                date: string;
                count_2xx: unknown;
                count_4xx: unknown;
                count_5xx: unknown;
            }>
        )
            .map((row) => ({
                date: row.date,
                count_2xx: Number(row.count_2xx),
                count_4xx: Number(row.count_4xx),
                count_5xx: Number(row.count_5xx),
            }))
            .sort((a, b) => a.date.localeCompare(b.date));

        // Fetch top 10 endpoints (last 30 days)
        const endpointsQuery = `
            SELECT
                endpoint_path,
                COUNT(*) as count,
                ROUND(100 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) as pct
            FROM \`${PROJECT_ID}.${DATASET}.api_requests\`
            WHERE user_id = @userId
                AND ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
            GROUP BY endpoint_path
            ORDER BY count DESC
            LIMIT 10
        `;

        const [endpointsJob] = await bq.createQueryJob({
            query: endpointsQuery,
            params: { userId },
            types: { userId: "STRING" },
            jobTimeoutMs: 10000,
        });
        const [endpointRows] = await endpointsJob.getQueryResults({
            timeoutMs: 10000,
        });

        const topEndpoints: TopEndpoint[] = (
            endpointRows as Array<{
                endpoint_path: string;
                count: number;
                pct: number;
            }>
        ).map((row) => ({
            endpoint_path: row.endpoint_path,
            count: Number(row.count),
            pct: Number(row.pct),
        }));

        // Fetch current minute/day usage (for rate limit progress bars)
        const limitsQuery = `
            SELECT
                COUNTIF(ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 MINUTE)) as minute_current,
                COUNTIF(ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 DAY)) as day_current
            FROM \`${PROJECT_ID}.${DATASET}.api_requests\`
            WHERE user_id = @userId
        `;

        const [limitsJob] = await bq.createQueryJob({
            query: limitsQuery,
            params: { userId },
            types: { userId: "STRING" },
            jobTimeoutMs: 10000,
        });
        const [limitRows] = await limitsJob.getQueryResults({
            timeoutMs: 10000,
        });

        // BigQuery COUNTIF may return Int wrappers; coerce to number.
        const rawLimitRow =
            (limitRows as Array<Record<string, unknown>>)[0] ?? {};
        const limitRow = {
            minute_current: Number(rawLimitRow.minute_current ?? 0),
            day_current: Number(rawLimitRow.day_current ?? 0),
        };

        const limits = RATE_LIMITS[tier] ?? RATE_LIMITS.free;

        // Check if user has zero requests (empty state)
        const totalRequests =
            dailyRequests.reduce(
                (sum, day) =>
                    sum + day.count_2xx + day.count_4xx + day.count_5xx,
                0
            ) || 0;

        const response: UsageResponse = {
            currentTier: tier,
            tierName: tierConfig.name,
            monthlyQuota: tierConfig.monthlyQuota || limits.day,
            renewalDate: null, // TODO: integrate with Stripe subscription data
            dailyRequests,
            topEndpoints,
            rateLimitStatus: {
                minute_current: limitRow.minute_current,
                minute_limit: limits.minute,
                day_current: limitRow.day_current,
                day_limit: limits.day,
            },
            emptyState: totalRequests === 0,
        };

        // private + no-store: auth-gated user data must not be shared/CDN-cached
        return NextResponse.json(response, {
            headers: {
                "Cache-Control": "private, no-store",
            },
        });
    } catch (err) {
        console.error("[Usage API] Error:", err);
        return NextResponse.json(
            {
                error: "Failed to fetch usage data",
                currentTier: "free",
                tierName: "Free",
                monthlyQuota: 10000,
                renewalDate: null,
                dailyRequests: [],
                topEndpoints: [],
                rateLimitStatus: {
                    minute_current: 0,
                    minute_limit: 100,
                    day_current: 0,
                    day_limit: 10000,
                },
                emptyState: true,
            },
            { status: 200 } // Return 200 with fallback data on error
        );
    }
}
