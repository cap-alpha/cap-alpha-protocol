import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
    title: "Terms of Service | Pundit Ledger",
    description: "Terms of Service for the Pundit Ledger prediction tracking platform.",
};

export default function TermsOfService() {
    return (
        <div className="bg-black text-white min-h-[100dvh]">
            <article className="max-w-3xl mx-auto px-6 py-20 space-y-10">
                <header className="space-y-3 border-b border-zinc-800 pb-8">
                    <h1 className="text-4xl font-black tracking-tight">Terms of Service</h1>
                    <p className="text-sm text-zinc-500">Effective: [DATE]</p>
                </header>

                <section className="space-y-4 text-zinc-300 leading-relaxed">
                    <p>
                        These Terms of Service (&quot;Terms&quot;) govern your access to and use of the
                        Pundit Ledger platform (&quot;Service&quot;), operated by Cap Alpha Protocol LLC
                        (&quot;we,&quot; &quot;us,&quot; or &quot;our&quot;), a Washington state limited liability company. By creating an account or
                        using the Service, you agree to be bound by these Terms. If you do not agree,
                        do not use the Service.
                    </p>
                </section>

                {/* 1. Service Description */}
                <section className="space-y-3">
                    <h2 className="text-xl font-bold text-white">1. Service Description</h2>
                    <p className="text-zinc-300 leading-relaxed">
                        Pundit Ledger is a sports prediction accountability platform. We track
                        predictions made publicly by sports media personalities, score their accuracy
                        using algorithmic methods, and present the results through a cryptographically
                        sealed ledger. The Service is designed to promote transparency and
                        accountability in sports media commentary.
                    </p>
                </section>

                {/* 2. Accounts */}
                <section className="space-y-3">
                    <h2 className="text-xl font-bold text-white">2. Accounts</h2>
                    <p className="text-zinc-300 leading-relaxed">
                        You must create an account to access certain features. Authentication is
                        provided through Clerk, our third-party authentication provider. You are
                        responsible for maintaining the security of your account credentials.
                    </p>
                    <p className="text-zinc-300 leading-relaxed">
                        Each individual may maintain only one account. Creating multiple accounts to
                        circumvent tier limitations, rate limits, or enforcement actions is prohibited
                        and may result in termination of all associated accounts.
                    </p>
                </section>

                {/* 3. Subscription Tiers and Billing */}
                <section className="space-y-3">
                    <h2 className="text-xl font-bold text-white">3. Subscription Tiers and Billing</h2>
                    <p className="text-zinc-300 leading-relaxed">
                        The Service is available across several tiers:
                    </p>
                    <ul className="list-disc list-inside space-y-2 text-zinc-300 pl-2">
                        <li>
                            <strong className="text-white">Free</strong> &mdash; Basic access to the
                            pundit leaderboard and top-line accuracy scores. No payment required.
                        </li>
                        <li>
                            <strong className="text-white">Pro ($10&ndash;20/month)</strong> &mdash;
                            Full Pundit Credit Scores, complete prediction history, magnitude tracking,
                            and data export.
                        </li>
                        <li>
                            <strong className="text-white">Agent ($199&ndash;299/month)</strong> &mdash;
                            Programmatic access for single-developer, personal use. This tier is
                            licensed to one individual and may not be resold, sublicensed, or shared.
                        </li>
                        <li>
                            <strong className="text-white">API ($99&ndash;499/month)</strong> &mdash;
                            REST API access for commercial applications, subject to published rate
                            limits. Commercial use is permitted within the bounds of
                            your <Link href="/legal/acceptable-use" className="text-emerald-400 hover:text-emerald-300 underline underline-offset-2">Acceptable Use Policy</Link> obligations.
                        </li>
                        <li>
                            <strong className="text-white">Enterprise</strong> &mdash; Custom pricing,
                            volume licensing, and dedicated support. Contact us for details.
                        </li>
                    </ul>
                    <p className="text-zinc-300 leading-relaxed">
                        Paid subscriptions are billed monthly through Stripe, our payment processor.
                        Subscriptions renew automatically at the start of each billing cycle unless
                        canceled beforehand. You may cancel your subscription at any time, and
                        cancellation takes effect at the end of the current billing period.
                    </p>
                    <p className="text-zinc-300 leading-relaxed">
                        <strong className="text-white">Refund policy:</strong> We do not issue refunds
                        for partial billing periods. If you cancel mid-cycle, you will retain access
                        to your paid tier through the remainder of the period you have already paid for.
                    </p>
                </section>

                {/* 4. Intellectual Property */}
                <section className="space-y-3">
                    <h2 className="text-xl font-bold text-white">4. Intellectual Property</h2>
                    <p className="text-zinc-300 leading-relaxed">
                        All Pundit Credit Scores, accuracy metrics, scoring methodologies, data
                        compilations, and platform content are the intellectual property of Pundit
                        Ledger. Your subscription grants you a limited, non-exclusive,
                        non-transferable license to access and use this data for the purposes
                        permitted by your tier.
                    </p>
                    <p className="text-zinc-300 leading-relaxed">
                        You may not scrape, bulk download, redistribute, or commercially syndicate
                        data from the Service except as expressly permitted by the API or Enterprise
                        tiers. The scoring algorithm and its underlying methodology are proprietary
                        and may not be reverse-engineered.
                    </p>
                </section>

                {/* 5. Data Accuracy and Disclaimers */}
                <section className="space-y-3">
                    <h2 className="text-xl font-bold text-white">5. Data Accuracy and Disclaimers</h2>
                    <p className="text-zinc-300 leading-relaxed">
                        Pundit Credit Scores and all associated metrics are computed algorithmically
                        based on publicly available information. While we strive for accuracy, we do
                        not guarantee that scores, predictions, or resolutions are error-free. Data
                        may be delayed, incomplete, or subject to revision.
                    </p>
                    <p className="text-zinc-300 leading-relaxed font-semibold text-white">
                        The Service does not constitute financial advice, investment advice, or
                        gambling advice. We track prediction accuracy &mdash; we do not recommend
                        bets, trades, or any other financial decisions. You should not rely on
                        Pundit Ledger data when making wagering or investment decisions.
                    </p>
                </section>

                {/* 6. Limitation of Liability */}
                <section className="space-y-3">
                    <h2 className="text-xl font-bold text-white">6. Limitation of Liability</h2>
                    <p className="text-zinc-300 leading-relaxed">
                        TO THE MAXIMUM EXTENT PERMITTED BY LAW, PUNDIT LEDGER AND ITS OPERATORS,
                        DEVELOPERS, AND AFFILIATED ENTITIES SHALL NOT BE LIABLE FOR ANY INDIRECT,
                        INCIDENTAL, SPECIAL, CONSEQUENTIAL, OR PUNITIVE DAMAGES, OR ANY LOSS OF
                        PROFITS OR REVENUE, WHETHER INCURRED DIRECTLY OR INDIRECTLY, ARISING FROM
                        YOUR USE OF THE SERVICE.
                    </p>
                    <p className="text-zinc-300 leading-relaxed">
                        Our total aggregate liability for any claims arising from or related to the
                        Service shall not exceed the amount you paid us in the twelve (12) months
                        preceding the claim.
                    </p>
                </section>

                {/* 7. Acceptable Use and Termination */}
                <section className="space-y-3">
                    <h2 className="text-xl font-bold text-white">7. Acceptable Use and Termination</h2>
                    <p className="text-zinc-300 leading-relaxed">
                        Your use of the Service is subject to
                        our <Link href="/legal/acceptable-use" className="text-emerald-400 hover:text-emerald-300 underline underline-offset-2">Acceptable Use Policy</Link>,
                        which is incorporated into these Terms by reference.
                    </p>
                    <p className="text-zinc-300 leading-relaxed">
                        We reserve the right to suspend or terminate your account at any time for
                        violations of these Terms or the Acceptable Use Policy. In cases of
                        termination for cause, no refund will be issued for the remaining billing
                        period. We may also terminate accounts that remain inactive for an extended
                        period, with reasonable advance notice.
                    </p>
                </section>

                {/* 8. Governing Law */}
                <section className="space-y-3">
                    <h2 className="text-xl font-bold text-white">8. Governing Law</h2>
                    <p className="text-zinc-300 leading-relaxed">
                        These Terms shall be governed by and construed in accordance with the laws of the
                        State of Washington, without regard to its conflict of law provisions. Any disputes
                        arising from or relating to these Terms or the Service shall be resolved exclusively
                        in the state or federal courts located in King County, Washington.
                    </p>
                </section>

                {/* 9. Changes to These Terms */}
                <section className="space-y-3">
                    <h2 className="text-xl font-bold text-white">9. Changes to These Terms</h2>
                    <p className="text-zinc-300 leading-relaxed">
                        We may update these Terms from time to time. When we make material changes,
                        we will notify you by email or through the Service. Your continued use of the
                        Service after such notice constitutes acceptance of the updated Terms.
                    </p>
                </section>

                {/* 10. Contact */}
                <section className="space-y-3">
                    <h2 className="text-xl font-bold text-white">10. Contact</h2>
                    <p className="text-zinc-300 leading-relaxed">
                        If you have questions about these Terms, contact us
                        at{" "}
                        <a href="mailto:support@cap-alpha.co" className="text-emerald-400 hover:text-emerald-300 underline underline-offset-2">
                            support@cap-alpha.co
                        </a>.
                    </p>
                </section>

                {/* Related policies */}
                <footer className="border-t border-zinc-800 pt-8 text-sm text-zinc-500">
                    <p>See also:</p>
                    <ul className="mt-2 space-y-1">
                        <li>
                            <Link href="/legal/privacy" className="text-emerald-400 hover:text-emerald-300 underline underline-offset-2">Privacy Policy</Link>
                        </li>
                        <li>
                            <Link href="/legal/acceptable-use" className="text-emerald-400 hover:text-emerald-300 underline underline-offset-2">Acceptable Use Policy</Link>
                        </li>
                    </ul>
                </footer>
            </article>
        </div>
    );
}
