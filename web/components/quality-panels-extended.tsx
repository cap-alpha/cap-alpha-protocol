"use client";

/**
 * Five new quality panels for the launch milestone dashboard.
 *
 * All panels are client components (recharts requires browser) that accept
 * pre-fetched data as props — the server component in page.tsx fetches and
 * passes the data. Each panel handles the empty/no-data case gracefully.
 */

import { Database } from "lucide-react";
import {
    BarChart,
    Bar,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    ResponsiveContainer,
    Cell,
    PieChart,
    Pie,
} from "recharts";
import type {
    SilverCoverage,
    ProvenanceCompleteness,
    TestabilityBucket,
    ProviderMixItem,
    AccuracyByCategoryItem,
} from "@/app/api/quality/extended/route";

// ---------------------------------------------------------------------------
// Shared primitives
// ---------------------------------------------------------------------------

function NoData({ label }: { label: string }) {
    return (
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-10 text-center space-y-3">
            <Database className="w-8 h-8 text-zinc-600 mx-auto" />
            <p className="text-zinc-400 font-medium">{label}</p>
            <p className="text-sm text-zinc-600">
                Data will appear here once the pipeline has run.
            </p>
        </div>
    );
}

function ProgressBar({
    value,
    max,
    color = "bg-emerald-500",
}: {
    value: number;
    max: number;
    color?: string;
}) {
    const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0;
    return (
        <div className="w-full h-2 rounded-full bg-zinc-800 overflow-hidden">
            <div
                className={`h-full rounded-full transition-all ${color}`}
                style={{ width: `${pct}%` }}
            />
        </div>
    );
}

// ---------------------------------------------------------------------------
// Panel 1 — Silver Coverage
// ---------------------------------------------------------------------------

export function SilverCoveragePanel({ data }: { data: SilverCoverage }) {
    const { total_utterances, promoted_utterances, coverage_pct } = data;

    return (
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-6 space-y-4">
            <div className="space-y-1">
                <p className="text-xs text-zinc-500 uppercase tracking-widest font-mono">
                    Silver Coverage
                </p>
                <p className="text-3xl font-black tabular-nums text-white">
                    {coverage_pct.toFixed(1)}%
                </p>
                <p className="text-sm text-zinc-400">
                    {promoted_utterances.toLocaleString()} /{" "}
                    {total_utterances.toLocaleString()} utterances promoted to
                    structured claims
                </p>
            </div>
            <ProgressBar
                value={promoted_utterances}
                max={total_utterances}
                color={coverage_pct >= 60 ? "bg-emerald-500" : "bg-amber-500"}
            />
            <p className="text-xs text-zinc-600">
                From{" "}
                <code className="font-mono">silver_v2_claims.raw_utterance</code>{" "}
                &#8594;{" "}
                <code className="font-mono">silver_v2_claims.claim</code>. A
                rising numerator means backfill is working.
            </p>
        </div>
    );
}

// ---------------------------------------------------------------------------
// Panel 2 — Provenance Completeness
// ---------------------------------------------------------------------------

export function ProvenanceCompletenessPanel({
    data,
}: {
    data: ProvenanceCompleteness;
}) {
    const { total_ledger, with_provider, completeness_pct } = data;

    return (
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-6 space-y-4">
            <div className="space-y-1">
                <p className="text-xs text-zinc-500 uppercase tracking-widest font-mono">
                    Provenance Completeness
                </p>
                <p
                    className={`text-3xl font-black tabular-nums ${
                        completeness_pct >= 99
                            ? "text-emerald-400"
                            : completeness_pct >= 50
                            ? "text-amber-400"
                            : "text-white"
                    }`}
                >
                    {completeness_pct.toFixed(1)}%
                </p>
                <p className="text-sm text-zinc-400">
                    {with_provider.toLocaleString()} /{" "}
                    {total_ledger.toLocaleString()} ledger rows with{" "}
                    <code className="font-mono text-xs">llm_provider</code>{" "}
                    filled
                </p>
            </div>
            <ProgressBar
                value={with_provider}
                max={total_ledger}
                color={
                    completeness_pct >= 99
                        ? "bg-emerald-500"
                        : completeness_pct >= 50
                        ? "bg-amber-500"
                        : "bg-red-500"
                }
            />
            <p className="text-xs text-zinc-600">
                From{" "}
                <code className="font-mono">gold_layer.prediction_ledger</code>.
                Reaches 100% after the provenance backfill lands.
            </p>
        </div>
    );
}

