/**
 * TrustStrip — Server Component
 *
 * Displays three aggregate trust signals derived from the leaderboard snapshot:
 * resolved predictions, pundits tracked, and total claims.
 *
 * Reads counts server-side from the snapshot and delegates rendering to the
 * StatsStrip client component (animated counters).
 *
 * Intended position: inside the hero section, below the CTA.
 */

import snapshot from "@/lib/data/leaderboard-snapshot.json";
import { StatsStrip } from "@/components/stats-strip";

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

    return (
        <div className="w-full px-4 sm:px-6 py-4">
            <div className="max-w-2xl mx-auto">
                <StatsStrip
                    resolvedPredictions={resolvedPredictions}
                    punditCount={punditCount}
                    totalPredictions={totalPredictions}
                />
            </div>
        </div>
    );
}
