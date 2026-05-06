"use client";

import React, { useState, useEffect } from "react";
import {
    BarChart,
    Bar,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    ResponsiveContainer,
} from "recharts";
import {
    TrendingUp,
    Zap,
    AlertTriangle,
    Activity,
    ArrowRight,
    Shield,
} from "lucide-react";
import { cn } from "@/lib/utils";

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

interface UsageData {
    currentTier: string;
    tierName: string;
    monthlyQuota: number;
    renewalDate: string | null;
    dailyRequests: DailyRequest[];
    topEndpoints: TopEndpoint[];
    rateLimitStatus: RateLimitStatus;
    emptyState: boolean;
}

function formatNumber(n: number): string {
    if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
    if (n >= 1_000) return (n / 1_000).toFixed(1) + "K";
    return n.toString();
}

function getTierBadge(tier: string, tierName: string) {
    const styles: Record<string, string> = {
        free: "bg-zinc-800 text-zinc-300 ring-zinc-700",
        pro: "bg-blue-900/40 text-blue-300 ring-blue-500/40",
        agent: "bg-purple-900/40 text-purple-300 ring-purple-500/40",
        api_starter: "bg-emerald-900/40 text-emerald-300 ring-emerald-500/40",
        api_growth: "bg-amber-900/40 text-amber-300 ring-amber-500/40",
        enterprise: "bg-red-900/40 text-red-300 ring-red-500/40",
    };
    const cls = styles[tier] ?? styles.free;
    return (
        <span
            className={cn(
                "inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold font-mono uppercase tracking-wider ring-1",
                cls
            )}
        >
            {tierName}
        </span>
    );
}

function RateLimitBar({
    current,
    limit,
    label,
}: {
    current: number;
    limit: number;
    label: string;
}) {
    const pct = Math.min((current / limit) * 100, 100);
    const barColor =
        pct > 80 ? "bg-red-500" : pct > 50 ? "bg-amber-500" : "bg-emerald-500";

    return (
        <div>
            <div className="flex justify-between mb-1.5">
                <span className="text-xs font-mono text-zinc-400">{label}</span>
                <span className="text-xs font-mono text-zinc-400 tabular-nums">
                    {formatNumber(current)} / {formatNumber(limit)}
                </span>
            </div>
            <div className="w-full bg-zinc-800 rounded-full h-1.5 overflow-hidden">
                <div
                    className={cn(
                        "h-full rounded-full transition-all",
                        barColor
                    )}
                    style={{ width: `${pct}%` }}
                />
            </div>
        </div>
    );
}

