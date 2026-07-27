import React from "react";
import { Metadata } from "next";
import Link from "next/link";
import { ArrowLeft, Phone, Heart, AlertTriangle, ExternalLink } from "lucide-react";
import { PageHeading } from "@/components/ui/heading";

export const metadata: Metadata = {
    title: "Responsible Gambling | Cap Alpha",
    description: "Responsible gambling resources, helplines, and information. If you or someone you know has a gambling problem, call 1-800-GAMBLER.",
};

const HELPLINES = [
    {
        name: "National Problem Gambling Helpline",
        number: "1-800-GAMBLER (1-800-426-2537)",
        tel: "18004262537",
        description: "24/7 confidential support — call, text, or chat",
        url: "https://www.ncpgambling.org/help-treatment/national-helpline/",
        national: true,
    },
    {
        name: "National Council on Problem Gambling (NCPG)",
        number: null,
        tel: null,
        description: "Resources, self-assessment tools, and treatment locator",
        url: "https://www.ncpgambling.org/",
        national: true,
    },
    {
        name: "Gamblers Anonymous",
        number: null,
        tel: null,
        description: "Fellowship of men and women who share experience and support",
        url: "https://www.gamblersanonymous.org/",
        national: true,
    },
    {
        name: "Substance Abuse and Mental Health Services Administration (SAMHSA)",
        number: "1-800-662-4357",
        tel: "18006624357",
        description: "National helpline for mental health and substance use disorders",
        url: "https://www.samhsa.gov/",
        national: true,
    },
];

const WARNING_SIGNS = [
    "Spending more money or time on gambling than intended",
    "Chasing losses — gambling to win back money you've lost",
    "Gambling interfering with work, relationships, or responsibilities",
    "Borrowing money or selling possessions to fund gambling",
    "Feeling restless or irritable when trying to stop gambling",
    "Lying to family or friends about gambling activity",
    "Using gambling to escape problems or relieve distress",
];