// ---------------------------------------------------------------------------
// Panel 3 — Testability Distribution
// ---------------------------------------------------------------------------

export function TestabilityDistributionPanel({
    data,
}: {
    data: TestabilityBucket[];
}) {
    if (data.length === 0 || data.every((b) => b.count === 0)) {
        return <NoData label="No testability distribution data yet" />;
    }

    const chartData = data.map((b) => ({
        bucket: b.bucket,
        count: b.count,
    }));

    return (
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-6 space-y-4">
            <div className="space-y-1">
                <p className="text-xs text-zinc-500 uppercase tracking-widest font-mono">
                    Testability Distribution
                </p>
                <p className="text-sm text-zinc-400">
                    Utterances by score bucket &#8212; higher buckets are
                    testable claims
                </p>
            </div>
            <ResponsiveContainer width="100%" height={180}>
                <BarChart
                    data={chartData}
                    margin={{ top: 4, right: 4, bottom: 0, left: -20 }}
                >
                    <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                    <XAxis
                        dataKey="bucket"
                        tick={{ fontSize: 10, fill: "#71717a" }}
                    />
                    <YAxis tick={{ fontSize: 10, fill: "#71717a" }} />
                    <Tooltip
                        contentStyle={{
                            background: "#18181b",
                            border: "1px solid #3f3f46",
                            borderRadius: 8,
                            fontSize: 12,
                        }}
                        formatter={(v: unknown) => [
                            (v as number).toLocaleString(),
                            "utterances",
                        ]}
                    />
                    <Bar dataKey="count" radius={[3, 3, 0, 0]}>
                        {chartData.map((entry, i) => {
                            const hue =
                                i <= 1
                                    ? "#ef4444"
                                    : i === 2
                                    ? "#f59e0b"
                                    : "#10b981";
                            return <Cell key={`cell-${i}`} fill={hue} />;
                        })}
                    </Bar>
                </BarChart>
            </ResponsiveContainer>
            <p className="text-xs text-zinc-600">
                &#8805;0.6 = testable assertion; &lt;0.4 = commentary or hedge.
                Green buckets are signal; red is noise.
            </p>
        </div>
    );
}

// ---------------------------------------------------------------------------
// Panel 4 — LLM Provider Mix
// ---------------------------------------------------------------------------

const PROVIDER_COLORS: Record<string, string> = {
    ollama: "#3b82f6",
    gemini: "#8b5cf6",
    manual: "#f59e0b",
    unset: "#52525b",
    unknown: "#52525b",
};

function providerColor(provider: string): string {
    return PROVIDER_COLORS[provider.toLowerCase()] ?? "#71717a";
}

export function ProviderMixPanel({ data }: { data: ProviderMixItem[] }) {
    if (data.length === 0) {
        return <NoData label="No provider mix data yet" />;
    }

    const chartData = data.map((item) => ({
        name: item.provider,
        value: item.count,
        pct: item.pct,
        fill: providerColor(item.provider),
    }));

    return (
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-6 space-y-4">
            <div className="space-y-1">
                <p className="text-xs text-zinc-500 uppercase tracking-widest font-mono">
                    LLM Provider Mix
                </p>
                <p className="text-sm text-zinc-400">
                    Ledger rows by extraction provider
                </p>
            </div>
            <div className="flex flex-col sm:flex-row items-center gap-4">
                <ResponsiveContainer width={160} height={160}>
                    <PieChart>
                        <Pie
                            data={chartData}
                            cx="50%"
                            cy="50%"
                            innerRadius={44}
                            outerRadius={72}
                            dataKey="value"
                            stroke="none"
                        >
                            {chartData.map((entry, i) => (
                                <Cell key={`pie-${i}`} fill={entry.fill} />
                            ))}
                        </Pie>
                        <Tooltip
                            contentStyle={{
                                background: "#18181b",
                                border: "1px solid #3f3f46",
                                borderRadius: 8,
                                fontSize: 12,
                            }}
                            formatter={(
                                v: unknown,
                                _name: unknown,
                                p: { payload?: { pct?: number } }
                            ) => [
                                `${(v as number).toLocaleString()} (${p?.payload?.pct ?? 0}%)`,
                                "rows",
                            ]}
                        />
                    </PieChart>
                </ResponsiveContainer>
                <div className="flex-1 space-y-2 min-w-0">
                    {chartData.map((item) => (
                        <div
                            key={item.name}
                            className="flex items-center justify-between gap-2 text-xs"
                        >
                            <div className="flex items-center gap-2 min-w-0">
                                <span
                                    className="w-2.5 h-2.5 rounded-full shrink-0"
                                    style={{ background: item.fill }}
                                />
                                <span className="font-mono text-zinc-300 truncate capitalize">
                                    {item.name}
                                </span>
                            </div>
                            <span className="font-mono text-zinc-500 tabular-nums shrink-0">
                                {item.value.toLocaleString()} ({item.pct}%)
                            </span>
                        </div>
                    ))}
                </div>
            </div>
            <p className="text-xs text-zinc-600">
                &ldquo;unset&rdquo; rows will drop to zero after the provenance
                backfill lands.
            </p>
        </div>
    );
}

