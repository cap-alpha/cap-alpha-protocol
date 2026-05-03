"use client";

import {
    LineChart,
    Line,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    ResponsiveContainer,
    BarChart,
    Bar,
    Cell,
    Legend,
} from "recharts";
import type { DailyTrendRow, PunditStatRow } from "@/app/api/quality/route";

// ── Testability Score Trend ───────────────────────────────────────────────────

export function TestabilityTrendChart({
    data,
}: {
    data: DailyTrendRow[];
}) {
    const formatted = data.map((d) => ({
        date: d.date.slice(5), // MM-DD
        score: +(d.mean_testability_score * 100).toFixed(1),
        avg7d: +(d.moving_avg_7d * 100).toFixed(1),
    }));

    return (
        <div className="space-y-2">
            <p className="text-xs text-zinc-500 leading-relaxed">
                Daily mean testability score (grey) with 7-day moving average
                (green). Higher is better — scores above 65 indicate claims are
                specific enough to verify.
            </p>
            <ResponsiveContainer width="100%" height={220}>
                <LineChart
                    data={formatted}
                    margin={{ top: 4, right: 8, bottom: 0, left: -16 }}
                >
                    <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                    <XAxis
                        dataKey="date"
                        tick={{ fontSize: 10, fill: "#71717a" }}
                        interval="preserveStartEnd"
                    />
                    <YAxis
                        domain={[0, 100]}
                        tick={{ fontSize: 10, fill: "#71717a" }}
                        unit="%"
                    />
                    <Tooltip
                        contentStyle={{
                            background: "#18181b",
                            border: "1px solid #3f3f46",
                            borderRadius: 8,
                            fontSize: 12,
                        }}
                        formatter={(v: number, name: string) => [
                            `${v}%`,
                            name === "avg7d" ? "7-day avg" : "Daily",
                        ]}
                    />
                    <Line
                        type="monotone"
                        dataKey="score"
                        stroke="#52525b"
                        dot={false}
                        strokeWidth={1}
                    />
                    <Line
                        type="monotone"
                        dataKey="avg7d"
                        stroke="#10b981"
                        dot={false}
                        strokeWidth={2}
                    />
                </LineChart>
            </ResponsiveContainer>
        </div>
    );
}

// ── Claim Promotion Rate Trend ────────────────────────────────────────────────

export function ClaimPromotionChart({ data }: { data: DailyTrendRow[] }) {
    const formatted = data.map((d) => ({
        date: d.date.slice(5),
        rate: +(d.claim_promotion_rate * 100).toFixed(1),
        utterances: d.utterances,
    }));

    return (
        <div className="space-y-2">
            <p className="text-xs text-zinc-500 leading-relaxed">
                Percentage of extracted utterances that passed the testability
                threshold and were promoted to the prediction ledger. A rising
                trend means the extraction quality is improving.
            </p>
            <ResponsiveContainer width="100%" height={220}>
                <LineChart
                    data={formatted}
                    margin={{ top: 4, right: 8, bottom: 0, left: -16 }}
                >
                    <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                    <XAxis
                        dataKey="date"
                        tick={{ fontSize: 10, fill: "#71717a" }}
                        interval="preserveStartEnd"
                    />
                    <YAxis
                        domain={[0, 100]}
                        tick={{ fontSize: 10, fill: "#71717a" }}
                        unit="%"
                    />
                    <Tooltip
                        contentStyle={{
                            background: "#18181b",
                            border: "1px solid #3f3f46",
                            borderRadius: 8,
                            fontSize: 12,
                        }}
                        formatter={(v: number) => [`${v}%`, "Claim rate"]}
                    />
                    <Line
                        type="monotone"
                        dataKey="rate"
                        stroke="#3b82f6"
                        dot={false}
                        strokeWidth={2}
                    />
                </LineChart>
            </ResponsiveContainer>
        </div>
    );
}

// ── Resolution Accuracy (per-pundit) ─────────────────────────────────────────

