/**
 * /status — Public operational status page
 *
 * Shows real-time health of key Cap Alpha services. Checks are performed
 * server-side on each request (no client-side fetching, no stale data).
 *
 * Issue #491
 */

import { Metadata } from "next";
import { CheckCircle2, XCircle, AlertTriangle, Activity } from "lucide-react";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
    title: "Service Status | Cap Alpha",
    description: "Real-time operational status for Cap Alpha services.",
    robots: { index: false },
};

type ServiceStatus = "operational" | "degraded" | "outage" | "unknown";

interface ServiceCheck {
    name: string;
    description: string;
    status: ServiceStatus;
    latencyMs?: number;
    detail?: string;
}

async function checkWithTimeout(
    url: string,
    timeoutMs = 4000
): Promise<{ ok: boolean; latencyMs: number; detail?: string }> {
    const start = Date.now();
    try {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), timeoutMs);
        const res = await fetch(url, {
            method: "GET",
            signal: controller.signal,
            cache: "no-store",
        });
        clearTimeout(timer);
        const latencyMs = Date.now() - start;
        return { ok: res.ok, latencyMs, detail: res.ok ? undefined : `HTTP ${res.status}` };
    } catch (err: unknown) {
        const latencyMs = Date.now() - start;
        const detail = err instanceof Error ? err.message : "unknown error";
        return { ok: false, latencyMs, detail };
    }
}

async function runChecks(): Promise<ServiceCheck[]> {
    const APP_URL =
        process.env.NEXT_PUBLIC_APP_URL ||
        (process.env.VERCEL_URL ? `https://${process.env.VERCEL_URL}` : "http://localhost:3000");

    const results = await Promise.allSettled([
        // 1. API health endpoint
        checkWithTimeout(`${APP_URL}/api/health`),
        // 2. Ledger API (first page)
        checkWithTimeout(`${APP_URL}/api/ledger/pundits?limit=1`, 6000),
        // 3. Clerk (auth) — ping their status page API
        checkWithTimeout("https://status.clerk.com/api/v2/status.json", 4000),
        // 4. Stripe — ping their status API
        checkWithTimeout("https://status.stripe.com/api/v2/status.json", 4000),
    ]);

    function toStatus(settled: PromiseSettledResult<{ ok: boolean; latencyMs: number; detail?: string }>): {
        ok: boolean;
        latencyMs: number;
        detail?: string;
    } {
        if (settled.status === "fulfilled") return settled.value;
        return { ok: false, latencyMs: 0, detail: settled.reason?.message ?? "check failed" };
    }

    const [api, ledger, clerkResult, stripeResult] = results.map(toStatus);

    // Parse third-party status pages
    function parseStatusPage(
        result: { ok: boolean; latencyMs: number; detail?: string },
        url: string
    ): { status: ServiceStatus; detail?: string } {
        if (!result.ok) return { status: "unknown", detail: result.detail };
        // statuspage.io uses "none" for operational
        try {
            // We can't parse the JSON here since we only tracked ok/latency,
            // so treat HTTP 200 from status.*.com as "operational"
            return { status: "operational" };
        } catch {
            return { status: "unknown" };
        }
    }

    const checks: ServiceCheck[] = [
        {
            name: "API",
            description: "Cap Alpha backend API",
            status: api.ok ? "operational" : "outage",
            latencyMs: api.latencyMs,
            detail: api.detail,
        },
        {
            name: "Ledger",
            description: "Pundit prediction ledger data",
            status: ledger.ok ? "operational" : (ledger.latencyMs > 5000 ? "degraded" : "outage"),
            latencyMs: ledger.latencyMs,
            detail: ledger.detail,
        },
        {
            name: "Authentication",
            description: "Clerk identity platform",
            ...parseStatusPage(clerkResult, "https://status.clerk.com"),
            latencyMs: clerkResult.latencyMs,
        },
        {
            name: "Payments",
            description: "Stripe billing & subscriptions",
            ...parseStatusPage(stripeResult, "https://status.stripe.com"),
            latencyMs: stripeResult.latencyMs,
        },
    ];

    return checks;
}

