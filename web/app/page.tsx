import Link from "next/link";
import { WaitlistForm } from "@/components/waitlist-form";
import { PunditLeaderboardPreview } from "@/components/pundit-leaderboard-preview";
import { TrackedPredictionCard } from "@/components/tracked-prediction-card";
import { TrustStrip } from "@/components/trust-strip";
import { RecentResolutionsTicker } from "@/components/recent-resolutions-ticker";
import { fetchPunditsSSR } from "@/lib/ledger-server";
import { fetchRecentResolutionsSSR } from "@/lib/recent-resolutions-server";
import snapshot from "@/lib/data/leaderboard-snapshot.json";

// Pundit accuracy updates at most daily (new resolutions land overnight).
// 1-hour page-level ISR keeps HTML fresh enough while avoiding the cold-render
// penalty on every visitor.  The inner fetchPunditsSSR call uses its own
// 5-minute revalidate window so data can update independently of this HTML cache.
export const revalidate = 3600; // 1-hour ISR

export default async function LandingPage() {
    // Fetch top NFL pundits and recent resolutions server-side in parallel so
    // the first HTML response includes real data — no blank spinners on FCP.
    // Both helpers fall back to static snapshots when the backend is unavailable
    // (issue #960).
    const [
        { pundits: initialPundits, fallback: isFallback },
        { resolutions, fallback: resolutionsFallback },
    ] = await Promise.all([
        fetchPunditsSSR("NFL", 20),
        fetchRecentResolutionsSSR(5),
    ]);

    // snapshot.pundits is the authoritative source for hero stats.
    // initialPundits is truncated (top-20) so we use the full snapshot for aggregate counts.
    const snapshotData = snapshot.pundits;

    // Format the pipeline watermark in Pacific time for the "Last updated" label.
    // snapshot_metadata.generated_at is an ISO-8601 UTC string set by the nightly
    // BigQuery export job.  We render it server-side so the label is stable across
    // client navigations and requires no client JS.
    const generatedAt = (snapshot.snapshot_metadata as { generated_at?: string }).generated_at;
    const lastUpdatedLabel = (() => {
        if (!generatedAt) return "Updated daily ~6am PT";
        try {
            const d = new Date(generatedAt);
            return "Last updated: " + d.toLocaleDateString("en-US", {
                timeZone: "America/Los_Angeles",
                month: "long",
                day: "numeric",
                year: "numeric",
            });
        } catch {
            return "Updated daily ~6am PT";
        }
    })();

    return (
        <div className="bg-black text-white min-h-[100dvh] flex flex-col font-sans">
            {/* ── Hero ── */}
            <section className="relative flex flex-col items-center justify-center text-center px-4 sm:px-6 pt-16 sm:pt-20 pb-10 overflow-hidden">
                {/* Background glow */}
                <div className="absolute inset-0 pointer-events-none">
                    <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[700px] h-[320px] bg-emerald-500/8 rounded-full blur-[120px]" />
                </div>

                <div className="relative z-10 w-full max-w-2xl mx-auto space-y-4">
                    {/* Static badge — no live/pulse chrome */}
                    <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-emerald-500/30 bg-emerald-500/10 text-emerald-400 text-xs font-mono font-medium uppercase tracking-widest">
                        Prediction Receipts
                    </div>

                    {/* Hero headline — 2 lines max */}
                    <h1 className="font-display font-black text-3xl sm:text-5xl lg:text-6xl tracking-tight leading-tight text-white">
                        Sports pundits guess.{" "}
                        <span className="text-emerald-400">We keep the receipts.</span>
                    </h1>
                    <p className="text-base sm:text-lg text-zinc-400 leading-snug">
                        Every prediction logged. Every verdict public.
                    </p>

                    {/* Single CTA — min 44px height for Apple HIG tap target */}
                    <div className="pt-2">
                        <Link
                            href="/ledger"
                            className="inline-flex items-center gap-2 min-h-[44px] px-7 py-3 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-black font-bold text-base transition-colors shadow-[0_0_24px_rgba(16,185,129,0.3)] hover:shadow-[0_0_32px_rgba(16,185,129,0.5)]"
                        >
                            See the full ledger →
                        </Link>
                    </div>

                    {/* ── Animated stats strip — ledger counts from snapshot ── */}
                    {/* Numbers come from the snapshot (read server-side); AnimatedCounter runs client-side */}
                    <TrustStrip
                        pundits={snapshotData.map((p) => ({
                            total_predictions: p.total_predictions,
                            resolved_predictions: p.resolved_predictions,
                        }))}
                    />

                    {/* ── Static watermark — no real-time chrome ── */}
                    <p className="text-[11px] font-mono text-zinc-600 tracking-wide">
                        {lastUpdatedLabel}
                    </p>
                </div>
            </section>

            {/* ── Tracked Prediction ── thesis demo card */}
            <section className="w-full px-6 pb-10">
                <div className="max-w-2xl mx-auto">
                    <TrackedPredictionCard />
                </div>
            </section>

            {/* ── Leaderboard Preview ── */}
            {/* overflow-x-hidden prevents any inner table from causing page-level horizontal scroll */}
            <section className="w-full px-4 sm:px-6 pb-8 overflow-x-hidden">
                <div className="max-w-2xl mx-auto min-w-0 space-y-4">
                    <h2 className="text-xs font-mono uppercase tracking-widest text-zinc-500">
                        Least Wrong, Recently
                    </h2>
                    <PunditLeaderboardPreview sport="NFL" initialPundits={initialPundits} fallback={isFallback} />
                </div>
            </section>

            {/* ── Recent Resolutions Ticker ── last 5 resolved verdicts */}
            <RecentResolutionsTicker resolutions={resolutions} fallback={resolutionsFallback} />

            {/* ── Waitlist ── (stays per product milestone gating) */}
            <section className="w-full px-4 sm:px-6 py-16 border-t border-zinc-900">
                <div className="max-w-xl mx-auto text-center space-y-4">
                    <p className="text-xs font-mono uppercase tracking-widest text-zinc-500">
                        Early access
                    </p>
                    <h2 className="text-2xl font-display font-black text-white">
                        Get notified at launch.
                    </h2>
                    <WaitlistForm />
                </div>
            </section>

            {/* ── Footer ── */}
            <footer className="border-t border-zinc-900 px-4 sm:px-6 py-8 mt-auto">
                <div className="max-w-5xl mx-auto flex flex-col items-center gap-4 text-xs text-zinc-400">
                    <span className="font-black text-sm text-emerald-500 tracking-tight uppercase">
                        Pundit Ledger
                    </span>
                    <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-0">
                        <Link href="/ledger" className="min-h-[44px] inline-flex items-center hover:text-white transition-colors">Leaderboard</Link>
                        <Link href="/pricing" className="min-h-[44px] inline-flex items-center hover:text-white transition-colors">Pricing</Link>
                        <Link href="/methodology" className="min-h-[44px] inline-flex items-center hover:text-white transition-colors">Methodology</Link>
                        <Link href="/legal/terms" className="min-h-[44px] inline-flex items-center hover:text-white transition-colors">Terms</Link>
                        <Link href="/legal/privacy" className="min-h-[44px] inline-flex items-center hover:text-white transition-colors">Privacy</Link>
                        <Link href="/legal/acceptable-use" className="min-h-[44px] inline-flex items-center hover:text-white transition-colors">Acceptable Use</Link>
                    </div>
                    <span>© {new Date().getFullYear()} Pundit Ledger. All predictions verified.</span>
                </div>
            </footer>
        </div>
    );
}
