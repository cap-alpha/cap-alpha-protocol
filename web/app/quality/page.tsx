import { Metadata } from "next";
import { CheckCircle2, XCircle, AlertTriangle, Activity, BarChart3, Database, Shield } from "lucide-react";
import type { QualityResponse, WaitlistGate } from "@/app/api/quality/route";
import {
    TestabilityTrendChart,
    ClaimPromotionChart,
    ResolutionAccuracyChart,
    PunditStatsTable,
} from "@/components/quality-charts";

export const revalidate = 3600;

export const metadata: Metadata = {
    title: "Extraction Quality Dashboard | Pundit Ledger",
    description:
        "Live extraction quality metrics — testability scores, claim promotion rates, and waitlist-removal gate status.",
};

const API_BASE =
    process.env.NEXT_PUBLIC_APP_URL ||
    process.env.VERCEL_URL
        ? `https://${process.env.VERCEL_URL}`
        : "http://localhost:3000";

async function getQualityData(): Promise<QualityResponse> {
    try {
        const res = await fetch(`${API_BASE}/api/quality`, {
            next: { revalidate: 3600 },
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
            },
            waitlistGates: [],
            generatedAt: new Date().toISOString(),
            hasData: false,
        };
    }
}

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

function SectionHeader({ icon: Icon, title, subtitle }: { icon: React.ElementType; title: string; subtitle?: string }) {
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

export default async function QualityPage() {
    const data = await getQualityData();

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

                {data.hasData && (
                    <>
                        {/* Trend charts */}
                        <section>
                            <SectionHeader
                                icon={BarChart3}
                                title="Trends (90 days)"
                                subtitle="Daily extraction metrics"
                            />
                            <div className="grid gap-8 lg:grid-cols-2">
                                <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-5 space-y-3">
                                    <h3 className="text-sm font-semibold text-zinc-200">
                                        Testability Score
                                    </h3>
                                    <TestabilityTrendChart
                                        data={data.dailyTrend}
                                    />
                                </div>
                                <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-5 space-y-3">
                                    <h3 className="text-sm font-semibold text-zinc-200">
                                        Claim Promotion Rate
                                    </h3>
                                    <ClaimPromotionChart
                                        data={data.dailyTrend}
                                    />
                                </div>
                                <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-5 space-y-3 lg:col-span-2">
                                    <h3 className="text-sm font-semibold text-zinc-200">
                                        Resolution Accuracy (top pundits with
                                        resolved predictions)
                                    </h3>
                                    <ResolutionAccuracyChart
                                        data={data.punditStats}
                                    />
                                </div>
                            </div>
                        </section>

                        {/* Per-pundit table */}
                        <section>
                            <SectionHeader
                                icon={BarChart3}
                                title="Top 25 Pundits by Volume"
                                subtitle="Ranked by total utterances extracted (last 12 months)"
                            />
                            <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-5">
                                <PunditStatsTable data={data.punditStats} />
                            </div>
                        </section>
                    </>
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
