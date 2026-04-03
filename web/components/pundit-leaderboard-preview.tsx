"use client";

import { useEffect, useState } from "react";
import { Activity, CheckCircle2, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";

interface PunditStat {
    pundit_name: string;
    pundit_id: string;
    total_predictions: number;
    resolved_predictions: number;
    correct_predictions: number;
    incorrect_predictions: number;
    accuracy_rate: number | null;
    avg_brier_score: number | null;
}

function AccuracyBar({ rate }: { rate: number | null }) {
    if (rate === null) return <span className="text-xs text-zinc-600 font-mono">—</span>;
    const pct = Math.round(rate * 100);
    const color = pct >= 60 ? "bg-emerald-500" : pct >= 45 ? "bg-yellow-500" : "bg-red-500";
    return (
        <div className="flex items-center gap-2">
            <div className="w-20 h-1.5 rounded-full bg-zinc-800 overflow-hidden">
                <div className={cn("h-full rounded-full", color)} style={{ width: `${pct}%` }} />
            </div>
            <span className={cn("text-xs font-mono font-semibold tabular-nums",
                pct >= 60 ? "text-emerald-400" : pct >= 45 ? "text-yellow-400" : "text-red-400"
            )}>
                {pct}%
            </span>
        </div>
    );
}

export function PunditLeaderboardPreview() {
    const [pundits, setPundits] = useState<PunditStat[]>([]);
    const [loading, setLoading] = useState(true);
    const [totalPredictions, setTotalPredictions] = useState(0);
    const [totalResolved, setTotalResolved] = useState(0);

    useEffect(() => {
        fetch("/api/ledger/pundits")
            .then((r) => r.json())
            .then((data) => {
                const all: PunditStat[] = data.pundits || [];
                setTotalPredictions(all.reduce((a, p) => a + p.total_predictions, 0));
                setTotalResolved(all.reduce((a, p) => a + p.resolved_predictions, 0));
                setPundits(all.slice(0, 5));
            })
            .finally(() => setLoading(false));
    }, []);

    if (loading) {
        return (
            <div className="flex items-center justify-center h-40">
                <div className="flex items-center gap-2 text-zinc-600">
                    <Activity className="w-4 h-4 animate-pulse" />
                    <span className="text-sm font-mono">Loading ledger…</span>
                </div>
            </div>
        );
    }

    if (pundits.length === 0) {
        return (
            <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 py-12 text-center text-zinc-600 text-sm">
                No pundit data yet — pipeline populating soon.
            </div>
        );
    }

    return (
        <div className="space-y-3">
            {/* Stats bar */}
            <div className="flex gap-6 text-xs font-mono text-zinc-500 pb-2 border-b border-zinc-900">
                <span>
                    <span className="text-white font-semibold">{pundits.length}+</span> pundits tracked
                </span>
                <span>
                    <span className="text-white font-semibold">{totalPredictions.toLocaleString()}</span> predictions logged
                </span>
                <span>
                    <span className="text-white font-semibold">{totalResolved.toLocaleString()}</span> resolved
                </span>
            </div>

            {pundits.map((p, idx) => (
                <div
                    key={p.pundit_id}
                    className="flex items-center gap-4 rounded-xl border border-zinc-800 bg-zinc-900/50 px-4 py-3"
                >
                    {/* Rank */}
                    <span className={cn(
                        "font-mono text-base font-black w-6 shrink-0 tabular-nums",
                        idx === 0 ? "text-yellow-400"
                        : idx === 1 ? "text-zinc-300"
                        : idx === 2 ? "text-orange-400"
                        : "text-zinc-600"
                    )}>
                        {idx + 1}
                    </span>

                    {/* Name */}
                    <span className="font-semibold text-white flex-1 truncate">{p.pundit_name}</span>

                    {/* Accuracy bar */}
                    <div className="hidden sm:block">
                        <AccuracyBar rate={p.accuracy_rate} />
                    </div>

                    {/* Correct / Incorrect */}
                    {p.resolved_predictions > 0 && (
                        <div className="flex items-center gap-3 text-xs font-mono shrink-0">
                            <span className="flex items-center gap-1 text-emerald-400">
                                <CheckCircle2 className="w-3 h-3" />
                                {p.correct_predictions}
                            </span>
                            <span className="flex items-center gap-1 text-red-400">
                                <XCircle className="w-3 h-3" />
                                {p.incorrect_predictions}
                            </span>
                        </div>
                    )}

                    {/* Total */}
                    <span className="text-xs font-mono text-zinc-600 shrink-0 w-20 text-right">
                        {p.total_predictions} picks
                    </span>
                </div>
            ))}
        </div>
    );
}
