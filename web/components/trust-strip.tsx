/**
 * TrustStrip — Server Component
 *
 * Displays three aggregate trust signals derived from the leaderboard snapshot:
 * pundits scored, predictions verified, and resolution rate.
 *
 * Renders immediately from static data (no client hydration needed).
 * Intended position: under the hero section, above the leaderboard.
 */

import snapshot from "@/lib/data/leaderboard-snapshot.json";

interface TrustStripProps {
    /** Pre-fetched pundit data — pass if you have it to avoid re-importing snapshot. */
    pundits?: Array<{
        total_predictions: number;
        resolved_predictions: number;
    }>;
}

export function TrustStrip({ pundits }: TrustStripProps) {
    const data = pundits ?? snapshot.pundits;

    const punditCount = data.length;
    const totalPredictions = data.reduce((sum, p) => sum + (p.total_predictions ?? 0), 0);
    const resolvedPredictions = data.reduce((sum, p) => sum + (p.resolved_predictions ?? 0), 0);
    const resolutionRate =
        totalPredictions > 0
            ? Math.round((resolvedPredictions / totalPredictions) * 100)
            : 0;

    const stats = [
        { value: String(punditCount), label: "Pundits Scored" },
        { value: String(resolvedPredictions), label: "Predictions Verified" },
        { value: `${resolutionRate}%`, label: "Resolution Rate" },
    ];

    return (
        <div className="w-full px-4 sm:px-6 py-4">
            <div className="max-w-2xl mx-auto">
                <div className="grid grid-cols-3 gap-2 sm:gap-4 rounded-lg border border-emerald-500/20 bg-zinc-950/80 px-4 sm:px-8 py-4 sm:py-5">
                    {stats.map((stat, i) => (
                        <div
                            key={stat.label}
                            className={
                                "flex flex-col items-center text-center" +
                                (i < stats.length - 1
                                    ? " border-r border-emerald-500/15"
                                    : "")
                            }
                        >
                            <span className="font-mono font-black text-2xl sm:text-3xl tabular-nums text-emerald-400 leading-none">
                                {stat.value}
                            </span>
                            <span className="mt-1 text-[10px] sm:text-xs font-mono font-medium uppercase tracking-widest text-zinc-500">
                                {stat.label}
                            </span>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}
