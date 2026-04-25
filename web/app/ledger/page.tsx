"use client";

import { useEffect, useState, useMemo } from "react";
import Link from "next/link";
import {
    Activity,
    ArrowUpDown,
    CheckCircle2,
    XCircle,
    Clock,
    ChevronDown,
    ChevronUp,
    ShieldCheck,
    TrendingUp,
    BarChart3,
    Hash,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface PunditStat {
    pundit_name: string;
    pundit_id: string;
    sport: string;
    total_predictions: number;
    resolved_predictions: number;
    correct_predictions: number;
    incorrect_predictions: number;
    avg_brier_score: number | null;
    avg_weighted_score: number | null;
    accuracy_rate: number | null;
    game_outcome_count: number;
    player_performance_count: number;
    trade_count: number;
    injury_count: number;
    contract_count: number;
    draft_pick_count: number;
    first_seen: string | null;
    last_seen: string | null;
}

type SortKey = "accuracy_rate" | "avg_brier_score" | "total_predictions" | "resolved_predictions";
type SortDir = "asc" | "desc";

function BrierBadge({ score }: { score: number | null }) {
    if (score === null) return <span className="text-xs text-zinc-600 font-mono">—</span>;
    // Brier score: 0 = perfect, 0.25 = coin flip, 1 = worst
    const color = score <= 0.15 ? "text-emerald-400" : score <= 0.22 ? "text-yellow-400" : "text-red-400";
    return <span className={cn("text-sm font-mono font-semibold tabular-nums", color)}>{score.toFixed(3)}</span>;
}

function AccuracyBar({ rate }: { rate: number | null }) {
    if (rate === null) return <span className="text-xs text-zinc-600 font-mono">—</span>;
    const pct = Math.round(rate * 100);
    const color = pct >= 60 ? "bg-emerald-500" : pct >= 45 ? "bg-yellow-500" : "bg-red-500";
    const textColor = pct >= 60 ? "text-emerald-400" : pct >= 45 ? "text-yellow-400" : "text-red-400";
    return (
        <div className="flex items-center gap-2 min-w-[100px]">
            <div className="flex-1 h-1.5 rounded-full bg-zinc-800 overflow-hidden">
                <div className={cn("h-full rounded-full", color)} style={{ width: `${pct}%` }} />
            </div>
            <span className={cn("text-xs font-mono font-semibold tabular-nums w-8 text-right", textColor)}>
                {pct}%
            </span>
        </div>
    );
}

function CategoryPills({ p }: { p: PunditStat }) {
    const cats = [
        { label: "Game", count: p.game_outcome_count },
        { label: "Player", count: p.player_performance_count },
        { label: "Trade", count: p.trade_count },
        { label: "Injury", count: p.injury_count },
        { label: "Contract", count: p.contract_count },
        { label: "Draft", count: p.draft_pick_count },
    ].filter((c) => c.count > 0).slice(0, 3);

    return (
        <div className="flex gap-1 flex-wrap">
            {cats.map((c) => (
                <span
                    key={c.label}
                    className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-zinc-800 text-zinc-500"
                >
                    {c.label} {c.count}
                </span>
            ))}
        </div>
    );
}

function SortButton({
    label,
    sortKey,
    current,
    dir,
    onSort,
}: {
    label: string;
    sortKey: SortKey;
    current: SortKey;
    dir: SortDir;
    onSort: (k: SortKey) => void;
}) {
    const active = current === sortKey;
    return (
        <button
            onClick={() => onSort(sortKey)}
            className={cn(
                "flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-mono font-medium transition-colors",
                active
                    ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                    : "bg-zinc-900 text-zinc-500 border border-zinc-800 hover:text-zinc-300"
            )}
        >
            {label}
            {active ? (
                dir === "desc" ? <ChevronDown className="w-3 h-3" /> : <ChevronUp className="w-3 h-3" />
            ) : (
                <ArrowUpDown className="w-3 h-3 opacity-40" />
            )}
        </button>
    );
}

export default function LedgerPage() {
    const [pundits, setPundits] = useState<PunditStat[]>([]);
    const [loading, setLoading] = useState(true);
    const [sortKey, setSortKey] = useState<SortKey>("avg_brier_score");
    const [sortDir, setSortDir] = useState<SortDir>("asc");
    const [expanded, setExpanded] = useState<string | null>(null);

    useEffect(() => {
        fetch("/api/ledger/pundits")
            .then((r) => r.json())
            .then((data) => setPundits(data.pundits || []))
            .finally(() => setLoading(false));
    }, []);

    const sorted = useMemo(() => {
        return [...pundits].sort((a, b) => {
            const av = a[sortKey] ?? (sortDir === "asc" ? Infinity : -Infinity);
            const bv = b[sortKey] ?? (sortDir === "asc" ? Infinity : -Infinity);
            return sortDir === "asc" ? (av as number) - (bv as number) : (bv as number) - (av as number);
        });
    }, [pundits, sortKey, sortDir]);

    const stats = useMemo(() => ({
        total: pundits.length,
        predictions: pundits.reduce((s, p) => s + p.total_predictions, 0),
        resolved: pundits.reduce((s, p) => s + p.resolved_predictions, 0),
        correct: pundits.reduce((s, p) => s + p.correct_predictions, 0),
    }), [pundits]);

    function handleSort(key: SortKey) {
        if (key === sortKey) {
            setSortDir((d) => (d === "asc" ? "desc" : "asc"));
        } else {
            setSortKey(key);
            // Brier score: lower is better → default asc
            // Everything else: higher is better → default desc
            setSortDir(key === "avg_brier_score" ? "asc" : "desc");
        }
    }

    return (
        <div className="bg-black text-white min-h-screen">
            <div className="max-w-6xl mx-auto px-4 sm:px-6 py-12 space-y-10">

                {/* Header */}
                <div className="space-y-4">
                    <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-emerald-500/30 bg-emerald-500/10 text-emerald-400 text-xs font-mono font-medium uppercase tracking-widest">
                        <ShieldCheck className="w-3.5 h-3.5" />
                        Cryptographically Verified
                    </div>
                    <h1 className="text-4xl sm:text-5xl font-black tracking-tight">
                        Pundit <span className="text-emerald-400">Accountability</span> Ledger
                    </h1>
                    <p className="text-zinc-400 max-w-2xl leading-relaxed">
                        Every tracked sports analyst, ranked by prediction accuracy and Brier Score.
                        Lower Brier = sharper. No revisionism. No excuses.
                    </p>
                </div>

                {/* Stats bar */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                    {[
                        { icon: <Hash className="w-4 h-4" />, label: "Pundits Tracked", value: stats.total },
                        { icon: <Activity className="w-4 h-4" />, label: "Total Predictions", value: stats.predictions.toLocaleString() },
                        { icon: <BarChart3 className="w-4 h-4" />, label: "Resolved", value: stats.resolved.toLocaleString() },
                        {
                            icon: <TrendingUp className="w-4 h-4" />,
                            label: "Overall Accuracy",
                            value: stats.resolved > 0
                                ? `${Math.round((stats.correct / stats.resolved) * 100)}%`
                                : "—",
                        },
                    ].map((s) => (
                        <div key={s.label} className="rounded-xl border border-zinc-800 bg-zinc-900/50 px-4 py-3 space-y-1">
                            <div className="flex items-center gap-1.5 text-zinc-600 text-xs font-mono">
                                {s.icon}
                                {s.label}
                            </div>
                            <div className="text-2xl font-black tabular-nums text-white">{s.value}</div>
                        </div>
                    ))}
                </div>

                {/* Sort controls */}
                <div className="flex flex-wrap items-center gap-2">
                    <span className="text-xs text-zinc-600 font-mono mr-1">Sort by:</span>
                    <SortButton label="Brier Score" sortKey="avg_brier_score" current={sortKey} dir={sortDir} onSort={handleSort} />
                    <SortButton label="Accuracy" sortKey="accuracy_rate" current={sortKey} dir={sortDir} onSort={handleSort} />
                    <SortButton label="Predictions" sortKey="total_predictions" current={sortKey} dir={sortDir} onSort={handleSort} />
                    <SortButton label="Resolved" sortKey="resolved_predictions" current={sortKey} dir={sortDir} onSort={handleSort} />
                </div>

                {/* Leaderboard */}
                {loading ? (
                    <div className="flex items-center justify-center py-24 text-zinc-600">
                        <Activity className="w-5 h-5 animate-pulse mr-2" />
                        <span className="font-mono text-sm">Loading ledger…</span>
                    </div>
                ) : sorted.length === 0 ? (
                    <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 py-16 text-center text-zinc-600 font-mono text-sm">
                        No pundit data yet — pipeline is populating.
                    </div>
                ) : (
                    <div className="space-y-2">
                        {sorted.map((p, idx) => {
                            const isExpanded = expanded === p.pundit_id;
                            const pending = p.total_predictions - p.resolved_predictions;
                            return (
                                <div
                                    key={p.pundit_id}
                                    className="rounded-xl border border-zinc-800 bg-zinc-900/50 overflow-hidden"
                                >
                                    {/* Main row */}
                                    <button
                                        className="w-full text-left px-4 py-3.5 flex items-center gap-3 sm:gap-4 hover:bg-zinc-900 transition-colors"
                                        onClick={() => setExpanded(isExpanded ? null : p.pundit_id)}
                                    >
                                        {/* Rank */}
                                        <span className={cn(
                                            "font-mono text-base font-black w-7 shrink-0 tabular-nums",
                                            idx === 0 ? "text-yellow-400"
                                            : idx === 1 ? "text-zinc-300"
                                            : idx === 2 ? "text-orange-400"
                                            : "text-zinc-600"
                                        )}>
                                            {idx + 1}
                                        </span>

                                        {/* Name + categories */}
                                        <div className="flex-1 min-w-0 space-y-1">
                                            <div className="font-semibold text-white truncate">{p.pundit_name}</div>
                                            <div className="hidden sm:block">
                                                <CategoryPills p={p} />
                                            </div>
                                        </div>

                                        {/* Accuracy */}
                                        <div className="hidden sm:flex flex-col items-end gap-0.5 shrink-0 w-28">
                                            <span className="text-[10px] text-zinc-600 font-mono">accuracy</span>
                                            <AccuracyBar rate={p.accuracy_rate} />
                                        </div>

                                        {/* Brier score */}
                                        <div className="flex flex-col items-end gap-0.5 shrink-0 w-16">
                                            <span className="text-[10px] text-zinc-600 font-mono">brier</span>
                                            <BrierBadge score={p.avg_brier_score} />
                                        </div>

                                        {/* Correct / Incorrect */}
                                        <div className="hidden md:flex items-center gap-2 shrink-0 text-xs font-mono">
                                            <span className="flex items-center gap-1 text-emerald-400">
                                                <CheckCircle2 className="w-3 h-3" />
                                                {p.correct_predictions}
                                            </span>
                                            <span className="text-zinc-700">/</span>
                                            <span className="flex items-center gap-1 text-red-400">
                                                <XCircle className="w-3 h-3" />
                                                {p.incorrect_predictions}
                                            </span>
                                        </div>

                                        {/* Total */}
                                        <span className="text-xs font-mono text-zinc-500 shrink-0 w-16 text-right">
                                            {p.total_predictions} picks
                                        </span>

                                        {/* Expand chevron */}
                                        {isExpanded
                                            ? <ChevronUp className="w-4 h-4 text-zinc-600 shrink-0" />
                                            : <ChevronDown className="w-4 h-4 text-zinc-600 shrink-0" />
                                        }
                                    </button>

                                    {/* Expanded detail */}
                                    {isExpanded && (
                                        <div className="border-t border-zinc-800 px-4 py-4 grid sm:grid-cols-2 gap-4">
                                            {/* Stats */}
                                            <div className="space-y-3">
                                                <h4 className="text-xs font-mono text-zinc-500 uppercase tracking-widest">Prediction Stats</h4>
                                                <div className="grid grid-cols-2 gap-2">
                                                    {[
                                                        { label: "Total", value: p.total_predictions },
                                                        { label: "Resolved", value: p.resolved_predictions },
                                                        { label: "Correct", value: p.correct_predictions },
                                                        { label: "Incorrect", value: p.incorrect_predictions },
                                                        { label: "Pending", value: pending },
                                                        {
                                                            label: "Weighted Score",
                                                            value: p.avg_weighted_score !== null
                                                                ? p.avg_weighted_score.toFixed(4)
                                                                : "—"
                                                        },
                                                    ].map((s) => (
                                                        <div key={s.label} className="rounded-lg bg-zinc-800/50 px-3 py-2">
                                                            <div className="text-[10px] font-mono text-zinc-600">{s.label}</div>
                                                            <div className="text-sm font-mono font-semibold text-white tabular-nums">{s.value}</div>
                                                        </div>
                                                    ))}
                                                </div>
                                            </div>

                                            {/* Category breakdown */}
                                            <div className="space-y-3">
                                                <h4 className="text-xs font-mono text-zinc-500 uppercase tracking-widest">By Category</h4>
                                                <div className="space-y-2">
                                                    {[
                                                        { label: "Game Outcome", count: p.game_outcome_count },
                                                        { label: "Player Performance", count: p.player_performance_count },
                                                        { label: "Trade", count: p.trade_count },
                                                        { label: "Injury", count: p.injury_count },
                                                        { label: "Contract", count: p.contract_count },
                                                        { label: "Draft Pick", count: p.draft_pick_count },
                                                    ].filter((c) => c.count > 0).map((c) => (
                                                        <div key={c.label} className="flex items-center gap-2">
                                                            <span className="text-xs font-mono text-zinc-400 w-36 shrink-0">{c.label}</span>
                                                            <div className="flex-1 h-1 rounded-full bg-zinc-800">
                                                                <div
                                                                    className="h-full rounded-full bg-emerald-500/60"
                                                                    style={{
                                                                        width: `${Math.round((c.count / p.total_predictions) * 100)}%`
                                                                    }}
                                                                />
                                                            </div>
                                                            <span className="text-xs font-mono text-zinc-500 w-6 text-right">{c.count}</span>
                                                        </div>
                                                    ))}
                                                </div>

                                                {/* Active period */}
                                                {p.first_seen && (
                                                    <div className="flex items-center gap-1.5 text-[10px] font-mono text-zinc-600 pt-1">
                                                        <Clock className="w-3 h-3" />
                                                        Tracked {new Date(p.first_seen).getFullYear()}–{new Date(p.last_seen ?? p.first_seen).getFullYear()}
                                                    </div>
                                                )}
                                            </div>
                                        </div>
                                    )}
                                </div>
                            );
                        })}
                    </div>
                )}

                {/* Footer note */}
                <p className="text-xs text-zinc-700 font-mono text-center pt-4">
                    Brier Score: 0.00 = perfect · 0.25 = random · 1.00 = consistently wrong ·{" "}
                    <Link href="/methodology" className="text-zinc-500 hover:text-zinc-400 underline underline-offset-2">
                        Methodology
                    </Link>
                </p>
            </div>
        </div>
    );
}