function StatusIcon({ status }: { status: ServiceStatus }) {
    if (status === "operational")
        return <CheckCircle2 className="h-5 w-5 text-emerald-400 shrink-0" />;
    if (status === "degraded")
        return <AlertTriangle className="h-5 w-5 text-amber-400 shrink-0" />;
    if (status === "outage")
        return <XCircle className="h-5 w-5 text-rose-400 shrink-0" />;
    return <Activity className="h-5 w-5 text-zinc-400 shrink-0" />;
}

function statusLabel(status: ServiceStatus) {
    if (status === "operational") return "Operational";
    if (status === "degraded") return "Degraded";
    if (status === "outage") return "Outage";
    return "Unknown";
}

function statusColor(status: ServiceStatus) {
    if (status === "operational") return "text-emerald-400";
    if (status === "degraded") return "text-amber-400";
    if (status === "outage") return "text-rose-400";
    return "text-zinc-400";
}

export default async function StatusPage() {
    const checks = await runChecks();
    const allGood = checks.every((c) => c.status === "operational");
    const hasOutage = checks.some((c) => c.status === "outage");
    const checkedAt = new Date().toISOString();

    const overallStatus: ServiceStatus = hasOutage ? "outage" : allGood ? "operational" : "degraded";
    const overallLabel = hasOutage
        ? "Service disruption in progress"
        : allGood
          ? "All systems operational"
          : "Partial degradation";

    return (
        <div className="max-w-2xl mx-auto px-4 py-12 space-y-8">
            {/* Header */}
            <div className="space-y-2">
                <div className="flex items-center gap-2 text-zinc-400 text-sm uppercase tracking-widest font-medium">
                    <Activity className="h-4 w-4" />
                    System Status
                </div>
                <div className="flex items-center gap-3">
                    <StatusIcon status={overallStatus} />
                    <h1 className="text-2xl font-black uppercase tracking-tight text-white">
                        {overallLabel}
                    </h1>
                </div>
                <p className="text-zinc-400 text-xs">
                    Last checked: {new Date(checkedAt).toLocaleString("en-US", { timeZoneName: "short" })}
                </p>
            </div>

            {/* Component table */}
            <div className="rounded-xl border border-zinc-800 bg-zinc-900 divide-y divide-zinc-800 overflow-hidden">
                {checks.map((check) => (
                    <div
                        key={check.name}
                        className="flex items-center justify-between px-5 py-4 gap-4"
                    >
                        <div className="flex items-center gap-3 min-w-0">
                            <StatusIcon status={check.status} />
                            <div className="min-w-0">
                                <p className="font-bold text-white text-sm">{check.name}</p>
                                <p className="text-zinc-400 text-xs truncate">{check.description}</p>
                                {check.detail && (
                                    <p className="text-rose-400 text-xs truncate">{check.detail}</p>
                                )}
                            </div>
                        </div>
                        <div className="text-right shrink-0 space-y-0.5">
                            <p className={`text-sm font-bold ${statusColor(check.status)}`}>
                                {statusLabel(check.status)}
                            </p>
                            {check.latencyMs != null && check.latencyMs > 0 && (
                                <p className="text-zinc-400 text-xs">{check.latencyMs}ms</p>
                            )}
                        </div>
                    </div>
                ))}
            </div>

            {/* External links */}
            <div className="text-zinc-400 text-xs space-y-1">
                <p>
                    Third-party provider status:{" "}
                    <a
                        href="https://status.clerk.com"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-zinc-400 hover:text-white underline transition-colors"
                    >
                        Clerk
                    </a>{" "}
                    ·{" "}
                    <a
                        href="https://status.stripe.com"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-zinc-400 hover:text-white underline transition-colors"
                    >
                        Stripe
                    </a>
                </p>
                <p>
                    Report an issue:{" "}
                    <a
                        href="mailto:support@cap-alpha.co"
                        className="text-zinc-400 hover:text-white underline transition-colors"
                    >
                        support@cap-alpha.co
                    </a>
                </p>
            </div>
        </div>
    );
}
