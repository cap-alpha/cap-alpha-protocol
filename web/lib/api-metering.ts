/**
 * API request metering — fire-and-forget event recording to BigQuery.
 *
 * Records every paid API request to monetization.api_requests.
 * The call NEVER blocks the request path: a BQ outage will NOT fail the
 * API caller. All errors are logged and swallowed.
 *
 * Issue: #145
 */
import { BigQuery } from "@google-cloud/bigquery";
import { createHash } from "crypto";

export type CostClass = "cheap" | "expensive";

export interface MeteringEvent {
    /** Full key ID (capk_live_xxx) */
    keyId: string;
    userId: string;
    tier: string;
    /**
     * URL path template — e.g. /v1/pundits/{id}
     * Use the route pattern, not the resolved path, for grouping.
     */
    endpoint: string;
    /** Resolved URL path — e.g. /v1/pundits/adam-schefter */
    endpointPath: string;
    method: string;
    statusCode: number;
    latencyMs: number;
    bytesOut: number;
    userAgent?: string | null;
    /** Raw IP address — hashed with METERING_IP_PEPPER before storage */
    ip?: string | null;
    rateLimitHit: boolean;
    /**
     * "cheap" = KV reads, lookup endpoints (burns quota-A)
     * "expensive" = /ask, /backtest, semantic search (burns quota-B)
     */
    costClass: CostClass;
    /** Sport slug — defaults to "nfl". Populated for sport-agnostic API. */
    sport?: string;
}

const PROJECT_ID = process.env.GCP_PROJECT_ID ?? "cap-alpha-protocol";

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

/**
 * Hash an IP address for abuse-detection storage.
 *
 * Uses SHA-256(METERING_IP_PEPPER || ip). The pepper is never stored and
 * can be rotated to invalidate all historical hashes (GDPR-friendly).
 * Logs a warning (but does not fail) when METERING_IP_PEPPER is unset.
 */
export function hashIp(ip: string): string {
    const pepper = process.env.METERING_IP_PEPPER ?? "";
    if (!pepper) {
        console.warn(
            "[metering] METERING_IP_PEPPER is not set — IP hashes are unpepered"
        );
    }
    return createHash("sha256").update(pepper + ip).digest("hex");
}

/**
 * Record an API request for metering / usage analytics.
 *
 * Fire-and-forget: this function is synchronous from the caller's perspective.
 * It launches an async BQ insert without awaiting it, so it NEVER throws and
 * NEVER adds latency to the request path.
 *
 * Usage:
 *   const start = Date.now();
 *   // ... handle request ...
 *   recordApiRequest({
 *     keyId, userId, tier, endpoint, endpointPath, method,
 *     statusCode: 200, latencyMs: Date.now() - start,
 *     bytesOut: responseBody.length, ip: req.ip,
 *     rateLimitHit: false, costClass: "cheap",
 *   });
 *   return response;  // returns immediately; metering continues in background
 */
export function recordApiRequest(event: MeteringEvent): void {
    _insertEvent(event).catch((err) => {
        // BQ outage must not fail the API caller — log and swallow.
        console.error("[metering] Failed to record API request:", err);
    });
}

async function _insertEvent(event: MeteringEvent): Promise<void> {
    const bq = getBigQuery();
    const table = bq.dataset("monetization").table("api_requests");

    const row = {
        ts: new Date().toISOString(),
        key_id: event.keyId,
        user_id: event.userId,
        tier: event.tier,
        endpoint: event.endpoint,
        endpoint_path: event.endpointPath,
        method: event.method.toUpperCase(),
        status_code: event.statusCode,
        latency_ms: event.latencyMs,
        bytes_out: event.bytesOut,
        user_agent: event.userAgent ?? null,
        ip_hash: event.ip ? hashIp(event.ip) : null,
        rate_limit_hit: event.rateLimitHit,
        cost_class: event.costClass,
        sport: event.sport ?? "nfl",
    };

    await table.insert([row], { skipInvalidRows: false });
}
