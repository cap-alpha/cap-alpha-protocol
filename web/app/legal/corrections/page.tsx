import React from "react";
import { Metadata } from "next";
import Link from "next/link";
import { ArrowLeft, RotateCcw } from "lucide-react";

export const metadata: Metadata = {
    title: "Correction & Retraction Policy | Cap Alpha",
    description:
        "How Cap Alpha handles wrong prediction resolutions — reporting errors, SLA, ledger corrections, and user notifications.",
};

export default function CorrectionsPolicy() {
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
                    <RotateCcw className="w-7 h-7 text-emerald-400 shrink-0" />
                    <h1 className="text-3xl font-extrabold tracking-tight">
                        Correction & Retraction Policy
                    </h1>
                </div>
                <p className="text-sm text-zinc-500 mb-12">Last Updated: May 4, 2026</p>

                <div className="space-y-10 text-zinc-300 leading-relaxed">
                    <section className="space-y-3">
                        <h2 className="text-xl font-bold text-white">1. Our Commitment</h2>
                        <p>
                            Cap Alpha strives to resolve predictions accurately and transparently.
                            When a resolution is wrong — whether due to a data error, ambiguous
                            claim language, or a factual mistake — we correct it promptly and
                            leave a permanent record in the ledger. We do not silently overwrite
                            incorrect resolutions.
                        </p>
                    </section>

                    <section className="space-y-3">
                        <h2 className="text-xl font-bold text-white">2. How to Report an Error</h2>
                        <p>
                            If you believe a prediction has been incorrectly resolved, contact us
                            at{" "}
                            <a
                                href="mailto:corrections@cap-alpha.co"
                                className="text-emerald-400 underline hover:text-emerald-300 transition-colors"
                            >
                                corrections@cap-alpha.co
                            </a>{" "}
                            with:
                        </p>
                        <ul className="list-disc list-inside space-y-1 pl-2">
                            <li>The pundit name and the specific prediction text</li>
                            <li>The resolution shown (CORRECT / INCORRECT / VOID)</li>
                            <li>
                                What you believe the correct resolution should be and why (with
                                source links if available)
                            </li>
                        </ul>
                    </section>

                    <section className="space-y-3">
                        <h2 className="text-xl font-bold text-white">
                            3. Review Timeline (SLA)
                        </h2>
                        <ul className="list-disc list-inside space-y-1 pl-2">
                            <li>
                                <strong className="text-white">Acknowledgment:</strong> within 24
                                hours of receiving your report
                            </li>
                            <li>
                                <strong className="text-white">Resolution decision:</strong> within
                                48 hours for clear-cut factual errors; up to 7 days for contested
                                interpretations
                            </li>
                            <li>
                                <strong className="text-white">Ledger update:</strong> same business
                                day as the decision
                            </li>
                        </ul>
                    </section>

                    <section className="space-y-3">
                        <h2 className="text-xl font-bold text-white">4. How Corrections Are Recorded</h2>
                        <p>
                            Cap Alpha uses a cryptographic ledger to ensure prediction records
                            cannot be silently altered. When a correction is made:
                        </p>
                        <ul className="list-disc list-inside space-y-1 pl-2">
                            <li>
                                The original (wrong) resolution entry is preserved in the ledger
                                with its original timestamp and hash
                            </li>
                            <li>
                                A new correction entry is appended referencing the original entry
                                ID, the correct outcome, the reason for correction, and the
                                correction timestamp
                            </li>
                            <li>
                                The pundit&apos;s accuracy statistics are recalculated from the
                                corrected ledger on the next scoring run
                            </li>
                            <li>
                                All historical correction entries are publicly visible in the
                                ledger audit log
                            </li>
                        </ul>
                    </section>

                    <section className="space-y-3">
                        <h2 className="text-xl font-bold text-white">5. User Notification</h2>
                        <p>
                            If a correction affects a prediction you have bookmarked or a pundit
                            you follow, we will notify you by email within 24 hours of the
                            correction being applied. We will explain what changed and why.
                        </p>
                    </section>

                    <section className="space-y-3">
                        <h2 className="text-xl font-bold text-white">
                            6. Contested Interpretations
                        </h2>
                        <p>
                            Some predictions are genuinely ambiguous. For contested cases where
                            reasonable people could disagree on the correct interpretation, we may
                            mark the resolution as <strong className="text-white">VOID</strong>{" "}
                            (unresolvable) rather than pick a side. Our reasoning will be
                            documented in the ledger entry.
                        </p>
                    </section>

                    <section className="space-y-3">
                        <h2 className="text-xl font-bold text-white">7. Appeals</h2>
                        <p>
                            If you disagree with our correction decision, you may appeal by
                            replying to your correction acknowledgment email. Appeals are reviewed
                            by a different team member than the original decision. Final
                            resolution decisions are made within 5 business days of the appeal.
                        </p>
                    </section>

                    <section className="space-y-3">
                        <h2 className="text-xl font-bold text-white">8. Scope</h2>
                        <p>
                            This policy applies to all prediction resolutions on Cap Alpha,
                            including automated resolutions and human-reviewed resolutions. It
                            does not apply to differences of opinion about whether a prediction
                            was a good or bad bet — only to factually incorrect outcomes.
                        </p>
                    </section>
                </div>
            </div>
        </main>
    );
}
