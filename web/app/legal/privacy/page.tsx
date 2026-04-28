import React from "react";
import { Metadata } from "next";
import Link from "next/link";
import { ShieldCheck, ArrowLeft } from "lucide-react";

export const metadata: Metadata = {
    title: "Privacy Policy | Pundit Ledger",
    description: "How Pundit Ledger collects, uses, and protects your information.",
};

export default function PrivacyPolicy() {
    return (
        <main className="min-h-[100dvh] bg-black text-white px-6 py-16">
            <div className="max-w-3xl mx-auto">
                {/* Back link */}
                <Link
                    href="/"
                    className="inline-flex items-center gap-2 text-sm text-zinc-500 hover:text-zinc-300 transition-colors mb-10"
                >
                    <ArrowLeft className="w-4 h-4" />
                    Back to Pundit Ledger
                </Link>

                {/* Header */}
                <div className="flex items-center gap-3 mb-2">
                    <ShieldCheck className="w-7 h-7 text-emerald-400 shrink-0" />
                    <h1 className="text-3xl font-extrabold tracking-tight">Privacy Policy</h1>
                </div>
                <p className="text-sm text-zinc-500 mb-12">Last updated: April 27, 2026</p>

                {/* Body */}
                <div className="space-y-10 text-zinc-300 leading-relaxed">
                    <section className="space-y-3">
                        <h2 className="text-xl font-bold text-white">1. What We Collect</h2>
                        <p>
                            When you visit Pundit Ledger we may collect standard server log data
                            (IP address, browser type, referring URL, pages visited). If you
                            create an account via Clerk, we store the email address and display
                            name you provide. We do not collect payment details directly — that is
                            handled by Stripe.
                        </p>
                        <p>
                            We do <strong>not</strong> sell your personal data to third parties.
                        </p>
                    </section>

                    <section className="space-y-3">
                        <h2 className="text-xl font-bold text-white">2. How We Use Your Information</h2>
                        <ul className="list-disc list-inside space-y-2 text-zinc-400">
                            <li>To operate and improve the service</li>
                            <li>To send transactional emails (account creation, password resets)</li>
                            <li>To detect and prevent abuse</li>
                            <li>
                                To understand aggregate usage patterns (via privacy-respecting
                                analytics — no cross-site tracking)
                            </li>
                        </ul>
                    </section>

                    <section className="space-y-3">
                        <h2 className="text-xl font-bold text-white">3. Cookies &amp; Local Storage</h2>
                        <p>
                            We use cookies set by Clerk for session authentication. We use browser
                            local storage for preferences such as sport filters. We do not use
                            advertising cookies or third-party tracking pixels.
                        </p>
                    </section>

                    <section className="space-y-3">
                        <h2 className="text-xl font-bold text-white">4. Third-Party Services</h2>
                        <p>We use the following third-party services:</p>
                        <ul className="list-disc list-inside space-y-2 text-zinc-400">
                            <li>
                                <strong className="text-zinc-300">Clerk</strong> — authentication
                                and user management
                            </li>
                            <li>
                                <strong className="text-zinc-300">Stripe</strong> — payment
                                processing (future Pro tier)
                            </li>
                            <li>
                                <strong className="text-zinc-300">Vercel</strong> — hosting and
                                edge network
                            </li>
                            <li>
                                <strong className="text-zinc-300">Google BigQuery</strong> — data
                                warehouse (server-side only; no user data stored there)
                            </li>
                        </ul>
                        <p>Each service has its own privacy policy that governs data they handle.</p>
                    </section>

                    <section className="space-y-3">
                        <h2 className="text-xl font-bold text-white">5. Data Retention</h2>
                        <p>
                            Account data is retained as long as your account is active. You may
                            request deletion at any time by emailing{" "}
                            <a
                                href="mailto:support@cap-alpha.co"
                                className="text-emerald-400 hover:text-emerald-300 transition-colors"
                            >
                                support@cap-alpha.co
                            </a>
                            . Prediction data in the public ledger is retained indefinitely as part
                            of the immutable record.
                        </p>
                    </section>

                    <section className="space-y-3">
                        <h2 className="text-xl font-bold text-white">6. Your Rights</h2>
                        <p>
                            Depending on your jurisdiction, you may have rights to access, correct,
                            or delete personal data we hold about you. To exercise these rights,
                            contact us at{" "}
                            <a
                                href="mailto:support@cap-alpha.co"
                                className="text-emerald-400 hover:text-emerald-300 transition-colors"
                            >
                                support@cap-alpha.co
                            </a>
                            .
                        </p>
                    </section>

                    <section className="space-y-3">
                        <h2 className="text-xl font-bold text-white">7. Changes to This Policy</h2>
                        <p>
                            We may update this policy from time to time. Material changes will be
                            announced via the site. Continued use of the service after the effective
                            date constitutes acceptance of the revised policy.
                        </p>
                    </section>

                    <section className="space-y-3">
                        <h2 className="text-xl font-bold text-white">8. Contact</h2>
                        <p>
                            Questions?{" "}
                            <a
                                href="mailto:support@cap-alpha.co"
                                className="text-emerald-400 hover:text-emerald-300 transition-colors"
                            >
                                support@cap-alpha.co
                            </a>
                        </p>
                    </section>
                </div>

                {/* Footer nav */}
                <div className="mt-16 pt-8 border-t border-zinc-900 flex items-center gap-6 text-xs text-zinc-600">
                    <Link href="/legal/terms" className="hover:text-zinc-400 transition-colors">
                        Terms of Service
                    </Link>
                    <Link href="/methodology" className="hover:text-zinc-400 transition-colors">
                        Methodology
                    </Link>
                    <Link href="/ledger" className="hover:text-zinc-400 transition-colors">
                        Leaderboard
                    </Link>
                </div>
            </div>
        </main>
    );
}
