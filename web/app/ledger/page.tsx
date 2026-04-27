"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
    Shield,
    Trophy,
    CheckCircle2,
    XCircle,
    Clock,
    ArrowRight,
    Activity,
} from "lucide-react";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface PunditStat {
    pundit_name: string;
    pundit_id: string;
    sport: string;
    total_predictions: number;
    resolved_predictions: number;
    correct_predictions: number;
    incorrect_predictions: number;
    accuracy_rate: number | null;
    avg_brier_score: number | null;
    avg_weighted_score: number | null;
    game_outcome_count: number;
    player_performance_count: number;
    trade_count: number;
    draft_pick_count: number;
    first_seen: string | null;
    last_seen: string | null;
}

interface RecentPrediction {
    pundit_name: string;
    pundit_id: string;
    extracted_claim: string;
    claim_category: string;
    season_year: number | null;
    target_player_id: string | null;
    target_team: string | null;
    sport: string;
    prediction_hash_short: string;
    ingestion_timestamp: string;
    resolution_status: string | null;
    brier_score: number | null;
    weighted_score: number | null;
}

// ---------------------------------------------------------------------------
// Small helpers
// ---------------------------------------------------------------------------

function AccuracyBar({ rate }: { rate: number | null }) {
    if (rate === null)
        return <span className="text-xs text-zinc-600 font-mono tabular-nums">—</span>;
    const pct = Math.round(rate * 100);
    const color =
        pct >= 60 ? "bg-emerald-500" : pct >= 45 ? "bg-yellow-500" : "bg-red-500";
    const textColor =
        pct >= 60
            ? "text-emerald-400"
            : pct >= 45
            ? "text-yellow-400"
            : "text-red-400";
    return (
        <div className="flex items-center gap-2">
            <div className="w-16 h-1.5 rounded-full bg-zinc-800 overflow-hidden">
                <div
                    className={cn("h-full rounded-full transition-all", color)}
                    style={{ width: `${pct}%` }}
                />
            </div>
            <span className={cn("text-xs font-mono font-semibold tabular-nums", textColor)}>
                {pct}%
            </span>
        </div>
    );
}

function BrierBadge({ score }: { score: number | null }) {
    if (score === null)
        return <span className="text-xs text-zinc-600 font-mono">—</span>;
    const color =
        score <= 0.1
            ? "text-emerald-400"
            : score <= 0.2
            ? "text-yellow-400"
            : "text-red-400";
    return (
        <span className={cn("text-xs font-mono tabular-nums font-semibold", color)}>
            {score.toFixed(3)}
        </span>
    );
}

function StatusBadge({ status }: { status: string | null }) {
    if (status === "CORRECT")
        return (
            <span className="inline-flex items-center gap-1 rounded-full bg-emerald-900/40 px-2 py-0.5 text-[10px] font-semibold text-emerald-400 ring-1 ring-emerald-500/30">
                <CheckCircle2 className="w-2.5 h-2.5" /> Correct
            </span>
        );
    if (status === "INCORRECT")
        return (
            <span className="inline-flex items-center gap-1 rounded-full bg-red-900/40 px-2 py-0.5 text-[10px] font-semibold text-red-400 ring-1 ring-red-500/30">
                <XCircle className="w-2.5 h-2.5" /> Wrong
            </span>
        );
    return (
        <span className="inline-flex items-center gap-1 rounded-full bg-zinc-800 px-2 py-0.5 text-[10px] font-semibold text-zinc-400 ring-1 ring-zinc-700">
            <Clock className="w-2.5 h-2.5" /> Pending
        </span>
    );
}

function CategoryPill({ category }: { category: string }) {
    const label: Record<string, string> = {
        game_outcome: "Game",
        player_performance: "Player",
        trade: "Trade",
        draft_pick: "Draft",
        injury: "Injury",
        contract: "Contract",
    };
    return (
        <span className="text-[10px] font-mono uppercase tracking-wide text-zinc-500 bg-zinc-900 border border-zinc-800 rounded px-1.5 py-0.5">
            {label[category] ?? category}
        </span>
    );
}