export function UsageDashboard() {
    const [data, setData] = useState<UsageData | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        fetch("/api/dashboard/usage")
            .then((res) => {
                if (!res.ok) {
                    throw new Error(`Usage API returned ${res.status}`);
                }
                return res.json();
            })
            .then((d: UsageData) => {
                setData(d);
                setLoading(false);
            })
            .catch((err) => {
                console.error("Failed to fetch usage data:", err);
                setLoading(false);
            });
    }, []);

    if (loading) {
        return (
            <div className="flex items-center justify-center h-48 text-zinc-400">
                <Activity className="w-4 h-4 animate-pulse mr-2" />
                <span className="font-mono text-sm">Loading usage data…</span>
            </div>
        );
    }

    if (!data) {
        return (
            <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 py-16 text-center text-zinc-400 text-sm">
                Could not load usage metrics. Please try again later.
            </div>
        );
    }

    const totalRequests = data.dailyRequests.reduce(
        (sum, day) => sum + day.count_2xx + day.count_4xx + day.count_5xx,
        0
    );
    const total2xx = data.dailyRequests.reduce(
        (sum, day) => sum + day.count_2xx,
        0
    );
    const successRate =
        totalRequests > 0
            ? ((total2xx / totalRequests) * 100).toFixed(1)
            : "100";

    // Use actual rate-limit usage from the rate limit status rather than
    // inferring from 4xx counts (which include 401/404, not just 429s).
    const dayLimitPct =
        data.rateLimitStatus.day_limit > 0
            ? (data.rateLimitStatus.day_current /
                  data.rateLimitStatus.day_limit) *
              100
            : 0;
    const nearDayLimit = dayLimitPct >= 80;

    const shouldShowUpgradeBanner = nearDayLimit && data.currentTier === "free";

    const chartData = data.dailyRequests.map((day) => ({
        ...day,
        label: new Date(day.date + "T00:00:00").toLocaleDateString("en-US", {
            month: "short",
            day: "numeric",
        }),
    }));

    return (
        <div className="space-y-6">
            {/* ----------------------------------------------------------------
                Tier + quota summary
            ---------------------------------------------------------------- */}
            <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-6">
                <div className="flex items-start justify-between gap-4 mb-6">
                    <div>
                        <div className="flex items-center gap-2 mb-1">
                            <Shield className="w-4 h-4 text-emerald-400" />
                            <span className="text-xs font-mono uppercase tracking-widest text-emerald-400">
                                Subscription
                            </span>
                        </div>
                        <h2 className="text-xl font-black tracking-tight text-white">
                            Your Plan
                        </h2>
                    </div>
                    {getTierBadge(data.currentTier, data.tierName)}
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
                    <div>
                        <p className="text-xs font-mono uppercase tracking-widest text-zinc-400 mb-1">
                            Monthly Quota
                        </p>
                        <p className="text-2xl font-black font-mono text-white tabular-nums">
                            {formatNumber(data.monthlyQuota)}
                        </p>
                        <p className="text-xs text-zinc-400 font-mono mt-0.5">
                            {totalRequests > 0
                                ? `${formatNumber(totalRequests)} used (30d)`
                                : "No requests yet"}
                        </p>
                    </div>
                    <div>
                        <p className="text-xs font-mono uppercase tracking-widest text-zinc-400 mb-1">
                            Success Rate
                        </p>
                        <p className="text-2xl font-black font-mono text-emerald-400 tabular-nums">
                            {successRate}%
                        </p>
                        <p className="text-xs text-zinc-400 font-mono mt-0.5">
                            2xx responses
                        </p>
                    </div>
                    <div>
                        <p className="text-xs font-mono uppercase tracking-widest text-zinc-400 mb-1">
                            Resets On
                        </p>
                        <p className="text-2xl font-black font-mono text-white tabular-nums">
                            {data.renewalDate
                                ? new Date(data.renewalDate).toLocaleDateString(
                                      "en-US",
                                      { month: "short", day: "numeric" }
                                  )
                                : "Next month"}
                        </p>
                        <p className="text-xs text-zinc-400 font-mono mt-0.5">
                            Quota cycle
                        </p>
                    </div>
                </div>
            </div>

            {/* ----------------------------------------------------------------
                Upgrade CTA (free tier users who hit rate limits)
            ---------------------------------------------------------------- */}
            {shouldShowUpgradeBanner && (
                <div className="rounded-xl border border-amber-500/30 bg-amber-900/20 p-5 flex items-start gap-4">
                    <AlertTriangle className="w-5 h-5 text-amber-400 mt-0.5 shrink-0" />
                    <div className="flex-1 min-w-0">
                        <p className="text-sm font-semibold text-amber-300">
                            Approaching your daily rate limit (
                            {Math.round(dayLimitPct)}% used)
                        </p>
                        <p className="text-xs text-amber-400/80 mt-0.5">
                            Upgrade to Pro for 10× higher quotas and priority
                            throughput.
                        </p>
                    </div>
                    <a
                        href="/pricing"
                        className="shrink-0 inline-flex items-center gap-1.5 rounded-lg bg-amber-500 hover:bg-amber-400 transition-colors px-4 py-2 text-xs font-bold text-black uppercase tracking-wide"
                    >
                        Upgrade <ArrowRight className="w-3 h-3" />
                    </a>
                </div>
            )}

            {/* Free-tier upgrade nudge (no rate-limit hits yet) */}
            {!shouldShowUpgradeBanner && data.currentTier === "free" && (
                <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-5 flex items-center justify-between gap-4">
                    <div>
                        <p className="text-sm font-semibold text-white">
                            You&apos;re on the Free tier
                        </p>
                        <p className="text-xs text-zinc-400 mt-0.5">
                            Upgrade to Pro for higher rate limits, more
                            endpoints, and priority support.
                        </p>
                    </div>
                    <a
                        href="/pricing"
                        className="shrink-0 inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 transition-colors px-4 py-2 text-xs font-bold text-white uppercase tracking-wide"
                    >
                        Upgrade to Pro <ArrowRight className="w-3 h-3" />
                    </a>
                </div>
            )}

            {/* ----------------------------------------------------------------
                Empty state
            ---------------------------------------------------------------- */}
            {data.emptyState && (
                <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-6">
                    <div className="flex items-center gap-2 mb-3">
                        <Zap className="w-4 h-4 text-emerald-400" />
                        <span className="text-sm font-semibold text-white">
                            No API requests yet
                        </span>
                    </div>
                    <p className="text-xs text-zinc-400 mb-4">
                        Create an API key and make your first request to start
                        seeing stats.
                    </p>
                    <pre className="bg-zinc-950 border border-zinc-800 rounded-lg p-4 text-xs font-mono text-emerald-400 overflow-x-auto">
                        {`curl -H "Authorization: Bearer YOUR_API_KEY" \\\n  https://api.pundit-ledger.com/v1/pundits`}
                    </pre>
                </div>
            )}

            {/* ----------------------------------------------------------------
                Request history chart
            ---------------------------------------------------------------- */}
            {!data.emptyState && (
                <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-6">
                    <div className="flex items-center gap-2 mb-1">
                        <TrendingUp className="w-4 h-4 text-emerald-400" />
                        <span className="text-xs font-mono uppercase tracking-widest text-emerald-400">
                            Request History
                        </span>
                    </div>
                    <h3 className="text-lg font-black tracking-tight text-white mb-1">
                        Last 30 Days
                    </h3>
                    <p className="text-xs text-zinc-400 font-mono mb-5">
                        Stacked by response status — 2xx / 4xx / 5xx
                    </p>

                    {totalRequests > 0 ? (
                        <ResponsiveContainer width="100%" height={260}>
                            <BarChart
                                data={chartData}
                                margin={{ top: 0, right: 0, left: -20, bottom: 0 }}
                            >
                                <CartesianGrid
                                    strokeDasharray="3 3"
                                    stroke="#27272a"
                                    vertical={false}
                                />
                                <XAxis
                                    dataKey="label"
                                    tick={{ fontSize: 11, fill: "#71717a" }}
                                    axisLine={false}
                                    tickLine={false}
                                    interval={chartData.length > 14 ? 2 : 0}
                                />
                                <YAxis
                                    tick={{ fontSize: 11, fill: "#71717a" }}
                                    axisLine={false}
                                    tickLine={false}
                                    tickFormatter={formatNumber}
                                />
                                <Tooltip
                                    contentStyle={{
                                        background: "#18181b",
                                        border: "1px solid #3f3f46",
                                        borderRadius: 8,
                                        fontSize: 12,
                                    }}
                                    labelStyle={{ color: "#a1a1aa" }}
                                    itemStyle={{ color: "#e4e4e7" }}
                                    formatter={(value) =>
                                        formatNumber(Number(value))
                                    }
                                />
                                <Bar
                                    dataKey="count_2xx"
                                    name="2xx Success"
                                    fill="#10b981"
                                    stackId="a"
                                    radius={[0, 0, 0, 0]}
                                />
                                <Bar
                                    dataKey="count_4xx"
                                    name="4xx Client Error"
                                    fill="#f59e0b"
                                    stackId="a"
                                />
                                <Bar
                                    dataKey="count_5xx"
                                    name="5xx Server Error"
                                    fill="#ef4444"
                                    stackId="a"
                                    radius={[2, 2, 0, 0]}
                                />
                            </BarChart>
                        </ResponsiveContainer>
                    ) : (
                        <div className="h-40 flex items-center justify-center text-zinc-400 text-sm font-mono">
                            No request data in the last 30 days
                        </div>
                    )}
                </div>
            )}

            {/* ----------------------------------------------------------------
                Rate limit status
            ---------------------------------------------------------------- */}
            <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-6">
                <div className="mb-1">
                    <span className="text-xs font-mono uppercase tracking-widest text-emerald-400">
                        Rate Limits
                    </span>
                </div>
                <h3 className="text-lg font-black tracking-tight text-white mb-5">
                    Current Usage
                </h3>
                <div className="space-y-5">
                    <RateLimitBar
                        current={data.rateLimitStatus.minute_current}
                        limit={data.rateLimitStatus.minute_limit}
                        label="Requests / minute"
                    />
                    <RateLimitBar
                        current={data.rateLimitStatus.day_current}
                        limit={data.rateLimitStatus.day_limit}
                        label="Requests / day"
                    />
                </div>
            </div>

            {/* ----------------------------------------------------------------
                Top endpoints
            ---------------------------------------------------------------- */}
            {!data.emptyState && data.topEndpoints.length > 0 && (
                <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-6">
                    <div className="mb-1">
                        <span className="text-xs font-mono uppercase tracking-widest text-emerald-400">
                            Endpoints
                        </span>
                    </div>
                    <h3 className="text-lg font-black tracking-tight text-white mb-5">
                        Top 10 (Last 30 Days)
                    </h3>

                    {/* Column headers */}
                    <div className="grid grid-cols-[1fr_80px_60px] gap-3 px-2 pb-2 text-[10px] font-mono uppercase tracking-widest text-zinc-400">
                        <span>Endpoint</span>
                        <span className="text-right">Requests</span>
                        <span className="text-right">%</span>
                    </div>

                    <div className="space-y-1">
                        {data.topEndpoints.map((ep, idx) => (
                            <div
                                key={idx}
                                className="grid grid-cols-[1fr_80px_60px] gap-3 items-center rounded-lg px-2 py-2.5 bg-zinc-900/60 border border-zinc-800/60"
                            >
                                <span className="text-xs font-mono text-zinc-300 truncate">
                                    {ep.endpoint_path}
                                </span>
                                <span className="text-xs font-mono text-white text-right tabular-nums">
                                    {formatNumber(ep.count)}
                                </span>
                                <span className="text-xs font-mono text-zinc-400 text-right tabular-nums">
                                    {ep.pct}%
                                </span>
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}