export default function ResponsibleGamblingPage() {
    return (
        <main className="min-h-[100dvh] bg-black text-white px-6 py-16">
            <div className="max-w-3xl mx-auto">
                <Link
                    href="/"
                    className="inline-flex items-center gap-2 text-sm text-zinc-500 hover:text-zinc-300 transition-colors mb-10"
                >
                    <ArrowLeft className="w-4 h-4" />
                    Back to Cap Alpha
                </Link>

                <div className="flex items-center gap-3 mb-2">
                    <Heart className="w-7 h-7 text-amber-400 shrink-0" />
                    <PageHeading>Responsible Gambling</PageHeading>
                </div>
                <p className="text-sm text-zinc-500 mb-10">Last Updated: April 29, 2026</p>

                {/* Emergency helpline — prominent placement */}
                <div className="bg-amber-950/50 border border-amber-700/50 rounded-xl p-6 mb-10">
                    <div className="flex items-start gap-3">
                        <Phone className="w-6 h-6 text-amber-400 shrink-0 mt-0.5" />
                        <div>
                            <p className="text-amber-200 font-bold text-lg leading-snug">
                                If you or someone you know has a gambling problem, call{" "}
                                <a href="tel:18004262537" className="underline hover:text-white transition-colors">
                                    1-800-GAMBLER
                                </a>
                            </p>
                            <p className="text-amber-300/70 text-sm mt-1">
                                1-800-426-2537 · Available 24/7 · Confidential
                            </p>
                        </div>
                    </div>
                </div>

                {/* Age eligibility */}
                <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5 mb-10 flex items-start gap-3">
                    <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
                    <p className="text-zinc-300 text-sm">
                        <span className="font-bold text-white">Age Requirement:</span> Must be 21 or older to participate in sports
                        betting where permitted. Void where prohibited by law. Laws governing sports betting vary by state and
                        jurisdiction — it is your responsibility to ensure compliance with local regulations.
                    </p>
                </div>

                {/* About this site */}
                <section className="mb-10">
                    <h2 className="text-xl font-bold mb-3">About This Site</h2>
                    <p className="text-zinc-400 text-sm leading-relaxed">
                        Cap Alpha is an entertainment and analytics platform that tracks sports pundits&apos; prediction
                        accuracy. This site contains affiliate links to sportsbook platforms. We are committed to responsible
                        gambling practices and require all users to be of legal gambling age in their jurisdiction.
                    </p>
                    <p className="text-zinc-400 text-sm leading-relaxed mt-3">
                        Gambling should be entertaining, not a way to make money or escape personal problems. If gambling
                        stops being fun, please reach out for help.
                    </p>
                </section>

                {/* Warning signs */}
                <section className="mb-10">
                    <h2 className="text-xl font-bold mb-4">Warning Signs of Problem Gambling</h2>
                    <ul className="space-y-2">
                        {WARNING_SIGNS.map((sign, i) => (
                            <li key={i} className="flex items-start gap-2 text-zinc-400 text-sm">
                                <span className="text-amber-500 mt-1 shrink-0">•</span>
                                {sign}
                            </li>
                        ))}
                    </ul>
                </section>

                {/* Helplines & resources */}
                <section className="mb-10">
                    <h2 className="text-xl font-bold mb-4">Helplines &amp; Resources</h2>
                    <div className="space-y-4">
                        {HELPLINES.map((resource, i) => (
                            <div key={i} className="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
                                <div className="flex items-start justify-between gap-2">
                                    <div>
                                        <p className="font-semibold text-white text-sm">{resource.name}</p>
                                        {resource.number && (
                                            <a
                                                href={`tel:${resource.tel}`}
                                                className="text-amber-400 font-mono text-sm hover:text-amber-200 transition-colors"
                                            >
                                                {resource.number}
                                            </a>
                                        )}
                                        <p className="text-zinc-500 text-xs mt-1">{resource.description}</p>
                                    </div>
                                    {resource.url && (
                                        <a
                                            href={resource.url}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            className="shrink-0 text-zinc-500 hover:text-zinc-300 transition-colors"
                                            aria-label={`Visit ${resource.name} website`}
                                        >
                                            <ExternalLink className="w-4 h-4" />
                                        </a>
                                    )}
                                </div>
                            </div>
                        ))}
                    </div>
                </section>

                {/* Self-exclusion */}
                <section className="mb-10">
                    <h2 className="text-xl font-bold mb-3">Self-Exclusion</h2>
                    <p className="text-zinc-400 text-sm leading-relaxed">
                        All licensed sportsbooks offer self-exclusion programs. If you feel you need a break from
                        gambling, contact the sportsbook directly or use your state&apos;s self-exclusion registry.
                        Most states maintain a statewide self-exclusion list that covers all licensed operators in that
                        state.
                    </p>
                </section>

                {/* Affiliate disclosure */}
                <section className="mb-10 bg-zinc-900 border border-zinc-800 rounded-xl p-5">
                    <h2 className="text-lg font-bold mb-2">Affiliate Disclosure</h2>
                    <p className="text-zinc-400 text-sm leading-relaxed">
                        Cap Alpha may earn commissions through affiliate links to sportsbook platforms. These
                        partnerships do not influence our editorial content or prediction accuracy scoring. We only link
                        to regulated, licensed operators. All affiliate partners require that we display responsible
                        gambling messaging and maintain compliance with their program terms.
                    </p>
                </section>

                <div className="flex flex-wrap gap-3 text-xs text-zinc-600">
                    <Link href="/legal/terms" className="hover:text-zinc-400 transition-colors">Terms of Service</Link>
                    <span>·</span>
                    <Link href="/legal/privacy" className="hover:text-zinc-400 transition-colors">Privacy Policy</Link>
                    <span>·</span>
                    <Link href="/legal/acceptable-use" className="hover:text-zinc-400 transition-colors">Acceptable Use</Link>
                </div>
            </div>
        </main>
    );
}
