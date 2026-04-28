import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
    title: "Acceptable Use Policy | Pundit Ledger",
    description: "Acceptable Use Policy for the Pundit Ledger prediction tracking platform.",
};

export default function AcceptableUsePolicy() {
    return (
        <div className="bg-black text-white min-h-[100dvh]">
            <article className="max-w-3xl mx-auto px-6 py-20 space-y-10">
                <header className="space-y-3 border-b border-zinc-800 pb-8">
                    <h1 className="text-4xl font-black tracking-tight">Acceptable Use Policy</h1>
                    <p className="text-sm text-zinc-500">Effective: [DATE]</p>
                </header>

                <section className="space-y-4 text-zinc-300 leading-relaxed">
                    <p>
                        This Acceptable Use Policy (&quot;AUP&quot;) defines the boundaries of
                        permitted behavior on the Pundit Ledger platform (&quot;Service&quot;). It
                        applies to all users regardless of subscription tier. Violations may result
                        in enforcement action up to and including permanent termination of your
                        account.
                    </p>
                </section>

                {/* 1. Data Access and Scraping */}
                <section className="space-y-3">
                    <h2 className="text-xl font-bold text-white">1. Data Access and Scraping</h2>
                    <p className="text-zinc-300 leading-relaxed">
                        You may not scrape, crawl, or bulk download data from the Service beyond the
                        access permitted by your subscription tier. Automated access is available only
                        through the API tier and above, and is subject to published rate limits.
                    </p>
                    <p className="text-zinc-300 leading-relaxed">
                        Free and Pro tier users may not use automated tools, scripts, or bots to
                        extract data from the platform. If you need programmatic access, upgrade to
                        an API or Enterprise tier.
                    </p>
                </section>

                {/* 2. Reselling and Redistribution */}
                <section className="space-y-3">
                    <h2 className="text-xl font-bold text-white">2. Reselling and Redistribution</h2>
                    <p className="text-zinc-300 leading-relaxed">
                        Data obtained through the Free or Pro tiers is licensed for personal,
                        non-commercial use only. You may not resell, sublicense, or redistribute
                        Pundit Ledger data, scores, or derived insights from these tiers.
                    </p>
                    <p className="text-zinc-300 leading-relaxed">
                        API tier users may incorporate Pundit Ledger data into commercial applications,
                        subject to the terms of their subscription and applicable rate limits.
                        Enterprise agreements may grant broader redistribution rights.
                    </p>
                </section>

                {/* 3. Agent Tier Restrictions */}
                <section className="space-y-3">
                    <h2 className="text-xl font-bold text-white">3. Agent Tier Restrictions</h2>
                    <p className="text-zinc-300 leading-relaxed">
                        The Agent tier is licensed for single-developer, personal use only. It is
                        intended for individual developers building personal projects or prototypes.
                        You may not:
                    </p>
                    <ul className="list-disc list-inside space-y-2 text-zinc-300 pl-2">
                        <li>Share Agent tier credentials with others</li>
                        <li>Use the Agent tier to power a multi-user application</li>
                        <li>Resell or sublicense access obtained through the Agent tier</li>
                    </ul>
                    <p className="text-zinc-300 leading-relaxed">
                        If your use case involves serving multiple end users or commercial
                        distribution, you must use the API or Enterprise tier.
                    </p>
                </section>

                {/* 4. Conduct Toward Tracked Pundits */}
                <section className="space-y-3">
                    <h2 className="text-xl font-bold text-white">4. Conduct Toward Tracked Pundits</h2>
                    <p className="text-zinc-300 leading-relaxed">
                        Pundit Ledger exists to promote accountability in sports media through
                        objective, data-driven scoring. It is not a vehicle for personal attacks. You
                        may not use the Service or its data to:
                    </p>
                    <ul className="list-disc list-inside space-y-2 text-zinc-300 pl-2">
                        <li>Harass, threaten, or stalk any tracked pundit or other individual</li>
                        <li>Defame or make knowingly false statements about a tracked pundit</li>
                        <li>
                            Organize or coordinate targeted harassment campaigns using data from
                            the Service
                        </li>
                    </ul>
                    <p className="text-zinc-300 leading-relaxed">
                        Critique of prediction accuracy is encouraged. Personal attacks are not.
                    </p>
                </section>

                {/* 5. Score and Data Integrity */}
                <section className="space-y-3">
                    <h2 className="text-xl font-bold text-white">5. Score and Data Integrity</h2>
                    <p className="text-zinc-300 leading-relaxed">
                        You may not attempt to manipulate Pundit Credit Scores or the integrity of the
                        prediction ledger. This includes, but is not limited to:
                    </p>
                    <ul className="list-disc list-inside space-y-2 text-zinc-300 pl-2">
                        <li>Submitting fraudulent or bad-faith dispute flags</li>
                        <li>Attempting to inject false predictions into the system</li>
                        <li>Coordinating with others to artificially inflate or deflate scores</li>
                    </ul>
                </section>

                {/* 6. Reverse Engineering */}
                <section className="space-y-3">
                    <h2 className="text-xl font-bold text-white">6. Reverse Engineering</h2>
                    <p className="text-zinc-300 leading-relaxed">
                        You may not reverse engineer, decompile, or disassemble the scoring algorithm,
                        cryptographic verification system, or any other proprietary component of the
                        Service. You may not attempt to reconstruct our methodology by systematically
                        probing the API with synthetic inputs.
                    </p>
                </section>

                {/* 7. Rate Limits */}
                <section className="space-y-3">
                    <h2 className="text-xl font-bold text-white">7. Rate Limits</h2>
                    <p className="text-zinc-300 leading-relaxed">
                        All API access is subject to rate limits published in our API documentation.
                        You must respect these limits and implement appropriate backoff strategies in
                        your integrations. Intentionally exceeding rate limits or using multiple
                        accounts to circumvent them is a violation of this policy.
                    </p>
                </section>

                {/* 8. Enforcement */}
                <section className="space-y-3">
                    <h2 className="text-xl font-bold text-white">8. Enforcement</h2>
                    <p className="text-zinc-300 leading-relaxed">
                        We enforce this policy through a graduated process:
                    </p>
                    <ol className="list-decimal list-inside space-y-2 text-zinc-300 pl-2">
                        <li>
                            <strong className="text-white">Warning</strong> &mdash; For first-time or
                            minor violations, we will notify you and request corrective action.
                        </li>
                        <li>
                            <strong className="text-white">Suspension</strong> &mdash; For repeated or
                            more serious violations, we may temporarily suspend your account and API
                            access.
                        </li>
                        <li>
                            <strong className="text-white">Termination</strong> &mdash; For severe or
                            persistent violations, we may permanently terminate your account without
                            refund.
                        </li>
                    </ol>
                    <p className="text-zinc-300 leading-relaxed">
                        We reserve the right to skip steps in this process for egregious violations,
                        including but not limited to harassment, data theft, or attempts to compromise
                        the integrity of the scoring system.
                    </p>
                </section>

                {/* 9. Reporting Violations */}
                <section className="space-y-3">
                    <h2 className="text-xl font-bold text-white">9. Reporting Violations</h2>
                    <p className="text-zinc-300 leading-relaxed">
                        If you believe someone is violating this policy, please report it
                        to{" "}
                        <a href="mailto:support@cap-alpha.co" className="text-emerald-400 hover:text-emerald-300 underline underline-offset-2">
                            support@cap-alpha.co
                        </a>.
                        We review all reports and take appropriate action.
                    </p>
                </section>

                {/* Related policies */}
                <footer className="border-t border-zinc-800 pt-8 text-sm text-zinc-500">
                    <p>See also:</p>
                    <ul className="mt-2 space-y-1">
                        <li>
                            <Link href="/legal/terms" className="text-emerald-400 hover:text-emerald-300 underline underline-offset-2">Terms of Service</Link>
                        </li>
                        <li>
                            <Link href="/legal/privacy" className="text-emerald-400 hover:text-emerald-300 underline underline-offset-2">Privacy Policy</Link>
                        </li>
                    </ul>
                </footer>
            </article>
        </div>
    );
}
