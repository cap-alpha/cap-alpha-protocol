"use client";

/**
 * StatsStrip — Client Component
 *
 * Renders three animated ledger stats (resolved predictions, pundits tracked,
 * total claims) using AnimatedCounter.  Designed for the hero section.
 *
 * Mobile: single column stack.  Desktop: horizontal pipe-separated row.
 *
 * Props are numeric so the parent (server component) can read them from the
 * snapshot and pass them down without re-importing JSON on the client.
 */

import { AnimatedCounter } from "@/components/animated-counter";

export interface StatsStripProps {
    resolvedPredictions: number;
    punditCount: number;
    totalPredictions: number;
}

const STATS = (p: StatsStripProps) => [
    { value: p.resolvedPredictions, label: "RESOLVED PREDICTIONS", suffix: "" },
    { value: p.punditCount, label: "PUNDITS TRACKED", suffix: "" },
    { value: p.totalPredictions, label: "CLAIMS LEDGERED", suffix: "" },
];

export function StatsStrip(props: StatsStripProps) {
    const stats = STATS(props);

    return (
        <div
            className="w-full mt-5"
            aria-label="Live ledger statistics"
        >
            {/* Mobile: stacked rows; Desktop: horizontal pipe-separated */}
            <div className="flex flex-col sm:flex-row items-center justify-center gap-1 sm:gap-0">
                {stats.map((stat, i) => (
                    <div key={stat.label} className="flex items-center gap-0">
                        <div className="flex flex-col sm:flex-row items-center sm:gap-2 px-4 sm:px-5 py-1 sm:py-0">
                            <AnimatedCounter
                                value={stat.value}
                                suffix={stat.suffix}
                                duration={1200}
                                className="font-mono font-black text-2xl sm:text-xl tabular-nums text-emerald-400 leading-none"
                            />
                            <span className="text-[10px] font-mono font-semibold uppercase tracking-[0.18em] text-zinc-500 sm:text-zinc-400">
                                {stat.label}
                            </span>
                        </div>
                        {/* Pipe separator — desktop only, except after last item */}
                        {i < stats.length - 1 && (
                            <span
                                className="hidden sm:inline text-zinc-700 font-light text-lg select-none"
                                aria-hidden="true"
                            >
                                ·
                            </span>
                        )}
                    </div>
                ))}
            </div>
        </div>
    );
}