export function ResolutionAccuracyChart({
    data,
}: {
    data: PunditStatRow[];
}) {
    const formatted = data
        .filter((d) => d.resolved > 0)
        .slice(0, 15)
        .map((d) => ({
            name: d.speaker_entity_id.replace(/-/g, " ").slice(0, 18),
            rate: +(
                (d.resolved > 0 ? d.correct / d.resolved : 0) * 100
            ).toFixed(1),
            resolved: d.resolved,
        }));

    return (
        <div className="space-y-2">
            <p className="text-xs text-zinc-500 leading-relaxed">
                Accuracy rate for pundits with at least one resolved prediction.
                Green bars = above 50% accuracy. This reflects real signal
                quality, not volume.
            </p>
            <ResponsiveContainer width="100%" height={220}>
                <BarChart
                    data={formatted}
                    margin={{ top: 4, right: 8, bottom: 40, left: -16 }}
                >
                    <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                    <XAxis
                        dataKey="name"
                        tick={{ fontSize: 9, fill: "#71717a" }}
                        angle={-30}
                        textAnchor="end"
                        interval={0}
                    />
                    <YAxis
                        domain={[0, 100]}
                        tick={{ fontSize: 10, fill: "#71717a" }}
                        unit="%"
                    />
                    <Tooltip
                        contentStyle={{
                            background: "#18181b",
                            border: "1px solid #3f3f46",
                            borderRadius: 8,
                            fontSize: 12,
                        }}
                        formatter={(v: number) => [
                            `${v}%`,
                            "Accuracy",
                        ]}
                    />
                    <Bar dataKey="rate" radius={[3, 3, 0, 0]}>
                        {formatted.map((entry, i) => (
                            <Cell
                                key={i}
                                fill={entry.rate >= 50 ? "#10b981" : "#f59e0b"}
                            />
                        ))}
                    </Bar>
                </BarChart>
            </ResponsiveContainer>
        </div>
    );
}

// ── Per-pundit volume table ───────────────────────────────────────────────────

export function PunditStatsTable({ data }: { data: PunditStatRow[] }) {
    return (
        <div className="overflow-x-auto">
            <table className="w-full text-xs text-left">
                <thead>
                    <tr className="border-b border-zinc-800 text-zinc-500 font-mono uppercase tracking-wider">
                        <th className="pb-2 pr-4">Pundit</th>
                        <th className="pb-2 pr-4 text-right">Utterances</th>
                        <th className="pb-2 pr-4 text-right">Claims</th>
                        <th className="pb-2 pr-4 text-right">Claim Rate</th>
                        <th className="pb-2 pr-4 text-right">Testability</th>
                        <th className="pb-2 text-right">Resolution %</th>
                    </tr>
                </thead>
                <tbody className="divide-y divide-zinc-900">
                    {data.map((row) => (
                        <tr
                            key={row.speaker_entity_id}
                            className="text-zinc-300 hover:bg-zinc-900/40"
                        >
                            <td className="py-2 pr-4 font-medium text-zinc-200 max-w-[140px] truncate">
                                {row.speaker_entity_id.replace(/-/g, " ")}
                            </td>
                            <td className="py-2 pr-4 text-right tabular-nums">
                                {row.utterances.toLocaleString()}
                            </td>
                            <td className="py-2 pr-4 text-right tabular-nums">
                                {row.claims_promoted.toLocaleString()}
                            </td>
                            <td className="py-2 pr-4 text-right tabular-nums">
                                {(row.claim_rate * 100).toFixed(1)}%
                            </td>
                            <td className="py-2 pr-4 text-right tabular-nums">
                                <span
                                    className={
                                        row.mean_testability_score >= 0.65
                                            ? "text-emerald-400"
                                            : "text-amber-400"
                                    }
                                >
                                    {(
                                        row.mean_testability_score * 100
                                    ).toFixed(1)}
                                    %
                                </span>
                            </td>
                            <td className="py-2 text-right tabular-nums">
                                {row.resolved > 0
                                    ? `${(row.resolution_rate * 100).toFixed(0)}%`
                                    : "—"}
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}
