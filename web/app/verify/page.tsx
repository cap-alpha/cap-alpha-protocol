/**
 * /verify — Verify the Ledger
 *
 * Public integrity page exposing SHA-256 chain verification.
 * Server shell + client islands for interactive parts.
 *
 * Issue #768.
 */

import { Metadata } from "next";
import Link from "next/link";
import {
    Lock,
    ShieldCheck,
    ArrowRight,
    Hash,
    BookOpen,
    Code2,
    Terminal,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { DisplayHeading } from "@/components/ui/heading";
import { ChainStatusWidget, PredictionLookup } from "./VerifyClient";

export const metadata: Metadata = {
    title: "Verify the Ledger | Pundit Ledger",
    description:
        "Independently verify the cryptographic integrity of the Pundit Prediction Ledger. Every prediction is SHA-256 hash-chained — tamper-evident and publicly auditable.",
    openGraph: {
        title: "Verify the Ledger | Pundit Ledger",
        description:
            "The Pundit Prediction Ledger is cryptographically sealed. Verify chain integrity or look up any individual prediction hash here.",
    },
};

// ---------------------------------------------------------------------------
// Static sub-components (server-rendered)
// ---------------------------------------------------------------------------

function StepNumber({ n }: { n: number }) {
    return (
        <div className="flex-shrink-0 w-8 h-8 rounded-full bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center">
            <span className="text-sm font-black text-emerald-400">{n}</span>
        </div>
    );
}

function InlineCode({ children }: { children: string }) {
    return (
        <code className="font-mono text-xs bg-zinc-800 border border-zinc-700 rounded px-1.5 py-0.5 text-emerald-300">
            {children}
        </code>
    );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function VerifyPage() {
    return (
        <div className="bg-black text-white min-h-[100dvh] flex flex-col font-sans">
            {/* ================================================================
                Hero
            ================================================================ */}
            <section className="relative flex flex-col items-center justify-center text-center px-6 pt-24 pb-20 overflow-hidden">
                <div className="absolute inset-0 pointer-events-none">
                    <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[800px] h-[400px] bg-emerald-500/8 rounded-full blur-[120px]" />
                </div>
                <div className="relative z-10 max-w-3xl mx-auto space-y-6">
                    <Badge variant="eyebrow" className="border-emerald-500/30 bg-emerald-500/10 text-emerald-400">
                        <Lock className="w-3.5 h-3.5" />
                        Cryptographic Integrity
                    </Badge>
                    <DisplayHeading size="md" className="font-display sm:text-display-lg">
                        Verify the{" "}
                        <span className="text-emerald-400">Ledger</span>
                    </DisplayHeading>
                    <p className="text-xl text-zinc-400 max-w-xl mx-auto leading-relaxed">
                        Every prediction in the Pundit Ledger is sealed with a
                        SHA-256 hash chain. Anyone can verify that the record has
                        never been altered — you don&apos;t have to take our word
                        for it.
                    </p>
                    <div className="flex flex-wrap items-center justify-center gap-4 text-sm">
                        <Link
                            href="/methodology"
                            className="inline-flex items-center gap-1.5 text-emerald-400 hover:text-emerald-300 transition-colors"
                        >
                            <BookOpen className="w-4 h-4" />
                            Read the methodology
                        </Link>
                        <span className="text-zinc-700">·</span>
                        <a
                            href="#how-to-verify"
                            className="inline-flex items-center gap-1.5 text-zinc-400 hover:text-zinc-300 transition-colors"
                        >
                            How to verify independently
                            <ArrowRight className="w-4 h-4" />
                        </a>
                    </div>
                </div>
            </section>

            {/* ================================================================
                How SHA-256 chaining works
            ================================================================ */}
            <section className="w-full px-6 py-16 border-t border-zinc-900">
                <div className="max-w-3xl mx-auto space-y-8">
                    <div className="space-y-3">
                        <Badge variant="eyebrow" className="border-zinc-700 bg-zinc-900 text-zinc-400">
                            <Hash className="w-3.5 h-3.5" />
                            How it works
                        </Badge>
                        <h2 className="text-2xl sm:text-3xl font-black text-white">
                            SHA-256 Hash Chaining
                        </h2>
                    </div>

                    <div className="space-y-6 text-zinc-400 leading-relaxed">
                        <p>
                            When a prediction is extracted and written to the ledger, the
                            system computes two hashes:
                        </p>

                        <div className="space-y-4">
                            <div className="flex items-start gap-4">
                                <div className="flex-shrink-0 w-2 h-2 mt-2.5 rounded-full bg-emerald-400" />
                                <div>
                                    <p className="text-zinc-200 font-semibold">
                                        prediction_hash
                                    </p>
                                    <p className="text-sm mt-1">
                                        A SHA-256 digest of the prediction&apos;s core fields:{" "}
                                        <InlineCode>
                                            timestamp|source_url|pundit_id|raw_assertion_text
                                        </InlineCode>
                                        . This uniquely identifies the content of the
                                        prediction itself.
                                    </p>
                                </div>
                            </div>

                            <div className="flex items-start gap-4">
                                <div className="flex-shrink-0 w-2 h-2 mt-2.5 rounded-full bg-emerald-400" />
                                <div>
                                    <p className="text-zinc-200 font-semibold">chain_hash</p>
                                    <p className="text-sm mt-1">
                                        A SHA-256 digest of{" "}
                                        <InlineCode>
                                            prediction_hash + previous_chain_hash
                                        </InlineCode>
                                        . Each record in the ledger includes the hash of the
                                        record that came before it — forming an unbroken chain
                                        from the first prediction to the last.
                                    </p>
                                </div>
                            </div>
                        </div>

                        <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-5 space-y-2">
                            <p className="text-zinc-300 font-semibold text-sm">
                                Why this matters
                            </p>
                            <p className="text-sm">
                                If anyone modified even a single character of a stored
                                prediction — the text, the timestamp, the pundit — the
                                chain_hash would no longer match what it should be. Every
                                subsequent record would also fail verification. A broken chain
                                is detectable immediately and irrefutably.
                            </p>
                        </div>
                    </div>
                </div>
            </section>

            {/* ================================================================
                Live Chain Status Widget (client island)
            ================================================================ */}
            <section className="w-full px-6 py-16 border-t border-zinc-900">
                <div className="max-w-3xl mx-auto space-y-6">
                    <div className="space-y-2">
                        <Badge variant="eyebrow" className="border-zinc-700 bg-zinc-900 text-zinc-400">
                            <ShieldCheck className="w-3.5 h-3.5" />
                            Live status
                        </Badge>
                        <h2 className="text-2xl sm:text-3xl font-black text-white">
                            Chain Status
                        </h2>
                        <p className="text-zinc-400 text-sm leading-relaxed max-w-lg">
                            The widget below fetches the current chain head directly from
                            our ledger. The{" "}
                            <span className="font-semibold text-zinc-300">INTACT</span>{" "}
                            status indicates the ledger has passed a consistency read. For a
                            full cryptographic walk of every record, use the{" "}
                            <InlineCode>/v1/integrity/verify</InlineCode> API endpoint
                            (API key required).
                        </p>
                    </div>

                    <ChainStatusWidget />
                </div>
            </section>

            {/* ================================================================
                Single-prediction lookup (client island)
            ================================================================ */}
            <section className="w-full px-6 py-16 border-t border-zinc-900">
                <div className="max-w-3xl mx-auto space-y-6">
                    <div className="space-y-2">
                        <Badge variant="eyebrow" className="border-zinc-700 bg-zinc-900 text-zinc-400">
                            <Code2 className="w-3.5 h-3.5" />
                            Lookup
                        </Badge>
                        <h2 className="text-2xl sm:text-3xl font-black text-white">
                            Verify a Single Prediction
                        </h2>
                        <p className="text-zinc-400 text-sm leading-relaxed max-w-lg">
                            Have a <InlineCode>prediction_hash</InlineCode>? Paste it
                            below to confirm it exists in the ledger, see its chain
                            position, and view the prediction summary.
                        </p>
                    </div>

                    <PredictionLookup />
                </div>
            </section>

            {/* ================================================================
                How to verify independently
            ================================================================ */}
            <section
                id="how-to-verify"
                className="w-full px-6 py-16 border-t border-zinc-900 scroll-mt-8"
            >
                <div className="max-w-3xl mx-auto space-y-8">
                    <div className="space-y-2">
                        <Badge variant="eyebrow" className="border-zinc-700 bg-zinc-900 text-zinc-400">
                            <Terminal className="w-3.5 h-3.5" />
                            DIY verification
                        </Badge>
                        <h2 className="text-2xl sm:text-3xl font-black text-white">
                            How to Verify Independently
                        </h2>
                        <p className="text-zinc-400 leading-relaxed">
                            You don&apos;t need to trust our UI. Reproduce any hash from
                            scratch using standard command-line tools.
                        </p>
                    </div>

                    <div className="space-y-6">
                        {/* Step 1 */}
                        <div className="flex items-start gap-4">
                            <StepNumber n={1} />
                            <div className="space-y-2 min-w-0">
                                <h3 className="font-semibold text-zinc-200">
                                    Obtain the raw prediction fields
                                </h3>
                                <p className="text-sm text-zinc-400 leading-relaxed">
                                    From a prediction card, copy the four canonical fields:{" "}
                                    <InlineCode>ingestion_timestamp</InlineCode>,{" "}
                                    <InlineCode>source_url</InlineCode>,{" "}
                                    <InlineCode>pundit_id</InlineCode>, and{" "}
                                    <InlineCode>raw_assertion_text</InlineCode>. These are
                                    always shown verbatim — no summarization or paraphrasing.
                                </p>
                            </div>
                        </div>

                        {/* Step 2 */}
                        <div className="flex items-start gap-4">
                            <StepNumber n={2} />
                            <div className="space-y-2 min-w-0">
                                <h3 className="font-semibold text-zinc-200">
                                    Construct the canonical input string
                                </h3>
                                <p className="text-sm text-zinc-400 leading-relaxed">
                                    Join the four fields with a pipe separator in this exact
                                    order:
                                </p>
                                <div className="rounded-xl border border-zinc-800 bg-zinc-950 p-4 overflow-x-auto">
                                    <pre className="text-xs font-mono text-zinc-300 whitespace-pre-wrap break-all">
{`{ingestion_timestamp}|{source_url}|{pundit_id}|{raw_assertion_text}`}
                                    </pre>
                                </div>
                                <p className="text-xs text-zinc-500">
                                    The timestamp is ISO-8601 UTC. All fields are
                                    UTF-8 encoded. No trailing newline.
                                </p>
                            </div>
                        </div>

                        {/* Step 3 */}
                        <div className="flex items-start gap-4">
                            <StepNumber n={3} />
                            <div className="space-y-2 min-w-0">
                                <h3 className="font-semibold text-zinc-200">
                                    Compute the SHA-256 hash
                                </h3>
                                <p className="text-sm text-zinc-400 leading-relaxed">
                                    Using any standard SHA-256 implementation:
                                </p>
                                <div className="rounded-xl border border-zinc-800 bg-zinc-950 p-4 overflow-x-auto">
                                    <pre className="text-xs font-mono text-zinc-300 whitespace-pre">
{`# bash / macOS
echo -n "2024-09-01T12:00:00|https://...|adam_schefter|He'll get traded." \\
  | sha256sum

# Python
import hashlib
data = "2024-09-01T12:00:00|https://...|adam_schefter|He'll get traded."
print(hashlib.sha256(data.encode()).hexdigest())`}
                                    </pre>
                                </div>
                            </div>
                        </div>

                        {/* Step 4 */}
                        <div className="flex items-start gap-4">
                            <StepNumber n={4} />
                            <div className="space-y-2 min-w-0">
                                <h3 className="font-semibold text-zinc-200">
                                    Compare with the stored hash
                                </h3>
                                <p className="text-sm text-zinc-400 leading-relaxed">
                                    Paste the output hash into the lookup tool above, or compare
                                    it against the <InlineCode>prediction_hash</InlineCode> shown
                                    on the prediction card. If they match, the prediction
                                    is exactly as it was when originally recorded — byte for byte.
                                </p>
                            </div>
                        </div>
                    </div>

                    {/* API note */}
                    <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-5 space-y-3">
                        <h4 className="font-semibold text-zinc-200 text-sm">
                            Full chain walk via API
                        </h4>
                        <p className="text-sm text-zinc-400 leading-relaxed">
                            To walk every record in the ledger and verify the complete
                            hash chain, use the authenticated{" "}
                            <InlineCode>GET /v1/integrity/verify</InlineCode> endpoint.
                            An API key is required. See the{" "}
                            <Link
                                href="/docs"
                                className="text-emerald-400 hover:text-emerald-300 transition-colors"
                            >
                                API documentation
                            </Link>{" "}
                            for details.
                        </p>
                    </div>
                </div>
            </section>

            {/* ================================================================
                CTA
            ================================================================ */}
            <section className="w-full px-6 py-16 border-t border-zinc-900">
                <div className="max-w-3xl mx-auto text-center space-y-4">
                    <h2 className="text-2xl font-black text-white">
                        Still have questions?
                    </h2>
                    <p className="text-zinc-400 leading-relaxed">
                        Read the full methodology for how predictions are extracted,
                        scored, and why the ledger is immutable by design.
                    </p>
                    <div className="flex flex-wrap items-center justify-center gap-4">
                        <Link
                            href="/methodology"
                            className="inline-flex items-center gap-2 px-6 py-3 rounded-lg bg-emerald-500 text-black text-sm font-semibold hover:bg-emerald-400 transition-colors"
                        >
                            Read methodology <ArrowRight className="w-4 h-4" />
                        </Link>
                        <Link
                            href="/docs"
                            className="inline-flex items-center gap-2 px-6 py-3 rounded-lg border border-zinc-700 bg-zinc-900 text-zinc-200 text-sm font-semibold hover:border-zinc-600 hover:bg-zinc-800 transition-colors"
                        >
                            API docs
                        </Link>
                    </div>
                </div>
            </section>
        </div>
    );
}
