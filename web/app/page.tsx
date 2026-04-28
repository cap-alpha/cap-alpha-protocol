import Link from "next/link";
import { Shield, TrendingUp, BarChart3, Lock, ArrowRight, Zap } from "lucide-react";
import { WaitlistForm } from "@/components/waitlist-form";
import { PunditLeaderboardPreview } from "@/components/pundit-leaderboard-preview";
import { UpgradeButton } from "@/components/upgrade-button";

export const revalidate = 300; // 5-minute ISR

export default function LandingPage() {
    return (
        <div className="bg-black text-white min-h-[100dvh] flex flex-col font-sans">
            {/* Hero */}
            <section className="relative flex flex-col items-center justify-center text-center px-6 pt-24 pb-20 overflow-hidden">
                {/* Background glow */}
                <div className="absolute inset-0 pointer-events-none">
                    <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[800px] h-[400px] bg-emerald-500/8 rounded-full blur-[120px]" />
                </div>

                <div className="relative z-10 max-w-3xl mx-auto space-y-6">
                    <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-emerald-500/30 bg-emerald-500/10 text-emerald-400 text-xs font-mono font-medium uppercase tracking-widest">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                        Cryptographically Verified
                    </div>

                    <h1 className="text-5xl sm:text-6xl font-black tracking-tight leading-[1.05]">
                        Hold Pundits{" "}
                        <span className="text-emerald-400">Accountable.</span>
                    </h1>

                    <p className="text-xl text-zinc-400 max-w-xl mx-auto leading-relaxed">
                        Every sports prediction. Tracked, scored, and cryptographically
                        sealed — so no one can rewrite history.
                    </p>

                    <div className="flex flex-col items-center gap-4 pt-2">
                        <WaitlistForm />
                        <p className="text-xs text-zinc-600">
                            Free tier available at launch. No credit card required.
                        </p>
                    </div>
                </div>
            </section>

            {/* Live leaderboard preview */}
            <section className="w-full px-6 pb-20">
                <div className="max-w-5xl mx-auto">
                    <div className="flex items-center justify-between mb-6">
                        <div>
                            <h2 className="text-lg font-bold text-white">Pundit Leaderboard</h2>
                            <p className="text-sm text-zinc-500">Live accuracy scores across all tracked predictions</p>
                        </div>
                        <Link
                            href="/ledger"
                            className="flex items-center gap-1.5 text-sm text-emerald-400 hover:text-emerald-300 transition-colors font-medium"
                        >
                            Full ledger <ArrowRight className="w-3.5 h-3.5" />
                        </Link>
                    </div>
                    <PunditLeaderboardPreview />
                </div>
            </section>

            {/* How it works */}
            <section className="w-full px-6 py-20 border-t border-zinc-900">
                <div className="max-w-5xl mx-auto">
                    <h2 className="text-2xl font-bold text-center mb-12">How it works</h2>
                    <div className="grid sm:grid-cols-3 gap-8">
                        <div className="space-y-3">
                            <div className="w-10 h-10 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center">
                                <Zap className="w-5 h-5 text-emerald-400" />
                            </div>
                            <h3 className="font-semibold text-white">We ingest the takes</h3>
                            <p className="text-sm text-zinc-400 leading-relaxed">
                                Our pipeline monitors X, podcasts, and sports media daily — extracting
                                every verifiable prediction with a structured claim.
                            </p>
                        </div>
                        <div className="space-y-3">
                            <div className="w-10 h-10 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center">
                                <BarChart3 className="w-5 h-5 text-emerald-400" />
                            </div>
                            <h3 className="font-semibold text-white">We score the results</h3>
                            <p className="text-sm text-zinc-400 leading-relaxed">
                                Predictions are resolved against official outcomes. The Pundit Credit
                                Score weights accuracy, magnitude of misses, and prediction volume.{" "}
                                <Link href="/methodology" className="text-emerald-400 hover:text-emerald-300 transition-colors">
                                    Read the methodology &rarr;
                                </Link>
                            </p>
                        </div>
                        <div className="space-y-3">
                            <div className="w-10 h-10 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center">
                                <Lock className="w-5 h-5 text-emerald-400" />
                            </div>
                            <h3 className="font-semibold text-white">The ledger is sealed</h3>
                            <p className="text-sm text-zinc-400 leading-relaxed">
                                Each prediction gets a cryptographic hash at ingest. No
                                one — not even us — can alter the record after the fact.
                            </p>
                        </div>
                    </div>
                </div>
            </section>

            {/* Tier CTA */}
            <section className="w-full px-6 py-20 border-t border-zinc-900">
                <div className="max-w-5xl mx-auto grid sm:grid-cols-2 gap-6">
                    {/* Free */}
                    <div className="rounded-2xl border border-zinc-800 bg-zinc-900/50 p-8 space-y-4">
                        <div className="flex items-center justify-between">
                            <span className="text-sm font-mono uppercase tracking-widest text-zinc-500">Free</span>
                            <span className="text-2xl font-black text-white">$0</span>
                        </div>
                        <ul className="space-y-2 text-sm text-zinc-400">
                            <li className="flex items-center gap-2">
                                <span className="text-emerald-400">✓</span> Pundit leaderboard
                            </li>
                            <li className="flex items-center gap-2">
                                <span className="text-emerald-400">✓</span> Top-line accuracy scores
                            </li>
                            <li className="flex items-center gap-2">
                                <span className="text-emerald-400">✓</span> Current season predictions
                            </li>
                            <li className="flex items-center gap-2">
                                <span className="text-emerald-400">✓</span> Shareable pundit cards
                            </li>
                        </ul>
                        <Link
                            href="/ledger"
                            className="block text-center py-2.5 rounded-lg border border-zinc-700 text-sm font-medium text-zinc-300 hover:border-zinc-500 hover:text-white transition-colors"
                        >
                            View Leaderboard
                        </Link>
                    </div>

                    {/* Pro */}
                    <div className="rounded-2xl border border-emerald-500/30 bg-emerald-500/5 p-8 space-y-4 relative">
                        <div className="flex items-center justify-between">
                            <span className="text-sm font-mono uppercase tracking-widest text-emerald-400">Pro</span>
                            <div className="text-right">
                                <span className="text-2xl font-black text-white">$14.99</span>
                                <span className="text-zinc-500 text-sm">/mo</span>
                            </div>
                        </div>
                        <ul className="space-y-2 text-sm text-zinc-400">
                            <li className="flex items-center gap-2">
                                <span className="text-emerald-400">✓</span> Full 6-axis Pundit Credit Score
                            </li>
                            <li className="flex items-center gap-2">
                                <span className="text-emerald-400">✓</span> Complete prediction history
                            </li>
                            <li className="flex items-center gap-2">
                                <span className="text-emerald-400">✓</span> Magnitude tracking (how wrong)
                            </li>
                            <li className="flex items-center gap-2">
                                <span className="text-emerald-400">✓</span> Multi-sport coverage
                            </li>
                            <li className="flex items-center gap-2">
                                <span className="text-emerald-400">✓</span> Bulk CSV export
                            </li>
                        </ul>
                        <UpgradeButton plan="pro" />
                    </div>
                </div>
            </section>

            {/* API CTA */}
            <section className="w-full px-6 py-16 border-t border-zinc-900">
                <div className="max-w-5xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-6">
                    <div className="space-y-1">
                        <div className="flex items-center gap-2 text-sm font-mono text-zinc-500">
                            <Shield className="w-4 h-4" />
                            API Access
                        </div>
                        <h3 className="text-xl font-bold text-white">Building something? Use our data.</h3>
                        <p className="text-zinc-400 text-sm">
                            REST API with per-pundit scores, prediction history, and resolution data.
                            Starting at $99/mo.
                        </p>
                    </div>
                    <Link
                        href="/ledger"
                        className="shrink-0 flex items-center gap-2 px-6 py-3 rounded-lg bg-zinc-800 border border-zinc-700 text-sm font-semibold text-white hover:border-zinc-500 transition-colors"
                    >
                        <TrendingUp className="w-4 h-4" />
                        Explore the ledger
                    </Link>
                </div>
            </section>

            {/* Footer */}
            <footer className="border-t border-zinc-900 px-6 py-8 mt-auto">
                <div className="max-w-5xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-zinc-600">
                    <span className="font-black text-sm text-emerald-500 tracking-tight uppercase">
                        Pundit Ledger
                    </span>
                    <div className="flex items-center gap-6">
                        <Link href="/ledger" className="hover:text-zinc-400 transition-colors">Leaderboard</Link>
                        <Link href="/pricing" className="hover:text-zinc-400 transition-colors">Pricing</Link>
                        <Link href="/methodology" className="hover:text-zinc-400 transition-colors">Methodology</Link>
                        <Link href="/legal/terms" className="hover:text-zinc-400 transition-colors">Terms</Link>
                        <Link href="/legal/privacy" className="hover:text-zinc-400 transition-colors">Privacy</Link>
                        <Link href="/legal/acceptable-use" className="hover:text-zinc-400 transition-colors">Acceptable Use</Link>
                    </div>
                    <span>© {new Date().getFullYear()} Pundit Ledger. All predictions verified.</span>
                </div>
            </footer>
        </div>
    );
}
