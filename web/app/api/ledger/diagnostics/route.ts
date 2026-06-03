import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const BACKEND = "https://pundit-ledger-api-wvhvx2muna-uc.a.run.app";

/**
 * GET /api/ledger/diagnostics
 *
 * Temporary diagnostic endpoint — confirms whether CAP_ALPHA_INTERNAL_API_KEY
 * is present in the serverless runtime and whether the Cloud Run backend
 * accepts it.  Never exposes the key value.
 *
 * Remove once live-data flow is confirmed working.
 */
export async function GET() {
    const key = process.env.CAP_ALPHA_INTERNAL_API_KEY;
    const keyPresent = !!key;
    const keyLength = key ? key.length : 0;
    const keyPrefix = key ? key.slice(0, 4) + "…" : null;

    let backendStatus: number | null = null;
    let backendError: string | null = null;

    if (keyPresent) {
        try {
            const res = await fetch(`${BACKEND}/v1/pundits/?limit=1`, {
                headers: {
                    Accept: "application/json",
                    "x-api-key": key,
                },
                signal: AbortSignal.timeout(5000),
            });
            backendStatus = res.status;
        } catch (err) {
            backendError = err instanceof Error ? err.message : String(err);
        }
    } else {
        // Still probe without key to confirm 422 baseline
        try {
            const res = await fetch(`${BACKEND}/v1/pundits/?limit=1`, {
                headers: { Accept: "application/json" },
                signal: AbortSignal.timeout(5000),
            });
            backendStatus = res.status;
        } catch (err) {
            backendError = err instanceof Error ? err.message : String(err);
        }
    }

    return NextResponse.json(
        {
            key_present: keyPresent,
            key_length: keyLength,
            key_prefix: keyPrefix,
            backend_url: BACKEND,
            backend_status: backendStatus,
            backend_error: backendError,
            // 200 = live data will flow; 401 = wrong key value; 422 = key missing in env
            diagnosis:
                !keyPresent
                    ? "KEY_MISSING_IN_ENV"
                    : backendStatus === 200
                      ? "OK_LIVE_DATA_SHOULD_FLOW"
                      : backendStatus === 401
                        ? "KEY_PRESENT_BUT_WRONG_VALUE"
                        : backendStatus === 422
                          ? "KEY_PRESENT_BUT_NOT_SENT_CHECK_CODE"
                          : `UNEXPECTED_STATUS_${backendStatus}`,
        },
        {
            status: 200,
            headers: { "Cache-Control": "no-store" },
        }
    );
}
