import Link from "next/link";
import { WaitlistForm } from "@/components/waitlist-form";
import { SignUpCta } from "@/components/sign-up-cta";
import { PunditLeaderboardPreview } from "@/components/pundit-leaderboard-preview";

export const revalidate = 300; // 5-minute ISR

export default function LandingPage() {
    return (
        <div className="bg-black text-white min-h-[100dvh] flex flex-col font-sans">
            {/* ── Hero ── */}
            <section className="relative flex flex-col items-center justify-center text-center px-6 pt-20 pb-10 overflow-hidden">
                {/* Background glow */}
                <div className="absolute inset-0 pointer-events-none">
                    <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[700px] h-[320px] bg-emerald-500/8 rounded-full blur-[120px]" />
                </div>

                <div className="relative z-10 max-w-2xl mx-auto space-y-4">
                    {/* Live indicator */}
                    <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-emerald-500/30 bg-emerald-500/10 text-emerald-400 text-xs font-mono font-medium uppercase tracking-widest">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                        Live Edge Report
                    </div>

                    {/* Hero headline — 2 lines max */}
                    <h1 className="font-display font-black text-4xl sm:text-5xl lg:text-6xl tracking-tight leading-tight text-white">
                        The most accurate sports pundits, ranked.
                    </h1>
                    <p className="text-lg text-zinc-400 leading-snug">
                        Every prediction tracked, scored, and sealed.
                    </p>

                    {/* Single CTA */}
                    <div className="pt-2">
                        <Link
                            href="/ledger"
                            className="inline-flex items-center gap-2 px-7 py-3.5 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-black font-bold text-base transition-colors shadow-[0_0_24px_rgba(16,185,129,0.3)] hover:shadow-[0_0_32px_rgba(16,185,129,0.5)]"
                        >
                            See the full ledger →
                        </Link>
                    </div>
                </div>
            </section>

            {/* ── Live Leaderboard Preview ── (immediately below hero, no scroll on desktop) */}
            <section className="w-full px-6 pb-16">
                <div className="max-w-2xl mx-auto">
                    {/* sport prop drives the API filter; topic switcher (#774) will override at runtime */}
                    <PunditLeaderboardPreview sport="NFL" />
                </div>
            </section>

            {/* ── Waitlist ── (stays per product milestone gating) */}
            <section className="w-full px-6 py-16 border-t border-zinc-900">
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
            <footer className="border-t border-zinc-900 px-6 py-8 mt-auto">
                <div className="max-w-5xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-zinc-400">
                    <span className="font-black text-sm text-emerald-500 tracking-tight uppercase">
                        Pundit Ledger
                    </span>
                    <div className="flex items-center gap-6">
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
