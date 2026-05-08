import { Metadata } from "next";
import { CheckCircle2, XCircle, AlertTriangle, Activity, BarChart3, Database, Shield, TrendingUp } from "lucide-react";
import type { QualityResponse, WaitlistGate } from "@/app/api/quality/route";

export const revalidate = 300;

export const metadata: Metadata = {
    title: "Extraction Quality Dashboard | Pundit Ledger",
    description:
        "Live extraction quality metrics — testability scores, claim promotion rates, and waitlist-removal gate status.",
};

const INTERNAL_API_BASE =
    process.env.NEXT_PUBLIC_APP_URL ||
    (process.env.VERCEL_URL
        ? `https://${process.env.VERCEL_URL}`
        : "http://localhost:3000");

const FASTAPI_BASE =
    process.env.NEXT_PUBLIC_API_URL ||
    "https://pundit-ledger-api-wvhvx2muna-uc.a.run.app";

// ---------------------------------------------------------------------------
// Types for FastAPI backend responses
// ---------------------------------------------------------------------------

interface ExtractionHealthDay {
    run_date: string;
    utterances_written: number;
    claims_promoted: number;
    zero_output: boolean;
    mean_testability_score: number;
}

interface ExtractionHealthResponse {
    last_30_days: ExtractionHealthDay[];
    zero_output_rate_pct: number;
    testability_trend: "improving" | "declining" | "stable";
}

interface CategoryStat {
    category: string;
    count: number;
    resolution_rate_pct: number;
    void_rate_pct: number;
}

interface WeeklyBrier {
    week: string;
    mean_brier_score: number;
    n: number;
}

interface ResolutionStatsResponse {
    resolution_rate_pct: number;
    void_rate_pct: number;
    by_category: CategoryStat[];
    weekly_brier: WeeklyBrier[];
}

// ---------------------------------------------------------------------------
// Data fetchers
// ---------------------------------------------------------------------------

