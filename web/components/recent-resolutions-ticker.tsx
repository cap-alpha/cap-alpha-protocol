/**
 * RecentResolutionsTicker — Server Component
 *
 * Displays a horizontal strip of the 5 most recent resolved predictions.
 * Each chip shows pundit name, truncated claim, CORRECT/WRONG verdict,
 * and a month/year timestamp.
 *
 * Intended position: below the leaderboard section, above the waitlist.
 * No animations — avoids framer-motion dependency removed in perf PR.
 */

import Link from "next/link";
import type { Resolution } from "@/lib/recent-resolutions-server";

interface RecentResolutionsTickerProps {
    resolutions: Resolution[];
    fallback?: boolean;
}

function formatMonth(isoDate: string): string {
    const d = new Date(isoDate);
    if (isNaN(d.getTime())) return "";
    return d.toLocaleDateString("en-US", { month: "short", year: "numeric" });
}

function VerdictPill({ correct }: { correct: boolean }) {
    if (correct) {
        return (
            <span className="inline-flex items-center rounded-sm px-1.5 py-0.5 text-[10px] font-mono font-bold uppercase tracking-wider bg-emerald-500/15 text-emerald-400 border border-emerald-500/25">
                Correct
            </span>
        );
    }
    return (
        <span className="inline-flex items-center rounded-sm px-1.5 py-0.5 text-[10px] font-mono font-bold uppercase tracking-wider bg-amber-500/15 text-amber-400 border border-amber-500/25">
            Wrong
        </span>
    );
}

export function RecentResolutionsTicker({
    resolutions,
    fallback,
}: RecentResolutionsTickerProps) {
    const visible = resolutions.slice(0, 5);

    return (
        <div className="w-full px-4 sm:px-6 py-6">
            <div className="max-w-2xl mx-auto space-y-3">
                {/* Section label */}
                <p className="text-[10px] font-mono font-medium uppercase tracking-widest text-zinc-500">
                    Recently resolved
                    {fallback && (
                        <span className="ml-2 text-zinc-600">(snapshot)</span>
                    )}
                </p>

                {/* Resolution chips */}
                <div className="flex flex-col sm:flex-row sm:flex-wrap gap-2">
                    {visible.map((r, i) => (
                        <div
                            key={`${r.pundit_id}-${i}`}
                            className="flex-1 sm:flex-none sm:min-w-[220px] sm:max-w-[280px] rounded-md border border-zinc-800 bg-zinc-950/60 px-3 py-2.5 space-y-1.5"
                        >
                            {/* Pundit name + verdict row */}
                            <div className="flex items-center justify-between gap-2">
                                <span className="font-semibold text-white text-xs truncate">
                                    {r.pundit_name}
                                </span>
                                <VerdictPill correct={r.binary_correct} />
                            </div>

                            {/* Claim text */}
                            <p className="text-zinc-400 text-xs leading-snug line-clamp-1">
                                {r.extracted_claim}
                            </p>

                            {/* Timestamp */}
                            {r.resolved_at && (
                                <p className="text-zinc-600 text-[10px] font-mono">
                                    {formatMonth(r.resolved_at)}
                                </p>
                            )}
                        </div>
                    ))}
                </div>

                {/* Footer link */}
                <div className="pt-1">
                    <Link
                        href="/ledger"
                        className="text-xs text-zinc-500 hover:text-emerald-400 transition-colors font-mono"
                    >
                        View full ledger →
                    </Link>
                </div>
            </div>
        </div>
    );
}
