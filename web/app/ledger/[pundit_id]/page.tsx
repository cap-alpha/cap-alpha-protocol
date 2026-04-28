"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
    Shield,
    CheckCircle2,
    XCircle,
    Clock,
    ArrowLeft,
    Activity,
    TrendingUp,
    TrendingDown,
    Minus,
    ExternalLink,
} from "lucide-react";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface PunditSummary {
    pundit_id: string;
    pundit_name: string;
    sport: string;
    total_predictions: number;
    resolved_count: number;
    correct_count: number;
    accuracy_rate: number | null;
    avg_brier_score: number | null;
    avg_weighted_score: number | null;
}

interface CategoryBreakdown {
    claim_category: string;
    total: number;
    resolved: number;
    correct: number;
    accuracy_rate: number | null;
    avg_weighted_score: number | null;
}

interface Prediction {
    prediction_hash: string;
    ingestion_timestamp: string;
    source_url: string | null;
    raw_assertion_text: string | null;
    extracted_claim: string | null;
    claim_category: string;
    season_year: number | null;
    target_player_id: string | null;
    target_team: string | null;
    resolution_status: string;
    resolved_at: string | null;
    binary_correct: boolean | null;
    brier_score: number | null;
    weighted_score: number | null;
    outcome_notes: string | null;
}

interface PunditDetailResponse {
    pundit: PunditSummary;
    accuracy_by_category: CategoryBreakdown[];
}

