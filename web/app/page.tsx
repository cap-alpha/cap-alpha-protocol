import Link from "next/link";
import { WaitlistForm } from "@/components/waitlist-form";
import { SignUpCta } from "@/components/sign-up-cta";
import { PunditLeaderboardPreview } from "@/components/pundit-leaderboard-preview";
import { TrackedPredictionCard } from "@/components/tracked-prediction-card";
import { TrustStrip } from "@/components/trust-strip";
import { RecentResolutionsTicker } from "@/components/recent-resolutions-ticker";
import { fetchPunditsSSR } from "@/lib/ledger-server";
import { fetchRecentResolutionsSSR } from "@/lib/recent-resolutions-server";

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

    return (
        <div className="bg-black text-white min-h-[100dvh] flex flex-col font-sans">
            {/* ── Hero ── */}
            <section className="relative flex flex-col items-center justify-center text-center px-4 sm:px-6 pt-16 sm:pt-20 pb-10 overflow-hidden">
                {/* Background glow */}
                <div className="absolute inset-0 pointer-events-none">
                    <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[700px] h-[320px] bg-emerald-500/8 rounded-full blur-[120px]" />
                </div>

                <div className="relative z-10 w-full max-w-2xl mx-auto space-y-4">
                    {/* Live indicator */}
                    <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-emerald-500/30 bg-emerald-500/10 text-emerald-400 text-xs font-mono font-medium uppercase tracking-widest">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                        Live Edge Report
                    </div>

                    {/* Hero headline — 2 lines max */}
                    <h1 className="font-display font-black text-3xl sm:text-5xl lg:text-6xl tracking-tight leading-tight text-white">
                        The most accurate sports pundits, ranked.
                    </h1>
                    <p className="text-base sm:text-lg text-zinc-400 leading-snug">
                        Every prediction tracked, scored, and sealed.
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
                </div>
            </section>

            {/* ── Trust Strip ── scale signals: pundits scored, predictions verified, resolution rate */}
            <TrustStrip />

            {/* ── Tracked Prediction ── thesis demo card (PR #927) */}
            <section className="w-full px-6 pb-10">
                <div className="max-w-2xl mx-auto space-y-3">
                    <p className="text-[10px] font-mono uppercase tracking-widest text-zinc-500">
                        Tracked Prediction
                    </p>
                    <TrackedPredictionCard />
                </div>
            </section>

            {/* ── Live Leaderboard Preview ── (below trust strip + thesis card) */}
            {/* overflow-x-hidden prevents any inner table from causing page-level horizontal scroll */}
            <section className="w-full px-4 sm:px-6 pb-8 overflow-x-hidden">
                <div className="max-w-2xl mx-auto min-w-0">
                    {/* sport prop drives the API filter; topic switcher (#774) will override at runtime */}
                    {/* initialPundits pre-populated server-side — eliminates blank spinner on FCP */}
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
                    <SignUpCta />
                </div>
            </section>

            {/* ── Footer ── */}
            <footer className="border-t border-zinc-900 px-4 sm:px-6 py-8 mt-auto">
                <div className="max-w-5xl mx-auto flex flex-col items-center gap-4 text-xs text-zinc-400">
                    <span className="font-black text-sm text-emerald-500 tracking-tight uppercase">
                        Pundit Ledger
                    </span>
                    <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-2">
                        <Link href="/ledger" className="hover:text-white transition-colors">Leaderboard</Link>
                        <Link href="/pricing" className="hover:text-white transition-colors">Pricing</Link>
                        <Link href="/methodology" className="hover:text-white transition-colors">Methodology</Link>
                        <Link href="/legal/terms" className="hover:text-white transition-colors">Terms</Link>
                        <Link href="/legal/privacy" className="hover:text-white transition-colors">Privacy</Link>
                        <Link href="/legal/acceptable-use" className="hover:text-white transition-colors">Acceptable Use</Link>
                    </div>
                    <span>© {new Date().getFullYear()} Pundit Ledger. All predictions verified.</span>
                </div>
            </footer>
        </div>
    );
}