function RankBadge({ rank }: { rank: number }) {
    const color =
        rank === 1
            ? "text-yellow-400"
            : rank === 2
            ? "text-zinc-300"
            : rank === 3
            ? "text-orange-400"
            : "text-zinc-600";
    return (
        <span className={cn("font-mono text-sm font-black w-5 shrink-0 tabular-nums", color)}>
            {rank}
        </span>
    );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function LedgerPage() {
    const [pundits, setPundits] = useState<PunditStat[]>([]);
    const [recent, setRecent] = useState<RecentPrediction[]>([]);
    const [loading, setLoading] = useState(true);
    const [sportFilter, setSportFilter] = useState<string>("ALL");
    const [activeTab, setActiveTab] = useState<"leaderboard" | "recent">(
        "leaderboard"
    );

    useEffect(() => {
        const sportParam =
            sportFilter !== "ALL" ? `?sport=${sportFilter}` : "";
        Promise.all([
            fetch(`/api/ledger/pundits${sportParam}`).then((r) => r.json()),
            fetch(`/api/ledger/recent?limit=30${sportFilter !== "ALL" ? `&sport=${sportFilter}` : ""}`).then((r) =>
                r.json()
            ),
        ]).then(([punditsData, recentData]) => {
            setPundits(punditsData.pundits || []);
            setRecent(recentData.predictions || []);
        }).catch((err) => {
            console.error("[Ledger] Failed to load data:", err);
        }).finally(() => {
            setLoading(false);
        });
    }, [sportFilter]);

    // Sort leaderboard: resolved first (by accuracy desc), then unresolved (by total desc)
    const sorted = [...pundits].sort((a, b) => {
        const aResolved = a.resolved_predictions > 0;
        const bResolved = b.resolved_predictions > 0;
        if (aResolved && !bResolved) return -1;
        if (!aResolved && bResolved) return 1;
        if (aResolved && bResolved) {
            const accDiff = (b.accuracy_rate ?? 0) - (a.accuracy_rate ?? 0);
            if (accDiff !== 0) return accDiff;
            return (a.avg_brier_score ?? 1) - (b.avg_brier_score ?? 1);
        }
        return b.total_predictions - a.total_predictions;
    });

    const totalPredictions = pundits.reduce((s, p) => s + p.total_predictions, 0);
    const totalResolved = pundits.reduce((s, p) => s + p.resolved_predictions, 0);
    const resolvedFeed = recent.filter(
        (r) => r.resolution_status === "CORRECT" || r.resolution_status === "INCORRECT"
    );

    const SPORTS = ["ALL", "NFL", "NBA", "MLB"];

    return (
        <div className="min-h-screen bg-black text-white">
            {/* Header */}
            <div className="border-b border-zinc-900 bg-zinc-950/50">
                <div className="max-w-6xl mx-auto px-4 py-8">
                    <div className="flex items-start justify-between gap-4">
                        <div>
                            <div className="flex items-center gap-2 mb-2">
                                <Shield className="w-4 h-4 text-emerald-400" />
                                <span className="text-xs font-mono uppercase tracking-widest text-emerald-400">
                                    Cryptographically Sealed
                                </span>
                            </div>
                            <h1 className="text-3xl font-black tracking-tight text-white">
                                Pundit Ledger
                            </h1>
                            <p className="mt-1 text-sm text-zinc-400 max-w-lg">
                                Every public sports prediction tracked, scored, and sealed on-chain
                                — so no one can rewrite history.
                            </p>
                        </div>

                        {/* Aggregate stats */}
                        <div className="hidden sm:flex items-center gap-6 text-right shrink-0">
                            <div>
                                <div className="text-2xl font-black font-mono text-white tabular-nums">
                                    {pundits.length}
                                </div>
                                <div className="text-xs text-zinc-500 font-mono">Pundits</div>
                            </div>
                            <div>
                                <div className="text-2xl font-black font-mono text-white tabular-nums">
                                    {totalPredictions.toLocaleString()}
                                </div>
                                <div className="text-xs text-zinc-500 font-mono">Predictions</div>
                            </div>
                            <div>
                                <div className="text-2xl font-black font-mono text-emerald-400 tabular-nums">
                                    {totalResolved.toLocaleString()}
                                </div>
                                <div className="text-xs text-zinc-500 font-mono">Resolved</div>
                            </div>
                        </div>
                    </div>

                    {/* Sport filter */}
                    <div className="flex items-center gap-2 mt-6">
                        {SPORTS.map((s) => (
                            <button
                                key={s}
                                onClick={() => setSportFilter(s)}
                                className={cn(
                                    "px-3 py-1 rounded text-xs font-mono font-semibold uppercase tracking-wide transition-colors border",
                                    sportFilter === s
                                        ? "bg-emerald-500/15 border-emerald-500/40 text-emerald-400"
                                        : "bg-zinc-900 border-zinc-800 text-zinc-500 hover:text-zinc-300 hover:border-zinc-700"
                                )}
                            >
                                {s}
                            </button>
                        ))}
                    </div>
                </div>
            </div>

            {/* Tabs */}
            <div className="border-b border-zinc-900">
                <div className="max-w-6xl mx-auto px-4">
                    <div className="flex gap-0">
                        {(["leaderboard", "recent"] as const).map((tab) => (
                            <button
                                key={tab}
                                onClick={() => setActiveTab(tab)}
                                className={cn(
                                    "px-5 py-3 text-sm font-semibold uppercase tracking-wide transition-colors border-b-2",
                                    activeTab === tab
                                        ? "border-emerald-500 text-emerald-400"
                                        : "border-transparent text-zinc-500 hover:text-zinc-300"
                                )}
                            >
                                {tab === "leaderboard" ? "Leaderboard" : `Recent (${resolvedFeed.length})`}
                            </button>
                        ))}
                    </div>
                </div>
            </div>

            {/* Content */}
            <div className="max-w-6xl mx-auto px-4 py-8">
                {loading ? (
                    <div className="flex items-center justify-center h-48 text-zinc-600">
                        <Activity className="w-4 h-4 animate-pulse mr-2" />
                        <span className="font-mono text-sm">Loading ledger…</span>
                    </div>
                ) : activeTab === "leaderboard" ? (
                    <LeaderboardTab pundits={sorted} />
                ) : (
                    <RecentTab predictions={recent} />
                )}
            </div>
        </div>
    );
}

// ---------------------------------------------------------------------------
// Leaderboard tab
// ---------------------------------------------------------------------------

function LeaderboardTab({ pundits }: { pundits: PunditStat[] }) {
    if (pundits.length === 0) {
        return (
            <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 py-16 text-center text-zinc-500 text-sm">
                No pundit data yet — pipeline populating soon.
            </div>
        );
    }

    return (
        <div className="space-y-2">
            {/* Column headers */}
            <div className="hidden md:grid grid-cols-[32px_1fr_130px_90px_80px_70px_90px_80px] gap-3 px-4 pb-1 text-[10px] font-mono uppercase tracking-widest text-zinc-600">
                <span>#</span>
                <span>Pundit</span>
                <span>Accuracy</span>
                <span className="text-right">Correct</span>
                <span className="text-right">Wrong</span>
                <span className="text-right">Brier ↓</span>
                <span className="text-right">Picks</span>
                <span className="text-right"></span>
            </div>

            {pundits.map((p, idx) => (
                <div
                    key={`${p.pundit_id}-${p.sport}`}
                    className={cn(
                        "rounded-xl border bg-zinc-900/50 px-4 py-3 transition-colors",
                        idx < 3
                            ? "border-zinc-700/70"
                            : "border-zinc-800/60"
                    )}
                >
                    {/* Desktop layout */}
                    <div className="hidden md:grid grid-cols-[32px_1fr_130px_90px_80px_70px_90px_80px] gap-3 items-center">
                        <RankBadge rank={idx + 1} />

                        <div className="min-w-0">
                            <div className="font-semibold text-white truncate text-sm">
                                {p.pundit_name}
                            </div>
                            <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                                <CategoryBreakdown p={p} />
                            </div>
                        </div>

                        <AccuracyBar rate={p.accuracy_rate} />

                        <span className="text-right text-sm font-mono font-semibold text-emerald-400 tabular-nums">
                            {p.correct_predictions > 0 ? p.correct_predictions : "—"}
                        </span>
                        <span className="text-right text-sm font-mono font-semibold text-red-400 tabular-nums">
                            {p.incorrect_predictions > 0 ? p.incorrect_predictions : "—"}
                        </span>
                        <div className="flex justify-end">
                            <BrierBadge score={p.avg_brier_score} />
                        </div>
                        <span className="text-right text-xs font-mono text-zinc-500 tabular-nums">
                            {p.total_predictions}
                        </span>
                        <div className="flex justify-end">
                            {p.pundit_id && p.pundit_id !== "None" ? (
                                <Link
                                    href={`/ledger/${encodeURIComponent(p.pundit_id)}`}
                                    className="text-[10px] font-mono text-zinc-600 hover:text-emerald-400 transition-colors inline-flex items-center gap-0.5"
                                >
                                    Card <ArrowRight className="w-2.5 h-2.5" />
                                </Link>
                            ) : null}
                        </div>
                    </div>

                    {/* Mobile layout */}
                    <div className="flex md:hidden items-center gap-3">
                        <RankBadge rank={idx + 1} />
                        <div className="flex-1 min-w-0">
                            <div className="font-semibold text-white text-sm truncate">
                                {p.pundit_name}
                            </div>
                            <AccuracyBar rate={p.accuracy_rate} />
                        </div>
                        <div className="text-right shrink-0">
                            <div className="text-xs font-mono text-zinc-400">
                                {p.total_predictions} picks
                            </div>
                            <div className="flex items-center gap-1.5 justify-end mt-0.5">
                                {p.correct_predictions > 0 && (
                                    <span className="text-xs font-mono text-emerald-400">
                                        ✓{p.correct_predictions}
                                    </span>
                                )}
                                {p.incorrect_predictions > 0 && (
                                    <span className="text-xs font-mono text-red-400">
                                        ✗{p.incorrect_predictions}
                                    </span>
                                )}
                            </div>
                            {p.pundit_id && p.pundit_id !== "None" && (
                                <Link
                                    href={`/ledger/${encodeURIComponent(p.pundit_id)}`}
                                    className="text-[10px] font-mono text-zinc-600 hover:text-emerald-400 transition-colors inline-flex items-center gap-0.5 mt-1"
                                >
                                    Card <ArrowRight className="w-2.5 h-2.5" />
                                </Link>
                            )}
                        </div>
                    </div>
                </div>
            ))}

            <p className="text-xs text-zinc-600 font-mono text-center pt-4">
                Brier score: lower is better (0 = perfect). Ranked by accuracy, then Brier score.
            </p>
        </div>
    );
}

function CategoryBreakdown({ p }: { p: PunditStat }) {
    const cats = [
        { key: "game_outcome_count", label: "Game" },
        { key: "player_performance_count", label: "Player" },
        { key: "trade_count", label: "Trade" },
        { key: "draft_pick_count", label: "Draft" },
    ] as const;

    const nonZero = cats.filter(
        (c) => (p[c.key as keyof PunditStat] as number) > 0
    );
    if (nonZero.length === 0) return null;

    return (
        <>
            {nonZero.map((c) => (
                <span
                    key={c.key}
                    className="text-[10px] font-mono text-zinc-600 leading-none"
                >
                    {c.label}:{" "}
                    <span className="text-zinc-400">
                        {p[c.key as keyof PunditStat] as number}
                    </span>
                </span>
            ))}
        </>
    );
}

// ---------------------------------------------------------------------------
// Recent tab
// ---------------------------------------------------------------------------

function RecentTab({ predictions }: { predictions: RecentPrediction[] }) {
    const resolved = predictions.filter(
        (p) =>
            p.resolution_status === "CORRECT" || p.resolution_status === "INCORRECT"
    );
    const pending = predictions.filter(
        (p) => !p.resolution_status || p.resolution_status === "PENDING"
    );

    if (predictions.length === 0) {
        return (
            <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 py-16 text-center text-zinc-500 text-sm">
                No recent predictions yet.
            </div>
        );
    }

    return (
        <div className="space-y-6">
            {resolved.length > 0 && (
                <div>
                    <h3 className="text-xs font-mono uppercase tracking-widest text-zinc-500 mb-3">
                        Recently Resolved
                    </h3>
                    <div className="space-y-2">
                        {resolved.map((p) => (
                            <PredictionRow key={p.prediction_hash_short} p={p} />
                        ))}
                    </div>
                </div>
            )}

            {pending.length > 0 && (
                <div>
                    <h3 className="text-xs font-mono uppercase tracking-widest text-zinc-500 mb-3">
                        Awaiting Resolution
                    </h3>
                    <div className="space-y-2">
                        {pending.slice(0, 10).map((p) => (
                            <PredictionRow key={p.prediction_hash_short} p={p} />
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}

function PredictionRow({ p }: { p: RecentPrediction }) {
    const date = p.ingestion_timestamp
        ? new Date(p.ingestion_timestamp).toLocaleDateString("en-US", {
              month: "short",
              day: "numeric",
              year: "numeric",
          })
        : null;

    return (
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 px-4 py-3 flex items-start gap-3">
            <StatusBadge status={p.resolution_status} />
            <div className="flex-1 min-w-0">
                <p className="text-sm text-white leading-snug line-clamp-2">
                    {p.extracted_claim}
                </p>
                <div className="flex items-center gap-3 mt-1.5 flex-wrap">
                    <span className="text-xs font-semibold text-zinc-300">
                        {p.pundit_name}
                    </span>
                    <CategoryPill category={p.claim_category} />
                    {p.season_year && (
                        <span className="text-[10px] font-mono text-zinc-600">
                            {p.season_year}
                        </span>
                    )}
                    {date && (
                        <span className="text-[10px] font-mono text-zinc-600">{date}</span>
                    )}
                    {p.brier_score !== null && (
                        <span className="text-[10px] font-mono text-zinc-500">
                            Brier: <BrierBadge score={p.brier_score} />
                        </span>
                    )}
                </div>
            </div>
            <span className="text-[10px] font-mono text-zinc-700 shrink-0 hidden sm:block">
                #{p.prediction_hash_short}
            </span>
        </div>
    );
}