interface PredictionsResponse {
    pundit_id: string;
    predictions: Prediction[];
    page: number;
    page_size: number;
    total: number;
    pages: number;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const CATEGORY_LABELS: Record<string, string> = {
    game_outcome: "Game Outcome",
    player_performance: "Player Performance",
    trade: "Trade",
    draft_pick: "Draft Pick",
    injury: "Injury",
    contract: "Contract",
};

const CATEGORY_COLORS: Record<string, string> = {
    game_outcome: "text-blue-400 bg-blue-900/30 border-blue-800/50",
    player_performance: "text-purple-400 bg-purple-900/30 border-purple-800/50",
    trade: "text-orange-400 bg-orange-900/30 border-orange-800/50",
    draft_pick: "text-emerald-400 bg-emerald-900/30 border-emerald-800/50",
    injury: "text-red-400 bg-red-900/30 border-red-800/50",
    contract: "text-yellow-400 bg-yellow-900/30 border-yellow-800/50",
};

function AccuracyGrade({ rate }: { rate: number | null }) {
    if (rate === null) return <span className="text-zinc-500 text-5xl font-black">—</span>;
    const pct = Math.round(rate * 100);
    const grade =
        pct >= 75 ? { letter: "A", color: "text-emerald-400" } :
        pct >= 60 ? { letter: "B", color: "text-lime-400" } :
        pct >= 50 ? { letter: "C", color: "text-yellow-400" } :
        pct >= 35 ? { letter: "D", color: "text-orange-400" } :
                    { letter: "F", color: "text-red-400" };
    return (
        <div className="flex items-baseline gap-3">
            <span className={cn("text-7xl font-black leading-none", grade.color)}>
                {grade.letter}
            </span>
            <span className={cn("text-3xl font-black font-mono", grade.color)}>
                {pct}%
            </span>
        </div>
    );
}

function AccuracyBar({ rate, size = "md" }: { rate: number | null; size?: "sm" | "md" }) {
    if (rate === null)
        return <span className="text-xs text-zinc-600 font-mono">—</span>;
    const pct = Math.round(rate * 100);
    const barColor =
        pct >= 60 ? "bg-emerald-500" : pct >= 45 ? "bg-yellow-500" : "bg-red-500";
    const textColor =
        pct >= 60 ? "text-emerald-400" : pct >= 45 ? "text-yellow-400" : "text-red-400";
    const barW = size === "sm" ? "w-20" : "w-28";
    return (
        <div className="flex items-center gap-2">
            <div className={cn("h-1.5 rounded-full bg-zinc-800 overflow-hidden", barW)}>
                <div
                    className={cn("h-full rounded-full", barColor)}
                    style={{ width: `${pct}%` }}
                />
            </div>
            <span className={cn("text-xs font-mono font-semibold tabular-nums", textColor)}>
                {pct}%
            </span>
        </div>
    );
}

function StatusBadge({ status }: { status: string }) {
    if (status === "CORRECT")
        return (
            <span className="inline-flex items-center gap-1 rounded-full bg-emerald-900/40 px-2 py-0.5 text-[10px] font-semibold text-emerald-400 ring-1 ring-emerald-500/30 shrink-0">
                <CheckCircle2 className="w-2.5 h-2.5" /> Correct
            </span>
        );
    if (status === "INCORRECT")
        return (
            <span className="inline-flex items-center gap-1 rounded-full bg-red-900/40 px-2 py-0.5 text-[10px] font-semibold text-red-400 ring-1 ring-red-500/30 shrink-0">
                <XCircle className="w-2.5 h-2.5" /> Wrong
            </span>
        );
    return (
        <span className="inline-flex items-center gap-1 rounded-full bg-zinc-800 px-2 py-0.5 text-[10px] font-semibold text-zinc-400 ring-1 ring-zinc-700 shrink-0">
            <Clock className="w-2.5 h-2.5" /> Pending
        </span>
    );
}

function CategoryPill({ category }: { category: string }) {
    const colorClass = CATEGORY_COLORS[category] ?? "text-zinc-400 bg-zinc-900 border-zinc-700";
    return (
        <span className={cn("text-[10px] font-mono uppercase tracking-wide border rounded px-1.5 py-0.5", colorClass)}>
            {CATEGORY_LABELS[category] ?? category}
        </span>
    );
}

function StatCard({
    label,
    value,
    sub,
    accent,
}: {
    label: string;
    value: string | number;
    sub?: string;
    accent?: string;
}) {
    return (
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 px-5 py-4">
            <div className="text-xs font-mono uppercase tracking-widest text-zinc-500 mb-1">
                {label}
            </div>
            <div className={cn("text-2xl font-black font-mono tabular-nums", accent ?? "text-white")}>
                {value}
            </div>
            {sub && <div className="text-xs text-zinc-600 font-mono mt-0.5">{sub}</div>}
        </div>
    );
}

// ---------------------------------------------------------------------------
// Category breakdown section
// ---------------------------------------------------------------------------

function CategorySection({ breakdown }: { breakdown: CategoryBreakdown[] }) {
    if (breakdown.length === 0) return null;

    return (
        <div>
            <h2 className="text-xs font-mono uppercase tracking-widest text-zinc-500 mb-3">
                Breakdown by Category
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {breakdown.map((cat) => (
                    <div
                        key={cat.claim_category}
                        className="rounded-xl border border-zinc-800 bg-zinc-900/40 px-4 py-3"
                    >
                        <div className="flex items-center justify-between mb-2">
                            <CategoryPill category={cat.claim_category} />
                            <span className="text-xs font-mono text-zinc-500 tabular-nums">
                                {cat.total} picks
                            </span>
                        </div>
                        <div className="flex items-center justify-between">
                            <AccuracyBar rate={cat.accuracy_rate} size="sm" />
                            <div className="flex items-center gap-2 text-xs font-mono">
                                <span className="text-emerald-400 tabular-nums">
                                    ✓{cat.correct}
                                </span>
                                <span className="text-zinc-600">
                                    /{cat.resolved}
                                </span>
                            </div>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}

// ---------------------------------------------------------------------------
// Predictions feed
// ---------------------------------------------------------------------------

function PredictionCard({ p }: { p: Prediction }) {
    const date = p.ingestion_timestamp
        ? new Date(p.ingestion_timestamp).toLocaleDateString("en-US", {
              month: "short",
              day: "numeric",
              year: "numeric",
          })
        : null;

    const resolvedDate = p.resolved_at
        ? new Date(p.resolved_at).toLocaleDateString("en-US", {
              month: "short",
              day: "numeric",
              year: "numeric",
          })
        : null;

    const isWrong = p.resolution_status === "INCORRECT";

    return (
        <div
            className={cn(
                "rounded-xl border bg-zinc-900/40 px-4 py-3 flex items-start gap-3 transition-colors",
                isWrong
                    ? "border-red-900/40 bg-red-950/10"
                    : p.resolution_status === "CORRECT"
                    ? "border-emerald-900/30"
                    : "border-zinc-800/60"
            )}
        >
            <StatusBadge status={p.resolution_status} />
            <div className="flex-1 min-w-0">
                <p className="text-sm text-white leading-snug">
                    {p.extracted_claim || p.raw_assertion_text || "(no claim text)"}
                </p>
                {p.outcome_notes && isWrong && (
                    <p className="mt-1.5 text-xs text-red-400/80 italic leading-snug">
                        {p.outcome_notes}
                    </p>
                )}
                <div className="flex items-center gap-3 mt-2 flex-wrap">
                    <CategoryPill category={p.claim_category} />
                    {p.season_year && (
                        <span className="text-[10px] font-mono text-zinc-600">
                            {p.season_year}
                        </span>
                    )}
                    {p.target_team && (
                        <span className="text-[10px] font-mono text-zinc-600">
                            {p.target_team}
                        </span>
                    )}
                    {date && (
                        <span className="text-[10px] font-mono text-zinc-600">{date}</span>
                    )}
                    {resolvedDate && p.resolution_status !== "PENDING" && (
                        <span className="text-[10px] font-mono text-zinc-500">
                            resolved {resolvedDate}
                        </span>
                    )}
                    {p.source_url && (
                        <a
                            href={p.source_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-[10px] font-mono text-zinc-600 hover:text-zinc-400 inline-flex items-center gap-0.5"
                        >
                            source <ExternalLink className="w-2.5 h-2.5" />
                        </a>
                    )}
                </div>
            </div>
            <span className="text-[10px] font-mono text-zinc-700 shrink-0 hidden sm:block">
                #{p.prediction_hash?.slice(-8)}
            </span>
        </div>
    );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function PunditAccountabilityPage() {
    const params = useParams();
    const punditId = Array.isArray(params.pundit_id)
        ? params.pundit_id[0]
        : params.pundit_id ?? "";

    const [detail, setDetail] = useState<PunditDetailResponse | null>(null);
    const [preds, setPreds] = useState<PredictionsResponse | null>(null);
    const [loading, setLoading] = useState(true);
    const [predsLoading, setPredsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [page, setPage] = useState(1);
    const [statusFilter, setStatusFilter] = useState<string>("ALL");

    // Load pundit detail
    useEffect(() => {
        if (!punditId) return;
        setLoading(true);
        fetch(`/api/ledger/pundits/${encodeURIComponent(punditId)}`)
            .then((r) => {
                if (!r.ok) throw new Error(`HTTP ${r.status}`);
                return r.json();
            })
            .then((data: PunditDetailResponse) => setDetail(data))
            .catch((e) => setError(e.message))
            .finally(() => setLoading(false));
    }, [punditId]);

    // Load predictions (paginated + filtered)
    useEffect(() => {
        if (!punditId) return;
        setPredsLoading(true);
        const statusParam =
            statusFilter !== "ALL" ? `&status=${statusFilter}` : "";
        fetch(
            `/api/ledger/pundits/${encodeURIComponent(punditId)}/predictions?page=${page}&page_size=20${statusParam}`
        )
            .then((r) => r.json())
            .then((data: PredictionsResponse) => setPreds(data))
            .catch(console.error)
            .finally(() => setPredsLoading(false));
    }, [punditId, page, statusFilter]);

    if (loading) {
        return (
            <div className="min-h-screen bg-black text-white flex items-center justify-center">
                <Activity className="w-4 h-4 animate-pulse mr-2 text-zinc-600" />
                <span className="font-mono text-sm text-zinc-600">Loading pundit card…</span>
            </div>
        );
    }

    if (error || !detail) {
        return (
            <div className="min-h-screen bg-black text-white flex flex-col items-center justify-center gap-4">
                <p className="text-red-400 font-mono text-sm">
                    {error ?? "Pundit not found"}
                </p>
                <Link
                    href="/ledger"
                    className="text-xs font-mono text-zinc-500 hover:text-zinc-300 inline-flex items-center gap-1"
                >
                    <ArrowLeft className="w-3 h-3" /> Back to Ledger
                </Link>
            </div>
        );
    }

    const { pundit, accuracy_by_category } = detail;
    const incorrectCount = (pundit.resolved_count ?? 0) - (pundit.correct_count ?? 0);
    const pendingCount = (pundit.total_predictions ?? 0) - (pundit.resolved_count ?? 0);

    const wrongPredictions = preds?.predictions.filter(
        (p) => p.resolution_status === "INCORRECT"
    ) ?? [];

    // Top-5 loud-and-wrong receipts (wrong ones from full feed)
    const topWrong = wrongPredictions.slice(0, 5);

    const STATUS_FILTERS = ["ALL", "CORRECT", "INCORRECT", "PENDING"];

    return (
        <div className="min-h-screen bg-black text-white">
            {/* Header / Hero */}
            <div className="border-b border-zinc-900 bg-zinc-950/50">
                <div className="max-w-5xl mx-auto px-4 py-8">
                    {/* Back link */}
                    <Link
                        href="/ledger"
                        className="inline-flex items-center gap-1.5 text-xs font-mono text-zinc-500 hover:text-zinc-300 mb-6 transition-colors"
                    >
                        <ArrowLeft className="w-3 h-3" /> Pundit Ledger
                    </Link>

                    {/* Pundit identity + headline score */}
                    <div className="flex flex-col sm:flex-row sm:items-end gap-6">
                        <div className="flex-1">
                            <div className="flex items-center gap-2 mb-1">
                                <Shield className="w-3.5 h-3.5 text-emerald-400" />
                                <span className="text-[10px] font-mono uppercase tracking-widest text-emerald-400">
                                    Accountability Card
                                </span>
                            </div>
                            <h1 className="text-4xl font-black tracking-tight text-white leading-none">
                                {pundit.pundit_name}
                            </h1>
                            <p className="mt-1 text-sm text-zinc-500 font-mono">
                                {pundit.sport} · {pundit.pundit_id}
                            </p>
                        </div>

                        {/* Headline score */}
                        <div className="shrink-0">
                            <AccuracyGrade rate={pundit.accuracy_rate} />
                            {pundit.resolved_count > 0 && (
                                <p className="text-xs text-zinc-600 font-mono mt-1">
                                    {pundit.resolved_count} resolved predictions
                                </p>
                            )}
                        </div>
                    </div>

                    {/* Stat row */}
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-8">
                        <StatCard
                            label="Total Picks"
                            value={pundit.total_predictions}
                        />
                        <StatCard
                            label="Resolved"
                            value={pundit.resolved_count}
                            sub={`${pendingCount} pending`}
                        />
                        <StatCard
                            label="Correct"
                            value={pundit.correct_count}
                            accent="text-emerald-400"
                        />
                        <StatCard
                            label="Wrong"
                            value={incorrectCount}
                            accent={incorrectCount > 0 ? "text-red-400" : "text-zinc-400"}
                        />
                    </div>
                </div>
            </div>

            {/* Body */}
            <div className="max-w-5xl mx-auto px-4 py-8 space-y-10">
                {/* Category breakdown */}
                <CategorySection breakdown={accuracy_by_category} />

                {/* Top-5 wrong receipts */}
                {topWrong.length > 0 && (
                    <div>
                        <div className="flex items-center gap-2 mb-3">
                            <TrendingDown className="w-3.5 h-3.5 text-red-400" />
                            <h2 className="text-xs font-mono uppercase tracking-widest text-red-400">
                                Loud-and-Wrong Receipts
                            </h2>
                        </div>
                        <div className="space-y-2">
                            {topWrong.map((p) => (
                                <PredictionCard key={p.prediction_hash} p={p} />
                            ))}
                        </div>
                    </div>
                )}

                {/* Full prediction history */}
                <div>
                    <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
                        <div className="flex items-center gap-2">
                            <Activity className="w-3.5 h-3.5 text-zinc-500" />
                            <h2 className="text-xs font-mono uppercase tracking-widest text-zinc-500">
                                Prediction History
                                {preds ? ` (${preds.total})` : ""}
                            </h2>
                        </div>

                        {/* Status filter */}
                        <div className="flex items-center gap-1.5">
                            {STATUS_FILTERS.map((s) => (
                                <button
                                    key={s}
                                    onClick={() => {
                                        setStatusFilter(s);
                                        setPage(1);
                                    }}
                                    className={cn(
                                        "px-2.5 py-1 rounded text-[10px] font-mono font-semibold uppercase tracking-wide transition-colors border",
                                        statusFilter === s
                                            ? "bg-emerald-500/15 border-emerald-500/40 text-emerald-400"
                                            : "bg-zinc-900 border-zinc-800 text-zinc-500 hover:text-zinc-300 hover:border-zinc-700"
                                    )}
                                >
                                    {s}
                                </button>
                            ))}
                        </div>
                    </div>

                    {predsLoading ? (
                        <div className="flex items-center justify-center h-24 text-zinc-600">
                            <Activity className="w-3.5 h-3.5 animate-pulse mr-2" />
                            <span className="font-mono text-sm">Loading…</span>
                        </div>
                    ) : preds && preds.predictions.length > 0 ? (
                        <>
                            <div className="space-y-2">
                                {preds.predictions.map((p) => (
                                    <PredictionCard key={p.prediction_hash} p={p} />
                                ))}
                            </div>

                            {/* Pagination */}
                            {preds.pages > 1 && (
                                <div className="flex items-center justify-center gap-3 mt-6">
                                    <button
                                        onClick={() => setPage((p) => Math.max(1, p - 1))}
                                        disabled={page === 1}
                                        className="px-3 py-1.5 rounded text-xs font-mono border border-zinc-800 text-zinc-400 hover:text-white hover:border-zinc-600 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                                    >
                                        ← Prev
                                    </button>
                                    <span className="text-xs font-mono text-zinc-500 tabular-nums">
                                        {page} / {preds.pages}
                                    </span>
                                    <button
                                        onClick={() => setPage((p) => Math.min(preds.pages, p + 1))}
                                        disabled={page === preds.pages}
                                        className="px-3 py-1.5 rounded text-xs font-mono border border-zinc-800 text-zinc-400 hover:text-white hover:border-zinc-600 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                                    >
                                        Next →
                                    </button>
                                </div>
                            )}
                        </>
                    ) : (
                        <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 py-12 text-center text-zinc-500 text-sm font-mono">
                            No predictions found
                            {statusFilter !== "ALL" ? ` with status ${statusFilter}` : ""}.
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