async function getQualityData(): Promise<QualityResponse> {
    try {
        const res = await fetch(`${INTERNAL_API_BASE}/api/quality`, {
            next: { revalidate: 300 },
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
    } catch {
        return {
            dailyTrend: [],
            punditStats: [],
            dataQuality: {
                null_metadata_pct: 0,
                pct_rows_with_complete_metadata: 1,
                zero_output_runs_7d: 0,
                provider_mix: {},
                resolution_accuracy: null,
            },
            waitlistGates: [],
            generatedAt: new Date().toISOString(),
            hasData: false,
        };
    }
}

async function getExtractionHealth(): Promise<ExtractionHealthResponse | null> {
    try {
        const res = await fetch(
            `${FASTAPI_BASE}/v1/quality/extraction-health`,
            { next: { revalidate: 300 } }
        );
        if (!res.ok) return null;
        return res.json();
    } catch {
        return null;
    }
}

async function getResolutionStats(): Promise<ResolutionStatsResponse | null> {
    try {
        const res = await fetch(
            `${FASTAPI_BASE}/v1/quality/resolution-stats`,
            { next: { revalidate: 300 } }
        );
        if (!res.ok) return null;
        return res.json();
    } catch {
        return null;
    }
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function GateCard({ gate }: { gate: WaitlistGate }) {
    const Icon = gate.pass ? CheckCircle2 : XCircle;
    const color = gate.pass
        ? "text-emerald-400 border-emerald-500/30 bg-emerald-500/10"
        : "text-red-400 border-red-500/30 bg-red-500/10";
    const iconColor = gate.pass ? "text-emerald-400" : "text-red-400";

    return (
        <div className={`rounded-xl border p-4 ${color.split(" ").slice(1).join(" ")} space-y-2`}>
            <div className="flex items-start gap-3">
                <Icon className={`w-5 h-5 mt-0.5 shrink-0 ${iconColor}`} />
                <div className="space-y-1 min-w-0">
                    <p className="text-sm font-semibold text-zinc-100 leading-snug">
                        {gate.label}
                    </p>
                    <p className="text-xs text-zinc-400 leading-relaxed">
                        {gate.description}
                    </p>
                    {gate.current_value !== null && (
                        <p className="text-xs font-mono text-zinc-500">
                            Current:{" "}
                            <span className={gate.pass ? "text-emerald-400" : "text-amber-400"}>
                                {gate.id === "zero_output"
                                    ? String(gate.current_value)
                                    : `${(gate.current_value * 100).toFixed(1)}%`}
                            </span>{" "}
                            / target{" "}
                            {gate.id === "zero_output"
                                ? "0 runs"
                                : `${(gate.threshold * 100).toFixed(0)}%`}
                        </p>
                    )}
                </div>
            </div>
        </div>
    );
}

function StatTile({
    label,
    value,
    sub,
    ok,
}: {
    label: string;
    value: string;
    sub?: string;
    ok?: boolean;
}) {
    return (
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-4 space-y-1">
            <p className="text-xs text-zinc-500 uppercase tracking-widest font-mono">
                {label}
            </p>
            <p
                className={`text-2xl font-black tabular-nums ${
                    ok === undefined
                        ? "text-white"
                        : ok
                        ? "text-emerald-400"
                        : "text-amber-400"
                }`}
            >
                {value}
            </p>
            {sub && <p className="text-xs text-zinc-600">{sub}</p>}
        </div>
    );
}

function SectionHeader({
    icon: Icon,
    title,
    subtitle,
}: {
    icon: React.ElementType;
    title: string;
    subtitle?: string;
}) {
    return (
        <div className="flex items-center gap-3 mb-5">
            <div className="w-8 h-8 rounded-lg bg-zinc-800 flex items-center justify-center">
                <Icon className="w-4 h-4 text-zinc-400" />
            </div>
            <div>
                <h2 className="text-base font-bold text-white">{title}</h2>
                {subtitle && (
                    <p className="text-xs text-zinc-500">{subtitle}</p>
                )}
            </div>
        </div>
    );
}

function TrendBadge({ trend }: { trend: string }) {
    const map: Record<string, { label: string; cls: string }> = {
        improving: { label: "Improving", cls: "text-emerald-400 bg-emerald-500/10 border-emerald-500/30" },
        declining: { label: "Declining", cls: "text-red-400 bg-red-500/10 border-red-500/30" },
        stable: { label: "Stable", cls: "text-zinc-400 bg-zinc-800 border-zinc-700" },
    };
    const { label, cls } = map[trend] ?? map.stable;
    return (
        <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-mono font-semibold ${cls}`}>
            {label}
        </span>
    );
}

// ---------------------------------------------------------------------------
// Panel 1 — Extraction Health (from FastAPI)
// ---------------------------------------------------------------------------

function ExtractionHealthPanel({ data }: { data: ExtractionHealthResponse }) {
    const days = data.last_30_days.slice(-14); // show last 14 for readability

    return (
        <section>
            <SectionHeader
                icon={Activity}
                title="Extraction Health (last 30 days)"
                subtitle="From silver_v2_claims.extraction_run — 5 min cache"
            />

            {/* Summary row */}
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 mb-6">
                <StatTile
                    label="Zero-output rate"
                    value={`${data.zero_output_rate_pct}%`}
                    sub="days with 0 utterances written"
                    ok={data.zero_output_rate_pct === 0}
                />
                <StatTile
                    label="Testability trend"
                    value={data.testability_trend.charAt(0).toUpperCase() + data.testability_trend.slice(1)}
                    sub="week-over-week direction"
                    ok={data.testability_trend !== "declining"}
                />
                <StatTile
                    label="Days in window"
                    value={String(data.last_30_days.length)}
                    sub="run days in last 30 days"
                />
            </div>

            {/* Table */}
            <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 overflow-hidden">
                <div className="overflow-x-auto">
                    <table className="w-full text-xs text-left">
                        <thead>
                            <tr className="border-b border-zinc-800 bg-zinc-900 text-zinc-500 font-mono uppercase tracking-wider">
                                <th className="px-4 py-3">Date</th>
                                <th className="px-4 py-3 text-right">Utterances</th>
                                <th className="px-4 py-3 text-right">Claims</th>
                                <th className="px-4 py-3 text-right">Testability</th>
                                <th className="px-4 py-3">Zero Output</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-zinc-900">
                            {days.map((day) => (
                                <tr key={day.run_date} className="text-zinc-300 hover:bg-zinc-900/40">
                                    <td className="px-4 py-2.5 font-mono text-zinc-400">
                                        {day.run_date}
                                    </td>
                                    <td className="px-4 py-2.5 text-right tabular-nums font-mono">
                                        <span className={day.utterances_written === 0 ? "text-red-400 font-bold" : ""}>
                                            {day.utterances_written.toLocaleString()}
                                        </span>
                                    </td>
                                    <td className="px-4 py-2.5 text-right tabular-nums font-mono">
                                        {day.claims_promoted.toLocaleString()}
                                    </td>
                                    <td className="px-4 py-2.5 text-right tabular-nums font-mono">
                                        <span className={
                                            day.mean_testability_score >= 0.65
                                                ? "text-emerald-400"
                                                : day.mean_testability_score >= 0.5
                                                ? "text-amber-400"
                                                : "text-red-400"
                                        }>
                                            {(day.mean_testability_score * 100).toFixed(1)}%
                                        </span>
                                    </td>
                                    <td className="px-4 py-2.5">
                                        {day.zero_output ? (
                                            <span className="inline-flex items-center gap-1 text-red-400 font-mono">
                                                <XCircle className="w-3 h-3" /> Yes
                                            </span>
                                        ) : (
                                            <span className="text-zinc-600 font-mono">—</span>
                                        )}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
                <div className="px-4 py-3 border-t border-zinc-800 text-xs text-zinc-600">
                    Showing last {days.length} of {data.last_30_days.length} run days.
                    Trend: <TrendBadge trend={data.testability_trend} />
                </div>
            </div>
        </section>
    );
}

// ---------------------------------------------------------------------------
// Panel 2 — Resolution Rate (from FastAPI)
// ---------------------------------------------------------------------------

function ResolutionRatePanel({ data }: { data: ResolutionStatsResponse }) {
    return (
        <section>
            <SectionHeader
                icon={Shield}
                title="Resolution Rate by Category"
                subtitle="From gold_layer.prediction_ledger + prediction_resolutions — 5 min cache"
            />

            {/* Header stats */}
            <div className="grid grid-cols-2 gap-4 mb-6">
                <StatTile
                    label="Overall resolution rate"
                    value={`${data.resolution_rate_pct}%`}
                    sub="predictions resolved / total"
                    ok={data.resolution_rate_pct >= 50}
                />
                <StatTile
                    label="Void rate"
                    value={`${data.void_rate_pct}%`}
                    sub="voided predictions / total"
                    ok={data.void_rate_pct <= 10}
                />
            </div>

            {/* Per-category table */}
            <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 overflow-hidden">
                <div className="overflow-x-auto">
                    <table className="w-full text-xs text-left">
                        <thead>
                            <tr className="border-b border-zinc-800 bg-zinc-900 text-zinc-500 font-mono uppercase tracking-wider">
                                <th className="px-4 py-3">Category</th>
                                <th className="px-4 py-3 text-right">Count</th>
                                <th className="px-4 py-3 text-right">Resolution %</th>
                                <th className="px-4 py-3 text-right">Void %</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-zinc-900">
                            {data.by_category.map((cat) => (
                                <tr key={cat.category} className="text-zinc-300 hover:bg-zinc-900/40">
                                    <td className="px-4 py-2.5 font-mono text-zinc-200 capitalize">
                                        {cat.category.replace(/_/g, " ")}
                                    </td>
                                    <td className="px-4 py-2.5 text-right tabular-nums font-mono text-zinc-400">
                                        {cat.count.toLocaleString()}
                                    </td>
                                    <td className="px-4 py-2.5 text-right tabular-nums font-mono">
                                        <span className={
                                            cat.resolution_rate_pct >= 70
                                                ? "text-emerald-400"
                                                : cat.resolution_rate_pct >= 40
                                                ? "text-amber-400"
                                                : "text-zinc-400"
                                        }>
                                            {cat.resolution_rate_pct}%
                                        </span>
                                    </td>
                                    <td className="px-4 py-2.5 text-right tabular-nums font-mono">
                                        <span className={cat.void_rate_pct > 15 ? "text-amber-400" : "text-zinc-500"}>
                                            {cat.void_rate_pct}%
                                        </span>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>
        </section>
    );
}

// ---------------------------------------------------------------------------
// Panel 3 — Brier Score Trend (from FastAPI)
// ---------------------------------------------------------------------------

function BrierTrendPanel({ data }: { data: ResolutionStatsResponse }) {
    const weeks = data.weekly_brier.slice(-12);

    if (weeks.length === 0) {
        return (
            <section>
                <SectionHeader
                    icon={TrendingUp}
                    title="Brier Score Trend (last 12 weeks)"
                    subtitle="Mean Brier score per week — lower is better"
                />
                <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-10 text-center space-y-3">
                    <Database className="w-8 h-8 text-zinc-600 mx-auto" />
                    <p className="text-zinc-400 font-medium">No Brier data yet</p>
                    <p className="text-sm text-zinc-600">
                        Appears once predictions are resolved with confidence scores.
                    </p>
                </div>
            </section>
        );
    }

    return (
        <section>
            <SectionHeader
                icon={TrendingUp}
                title="Brier Score Trend (last 12 weeks)"
                subtitle="Mean Brier score per week — lower is better (0 = perfect)"
            />
            <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 overflow-hidden">
                <div className="overflow-x-auto">
                    <table className="w-full text-xs text-left">
                        <thead>
                            <tr className="border-b border-zinc-800 bg-zinc-900 text-zinc-500 font-mono uppercase tracking-wider">
                                <th className="px-4 py-3">Week of</th>
                                <th className="px-4 py-3 text-right">Mean Brier</th>
                                <th className="px-4 py-3 text-right">n</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-zinc-900">
                            {weeks.map((w) => (
                                <tr key={w.week} className="text-zinc-300 hover:bg-zinc-900/40">
                                    <td className="px-4 py-2.5 font-mono text-zinc-400">
                                        {w.week}
                                    </td>
                                    <td className="px-4 py-2.5 text-right tabular-nums font-mono">
                                        <span className={
                                            w.mean_brier_score <= 0.1
                                                ? "text-emerald-400 font-semibold"
                                                : w.mean_brier_score <= 0.2
                                                ? "text-amber-400"
                                                : "text-red-400"
                                        }>
                                            {w.mean_brier_score.toFixed(4)}
                                        </span>
                                    </td>
                                    <td className="px-4 py-2.5 text-right tabular-nums font-mono text-zinc-500">
                                        {w.n.toLocaleString()}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
                <div className="px-4 py-3 border-t border-zinc-800 text-xs text-zinc-600">
                    Brier score: 0 = perfect, 0.25 = random, 1 = perfectly wrong. Cached 5 min.
                </div>
            </div>
        </section>
    );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default async function QualityPage() {
    const [data, extractionHealth, resolutionStats] = await Promise.all([
        getQualityData(),
        getExtractionHealth(),
        getResolutionStats(),
    ]);

    const totalUtterances = data.dailyTrend.reduce(
        (s, d) => s + d.utterances,
        0
    );
    const latestTrend = data.dailyTrend[data.dailyTrend.length - 1];
    const latestScore = latestTrend?.moving_avg_7d ?? 0;
    const allGatesPass =
        data.waitlistGates.length > 0 &&
        data.waitlistGates.every((g) => g.pass);

    return (
        <div className="bg-black text-white min-h-[100dvh]">
            {/* Header */}
            <section className="border-b border-zinc-900 px-6 py-12">
                <div className="max-w-5xl mx-auto space-y-4">
                    <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-emerald-500/30 bg-emerald-500/10 text-emerald-400 text-xs font-mono font-medium uppercase tracking-widest">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                        Public Dashboard
                    </div>
                    <h1 className="text-3xl sm:text-4xl font-black tracking-tight">
                        Extraction Quality
                    </h1>
                    <p className="text-zinc-400 max-w-2xl leading-relaxed">
                        How good is our data? This page tracks whether the
                        extraction pipeline produces claims that are specific,
                        testable, and attributable — and shows the three
                        criteria that gate waitlist removal.
                    </p>
                    {data.generatedAt && (
                        <p className="text-xs text-zinc-600 font-mono">
                            Updated{" "}
                            {new Date(data.generatedAt).toLocaleString(
                                "en-US",
                                {
                                    month: "short",
                                    day: "numeric",
                                    hour: "2-digit",
                                    minute: "2-digit",
                                    timeZoneName: "short",
                                }
                            )}
                        </p>
                    )}
                </div>
            </section>

            <div className="max-w-5xl mx-auto px-6 py-10 space-y-14">
                {/* Waitlist removal gates */}
                <section>
                    <SectionHeader
                        icon={Shield}
                        title="Waitlist Removal Gates"
                        subtitle="All three must be green before the waitlist is removed"
                    />
                    {allGatesPass ? (
                        <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-4 mb-5 flex items-center gap-3">
                            <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0" />
                            <p className="text-sm font-semibold text-emerald-300">
                                All gates passing — waitlist removal is
                                authorized.
                            </p>
                        </div>
                    ) : (
                        <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 mb-5 flex items-center gap-3">
                            <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0" />
                            <p className="text-sm text-amber-300">
                                <span className="font-semibold">
                                    {data.waitlistGates.filter(
                                        (g) => !g.pass
                                    ).length}{" "}
                                    of {data.waitlistGates.length} gates
                                    failing.
                                </span>{" "}
                                Waitlist stays until all pass.
                            </p>
                        </div>
                    )}
                    <div className="grid gap-4 sm:grid-cols-3">
                        {data.waitlistGates.map((gate) => (
                            <GateCard key={gate.id} gate={gate} />
                        ))}
                    </div>
                </section>

                {/* Summary stats */}
                <section>
                    <SectionHeader
                        icon={Activity}
                        title="At a Glance"
                        subtitle="Last 90 days"
                    />
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                        <StatTile
                            label="Utterances"
                            value={
                                totalUtterances >= 1000
                                    ? `${(totalUtterances / 1000).toFixed(1)}K`
                                    : String(totalUtterances)
                            }
                            sub="extracted last 90 days"
                        />
                        <StatTile
                            label="Testability (7d avg)"
                            value={`${(latestScore * 100).toFixed(1)}%`}
                            sub="moving average"
                            ok={latestScore >= 0.65}
                        />
                        <StatTile
                            label="Null Metadata"
                            value={`${(data.dataQuality.null_metadata_pct * 100).toFixed(1)}%`}
                            sub="missing speaker/domain/source"
                            ok={data.dataQuality.null_metadata_pct <= 0.01}
                        />
                        <StatTile
                            label="0-Output Runs (7d)"
                            value={String(
                                data.dataQuality.zero_output_runs_7d
                            )}
                            sub="production failures"
                            ok={data.dataQuality.zero_output_runs_7d === 0}
                        />
                    </div>
                </section>

                {!data.hasData && (
                    <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-10 text-center space-y-3">
                        <Database className="w-8 h-8 text-zinc-600 mx-auto" />
                        <p className="text-zinc-400 font-medium">
                            No extraction data yet
                        </p>
                        <p className="text-sm text-zinc-600">
                            Data will appear here once the pipeline has run.
                            Check back soon.
                        </p>
                    </div>
                )}

                {/* Panel 1 — Extraction Health (from FastAPI backend) */}
                {extractionHealth && (
                    <ExtractionHealthPanel data={extractionHealth} />
                )}

                {/* Panel 2 — Resolution Rate (from FastAPI backend) */}
                {resolutionStats && (
                    <ResolutionRatePanel data={resolutionStats} />
                )}

                {/* Panel 3 — Brier Score Trend (from FastAPI backend) */}
                {resolutionStats && (
                    <BrierTrendPanel data={resolutionStats} />
                )}

                {/* Footer note */}
                <p className="text-xs text-zinc-700 border-t border-zinc-900 pt-6">
                    Metrics computed from{" "}
                    <code className="font-mono">
                        silver_v2_claims.raw_utterance
                    </code>{" "}
                    and{" "}
                    <code className="font-mono">
                        gold_layer.prediction_ledger
                    </code>
                    . Page cached for 1 hour. Admin drill-down at{" "}
                    <a
                        href="/admin/quality/runs"
                        className="text-zinc-500 hover:text-zinc-400 underline"
                    >
                        /admin/quality/runs
                    </a>
                    .
                </p>
            </div>
        </div>
    );
}
