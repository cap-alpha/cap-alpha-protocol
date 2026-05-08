import React from "react";
import { Metadata } from "next";
import Link from "next/link";
import { ArrowLeft, DollarSign, BarChart2 } from "lucide-react";

export const metadata: Metadata = {
    title: "Affiliate Disclosure | Cap Alpha",
    description: "FTC-compliant affiliate disclosure for Cap Alpha / Cap Alpha.",
};

export default function DisclosurePage() {
    return (
        <main className="min-h-[100dvh] bg-black text-white px-6 py-16">
            <div className="max-w-3xl mx-auto">
                <Link
                    href="/"
                    className="inline-flex items-center gap-2 text-sm text-zinc-500 hover:text-zinc-300 transition-colors mb-10"
                >
                    <ArrowLeft className="w-4 h-4" />
                    Back to home
                </Link>

                <div className="flex items-center gap-3 mb-4">
                    <DollarSign className="w-7 h-7 text-emerald-500" />
                    <h1 className="font-display text-3xl font-extrabold tracking-tight">Affiliate Disclosure</h1>
                </div>
                <p className="text-zinc-500 text-sm mb-10">Last Updated: May 7, 2026</p>

                <div className="space-y-8 text-zinc-300 leading-relaxed">
                    <section className="border border-zinc-800 rounded-lg p-6 bg-zinc-950">
                        <div className="flex items-center gap-2 mb-3">
                            <BarChart2 className="w-5 h-5 text-emerald-500" />
                            <h2 className="text-xl font-bold text-white">Prediction Scoring — Not Betting Advice</h2>
                        </div>
                        <ul className="space-y-3 text-zinc-300">
                            <li>
                                Cap Alpha is not a sportsbook, sports betting operator, or gambling service.
                            </li>
                            <li>
                                The Pundit Prediction Ledger scores the historical accuracy of <strong className="text-white">public statements</strong> made
                                by sports media personalities. Scores are computed from past, resolved events using
                                publicly available sports data.
                            </li>
                            <li>
                                Nothing on this site constitutes a betting recommendation, gambling tip, odds
                                advisory, or financial advice of any kind.
                            </li>
                            <li>
                                Accuracy scores reflect historical performance only. Past prediction accuracy does
                                not guarantee future results.
                            </li>
                            <li>
                                Cap Alpha does not display live betting odds, point spreads, or bookmaker lines.
                            </li>
                            <li>
                                Pundits scored on this site are public figures making public statements. Each scored
                                claim is attributed to its original source URL.
                            </li>
                        </ul>
                        <p className="mt-4 text-sm text-zinc-400">
                            For information on how errors in scored predictions are handled, see our{' '}
                            <Link href="/legal/corrections" className="text-emerald-500 underline hover:text-emerald-400">
                                Corrections Policy
                            </Link>.
                        </p>
                    </section>

                    <section>
                        <h2 className="text-xl font-bold text-white mb-3">FTC Disclosure</h2>
                        <p>
                            In accordance with the Federal Trade Commission&apos;s guidelines on endorsements and
                            testimonials (<a href="https://www.ftc.gov/business-guidance/resources/ftc-endorsement-guides-what-people-are-asking" target="_blank" rel="noopener noreferrer" className="text-emerald-500 underline hover:text-emerald-400">16 CFR Part 255</a>),
                            Cap Alpha / Cap Alpha discloses the following: this site contains affiliate links.
                        </p>
                    </section>

                    <section>
                        <h2 className="text-xl font-bold text-white mb-3">What Are Affiliate Links?</h2>
                        <p>
                            Some links on this site are affiliate links, meaning Cap Alpha may earn a commission
                            if you click through and sign up or make a purchase — at no additional cost to you.
                            These partnerships help us keep the service running and free to use.
                        </p>
                    </section>

                    <section>
                        <h2 className="text-xl font-bold text-white mb-3">Which Partners?</h2>
                        <p className="mb-3">
                            We currently have or may have affiliate relationships with the following sportsbook
                            and daily-fantasy operators:
                        </p>
                        <ul className="list-disc list-inside space-y-1 text-zinc-400 ml-2">
                            <li>DraftKings</li>
                            <li>FanDuel</li>
                            <li>PrizePicks</li>
                            <li>Underdog Fantasy</li>
                        </ul>
                        <p className="mt-3 text-zinc-400 text-sm">
                            This list may not be exhaustive. Any link labeled &quot;affiliate link&quot; or accompanied
                            by an affiliate disclosure badge earns us a commission.
                        </p>
                    </section>

                    <section>
                        <h2 className="text-xl font-bold text-white mb-3">Our Editorial Independence</h2>
                        <p>
                            Affiliate relationships do not influence our analysis, predictions, or editorial
                            content. We do not accept payment in exchange for favorable coverage of any
                            sportsbook or fantasy platform. All opinions are our own.
                        </p>
                    </section>

                    <section>
                        <h2 className="text-xl font-bold text-white mb-3">Responsible Gambling</h2>
                        <p>
                            Sports betting and daily-fantasy contests involve risk and are not suitable for
                            everyone. Never wager more than you can afford to lose. If you or someone you
                            know has a gambling problem, call the National Problem Gambling Helpline at{' '}
                            <span className="text-white font-semibold">1-800-522-4700</span>.
                        </p>
                    </section>

                    <section>
                        <h2 className="text-xl font-bold text-white mb-3">Questions?</h2>
                        <p>
                            If you have any questions about this disclosure, please contact us. You can also
                            review our{' '}
                            <Link href="/legal/privacy" className="text-emerald-500 underline hover:text-emerald-400">
                                Privacy Policy
                            </Link>{' '}
                            and{' '}
                            <Link href="/legal/terms" className="text-emerald-500 underline hover:text-emerald-400">
                                Terms of Service
                            </Link>.
                        </p>
                    </section>
                </div>
            </div>
        </main>
    );
}