// ---------------------------------------------------------------------------
// Panel 5 — Resolution Accuracy by Claim Category
// ---------------------------------------------------------------------------

export function AccuracyByCategoryPanel({
    data,
}: {
    data: AccuracyByCategoryItem[];
}) {
    if (data.length === 0) {
        return <NoData label="No resolution accuracy data yet" />;
    }

    const chartData = data.map((item) => ({
        category: item.category.replace(/_/g, " "),
        accuracy: item.accuracy_pct ?? 0,
        total: item.total,
        correct: item.correct,
    }));

    return (
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-6 space-y-4">
            <div className="space-y-1">
                <p className="text-xs text-zinc-500 uppercase tracking-widest font-mono">
                    Resolution Accuracy by Category
                </p>
                <p className="text-sm text-zinc-400">
                    % correct of resolved predictions, grouped by claim category
                </p>
            </div>
            <ResponsiveContainer width="100%" height={Math.max(160, chartData.length * 36)}>
                <BarChart
                    data={chartData}
                    layout="vertical"
                    margin={{ top: 4, right: 8, bottom: 4, left: 80 }}
                >
                    <CartesianGrid
                        strokeDasharray="3 3"
                        stroke="#27272a"
                        horizontal={false}
                    />
                    <XAxis
                        type="number"
                        domain={[0, 100]}
                        tick={{ fontSize: 10, fill: "#71717a" }}
                        unit="%"
                    />
                    <YAxis
                        type="category"
                        dataKey="category"
                        tick={{ fontSize: 10, fill: "#a1a1aa" }}
                        width={78}
                    />
                    <Tooltip
                        contentStyle={{
                            background: "#18181b",
                            border: "1px solid #3f3f46",
                            borderRadius: 8,
                            fontSize: 12,
                        }}
                        formatter={(
                            v: unknown,
                            _name: unknown,
                            p: { payload?: { correct?: number; total?: number } }
                        ) => {
                            const correct = p?.payload?.correct ?? 0;
                            const total = p?.payload?.total ?? 0;
                            return [
                                `${v as number}% (${correct}/${total})`,
                                "accuracy",
                            ];
                        }}
                    />
                    <Bar dataKey="accuracy" radius={[0, 3, 3, 0]}>
                        {chartData.map((entry, i) => (
                            <Cell
                                key={`cat-${i}`}
                                fill={
                                    entry.accuracy >= 60
                                        ? "#10b981"
                                        : entry.accuracy >= 40
                                        ? "#f59e0b"
                                        : "#ef4444"
                                }
                            />
                        ))}
                    </Bar>
                </BarChart>
            </ResponsiveContainer>
            <p className="text-xs text-zinc-600">
                From{" "}
                <code className="font-mono">
                    gold_layer.prediction_resolutions
                </code>{" "}
                joined to{" "}
                <code className="font-mono">prediction_ledger.claim_category</code>
                . Only rows with a binary resolution verdict included.
            </p>
        </div>
    );
}
