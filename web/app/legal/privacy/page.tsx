import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
    title: "Privacy Policy | Pundit Ledger",
    description: "Privacy Policy for the Pundit Ledger prediction tracking platform.",
};

export default function PrivacyPolicy() {
    return (
        <div className="bg-black text-white min-h-[100dvh]">
            <article className="max-w-3xl mx-auto px-6 py-20 space-y-10">
                <header className="space-y-3 border-b border-zinc-800 pb-8">
                    <h1 className="text-4xl font-black tracking-tight">Privacy Policy</h1>
                    <p className="text-sm text-zinc-500">Effective: [DATE]</p>
                </header>

                <section className="space-y-4 text-zinc-300 leading-relaxed">
                    <p>
                        This Privacy Policy explains how Pundit Ledger (&quot;we,&quot; &quot;us,&quot;
                        or &quot;our&quot;) collects, uses, and protects your information when you use
                        our platform (&quot;Service&quot;). We are committed to handling your data
                        responsibly and transparently.
                    </p>
                </section>

                {/* 1. Information We Collect */}
                <section className="space-y-3">
                    <h2 className="text-xl font-bold text-white">1. Information We Collect</h2>

                    <h3 className="text-lg font-semibold text-zinc-200 mt-4">Account Information</h3>
                    <p className="text-zinc-300 leading-relaxed">
                        When you create an account, we collect your name and email address through
                        Clerk, our authentication provider. We use this information to identify your
                        account and communicate with you about the Service.
                    </p>

                    <h3 className="text-lg font-semibold text-zinc-200 mt-4">Payment Information</h3>
                    <p className="text-zinc-300 leading-relaxed">
                        Paid subscriptions are processed through Stripe. We do not store credit card
                        numbers, bank account details, or other sensitive payment credentials on our
                        servers. Stripe handles payment data in accordance with PCI DSS standards. We
                        retain only a transaction reference and subscription status for billing
                        purposes.
                    </p>

                    <h3 className="text-lg font-semibold text-zinc-200 mt-4">Usage Data</h3>
                    <p className="text-zinc-300 leading-relaxed">
                        We collect API request logs, page views, and feature usage data to operate the
                        Service, enforce rate limits, and meter usage for billing. This includes IP
                        addresses, request timestamps, endpoints accessed, and response codes.
                    </p>

                    <h3 className="text-lg font-semibold text-zinc-200 mt-4">What We Do Not Collect</h3>
                    <p className="text-zinc-300 leading-relaxed">
                        We do not collect your betting activity, gambling history, or financial
                        information beyond what is necessary to process your subscription payment.
                        Pundit Ledger tracks the accuracy of public sports media predictions &mdash;
                        it does not monitor or record your personal wagering behavior.
                    </p>
                </section>

                {/* 2. How We Use Your Information */}
                <section className="space-y-3">
                    <h2 className="text-xl font-bold text-white">2. How We Use Your Information</h2>
                    <p className="text-zinc-300 leading-relaxed">
                        We use the information we collect for the following purposes:
                    </p>
                    <ul className="list-disc list-inside space-y-2 text-zinc-300 pl-2">
                        <li>
                            <strong className="text-white">Service delivery</strong> &mdash;
                            Authenticating your account, delivering content based on your subscription
                            tier, and processing payments.
                        </li>
                        <li>
                            <strong className="text-white">Usage metering</strong> &mdash;
                            Tracking API calls and feature usage to enforce rate limits and calculate
                            billing for usage-based tiers.
                        </li>
                        <li>
                            <strong className="text-white">Product improvement</strong> &mdash;
                            Analyzing aggregate usage patterns to improve the Service, fix bugs, and
                            prioritize new features.
                        </li>
                        <li>
                            <strong className="text-white">Communication</strong> &mdash;
                            Sending transactional emails (billing confirmations, account changes) and,
                            if you opt in, product updates.
                        </li>
                    </ul>
                </section>

                {/* 3. Third-Party Services */}
                <section className="space-y-3">
                    <h2 className="text-xl font-bold text-white">3. Third-Party Services</h2>
                    <p className="text-zinc-300 leading-relaxed">
                        We rely on the following third-party providers to operate the Service. Each
                        processes data only as necessary to perform its function:
                    </p>
                    <ul className="list-disc list-inside space-y-2 text-zinc-300 pl-2">
                        <li>
                            <strong className="text-white">Clerk</strong> &mdash; Authentication and
                            user management.
                        </li>
                        <li>
                            <strong className="text-white">Stripe</strong> &mdash; Payment processing
                            and subscription management.
                        </li>
                        <li>
                            <strong className="text-white">Google Cloud Platform (BigQuery)</strong> &mdash;
                            Data warehouse for prediction data and scoring pipelines.
                        </li>
                        <li>
                            <strong className="text-white">Vercel</strong> &mdash; Application hosting
                            and edge delivery.
                        </li>
                        <li>
                            <strong className="text-white">Sentry</strong> &mdash; Error tracking and
                            performance monitoring.
                        </li>
                    </ul>
                    <p className="text-zinc-300 leading-relaxed">
                        We do not sell your personal information to third parties. We do not share
                        your data with advertisers.
                    </p>
                </section>

                {/* 4. Data Retention */}
                <section className="space-y-3">
                    <h2 className="text-xl font-bold text-white">4. Data Retention</h2>
                    <p className="text-zinc-300 leading-relaxed">
                        We retain your account information for as long as your account is active.
                        Usage logs are retained for billing verification and abuse prevention. If you
                        request account deletion, we will remove your personal data within 30 days,
                        except where retention is required by law or necessary to resolve disputes.
                    </p>
                </section>

                {/* 5. Cookies */}
                <section className="space-y-3">
                    <h2 className="text-xl font-bold text-white">5. Cookies</h2>
                    <p className="text-zinc-300 leading-relaxed">
                        We use minimal, essential cookies for authentication and session management.
                        We do not use advertising cookies, tracking pixels, or third-party analytics
                        cookies. The cookies we set are strictly necessary for the Service to function.
                    </p>
                </section>

                {/* 6. Your Rights */}
                <section className="space-y-3">
                    <h2 className="text-xl font-bold text-white">6. Your Rights</h2>
                    <p className="text-zinc-300 leading-relaxed">
                        Depending on your jurisdiction, you may have the following rights regarding
                        your personal data:
                    </p>
                    <ul className="list-disc list-inside space-y-2 text-zinc-300 pl-2">
                        <li>
                            <strong className="text-white">Access</strong> &mdash; Request a copy of
                            the personal data we hold about you.
                        </li>
                        <li>
                            <strong className="text-white">Deletion</strong> &mdash; Request that we
                            delete your personal data, subject to legal retention requirements.
                        </li>
                        <li>
                            <strong className="text-white">Export</strong> &mdash; Receive your data
                            in a portable, machine-readable format.
                        </li>
                        <li>
                            <strong className="text-white">Correction</strong> &mdash; Request
                            correction of inaccurate personal data.
                        </li>
                        <li>
                            <strong className="text-white">Opt out of sale</strong> &mdash; We do not
                            sell personal data, but if you are a California resident under the CCPA,
                            you have the right to confirm this.
                        </li>
                    </ul>
                    <p className="text-zinc-300 leading-relaxed">
                        To exercise any of these rights, contact us
                        at{" "}
                        <a href="mailto:legal@capalpha.com" className="text-emerald-400 hover:text-emerald-300 underline underline-offset-2">
                            legal@capalpha.com
                        </a>.
                        We will respond within 30 days.
                    </p>
                </section>

                {/* 7. Children's Privacy */}
                <section className="space-y-3">
                    <h2 className="text-xl font-bold text-white">7. Children&apos;s Privacy</h2>
                    <p className="text-zinc-300 leading-relaxed">
                        The Service is not directed to children under 13. We do not knowingly collect
                        personal information from children. If you believe a child has provided us
                        with personal data, please contact us and we will delete it promptly.
                    </p>
                </section>

                {/* 8. Changes to This Policy */}
                <section className="space-y-3">
                    <h2 className="text-xl font-bold text-white">8. Changes to This Policy</h2>
                    <p className="text-zinc-300 leading-relaxed">
                        We may update this Privacy Policy from time to time. When we make material
                        changes, we will notify you by email or through the Service. Your continued
                        use of the Service after notification constitutes acceptance of the updated
                        policy.
                    </p>
                </section>

                {/* 9. Contact */}
                <section className="space-y-3">
                    <h2 className="text-xl font-bold text-white">9. Contact</h2>
                    <p className="text-zinc-300 leading-relaxed">
                        If you have questions about this Privacy Policy or how we handle your data,
                        contact us at{" "}
                        <a href="mailto:legal@capalpha.com" className="text-emerald-400 hover:text-emerald-300 underline underline-offset-2">
                            legal@capalpha.com
                        </a>.
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
                            <Link href="/legal/acceptable-use" className="text-emerald-400 hover:text-emerald-300 underline underline-offset-2">Acceptable Use Policy</Link>
                        </li>
                    </ul>
                </footer>
            </article>
        </div>
    );
}
