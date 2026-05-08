import { Metadata } from "next";
import Link from "next/link";
import {
    ShieldCheck,
    ShieldAlert,
    Hash,
    Clock,
    BarChart3,
    Terminal,
} from "lucide-react";
import { ChainStatusDisplay } from "./chain-status-display";
import { HashLookupForm } from "./hash-lookup-form";

export const metadata: Metadata = {
    title: "Verify the Ledger | Pundit Ledger",
    description:
        "Every prediction in the Cap Alpha ledger is SHA-256 hashed and chained. Verify the chain integrity or look up any prediction by hash.",
};

interface ChainHead {
    chain_head_hash: string | null;
    total_predictions: number;
    last_added_at: string | null;
    chain_status: "INTACT" | "BROKEN" | "EMPTY" | "UNKNOWN";
}

async function fetchChainHead(): Promise<ChainHead> {
    const API_URL =
        process.env.API_URL ||
        process.env.NEXT_PUBLIC_API_URL ||
        "https://pundit-ledger-api-wvhvx2muna-uc.a.run.app";

    try {
        const res = await fetch(`${API_URL}/v1/integrity/head`, {
            headers: { Accept: "application/json" },
        });
        if (!res.ok) {
            return {
                chain_head_hash: null,
                total_predictions: 0,
                last_added_at: null,
                chain_status: "UNKNOWN",
            };
        }
        return await res.json();
    } catch {
        return {
            chain_head_hash: null,
            total_predictions: 0,
            last_added_at: null,
            chain_status: "UNKNOWN",
        };
    }
}

function formatNumber(n: number): string {
    return n.toLocaleString("en-US");
}

function formatTimestamp(iso: string | null): string {
    if (!iso) return "—";
    try {
        return new Date(iso).toLocaleString("en-US", {
            month: "short",
            day: "numeric",
            year: "numeric",
            hour: "2-digit",
            minute: "2-digit",
            timeZoneName: "short",
        });
    } catch {
        return iso;
    }
}

function truncateHash(hash: string | null): string {
    if (!hash) return "—";
    if (hash.length <= 32) return hash;
    return `${hash.slice(0, 16)}...${hash.slice(-8)}`;
}

export default async function VerifyPage() {
    const head = await fetchChainHead();
    const isIntact = head.chain_status === "INTACT";
    const isUnknown =
        head.chain_status === "UNKNOWN" || head.chain_status === "EMPTY";

    return (
        <div className="bg-black text-white min-h-[100dvh] flex flex-col font-sans">
            {/* Hero */}
            <section className="relative flex flex-col items-center justify-center text-center px-6 pt-24 pb-20 overflow-hidden">
                <div className="absolute inset-0 pointer-events-none">
                    <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[800px] h-[400px] bg-emerald-500/8 rounded-full blur-[120px]" />
                </div>
                <div className="relative z-10 max-w-3xl mx-auto space-y-6">
                    <span className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-emerald-500/30 bg-emerald-500/10 text-emerald-400 text-xs font-mono font-medium uppercase tracking-widest">
                        <ShieldCheck className="w-3.5 h-3.5" />
                        Verify the Ledger
                    </span>
                    <h1 className="text-4xl sm:text-5xl font-black tracking-tight leading-[1.1]">
                        Tamper-Proof by{" "}
                        <span className="text-emerald-400">Design</span>
                    </h1>
                    <p className="text-xl text-zinc-400 max-w-2xl mx-auto leading-relaxed">
                        Every prediction in the Cap Alpha ledger is SHA-256
                        hashed and chained. Changing any historical record
                        invalidates all hashes that follow. Verify it yourself.
                    </p>
                </div>
            </section>

            {/* Live chain status */}
            <section className="w-full px-6 py-16 border-t border-zinc-900">
                <div className="max-w-4xl mx-auto">
                    <div className="flex items-center gap-3 mb-8">
                        <span className="text-sm font-mono uppercase tracking-widest text-zinc-500">
                            Live Chain Status
                        </span>
                        <span className="text-xs text-zinc-700">
                            — refreshed every 60 seconds
                        </span>
                    </div>

                    <div className="grid sm:grid-cols-3 gap-4 mb-6">
                        {/* Total predictions */}
                        <div className="rounded-2xl border border-zinc-800 bg-zinc-900/50 p-6 space-y-2">
                            <div className="flex items-center gap-2 text-zinc-500 text-xs font-mono uppercase tracking-widest">
                                <BarChart3 className="w-3.5 h-3.5" />
                                Total Predictions
                            </div>
                            <div className="text-3xl font-black text-white tabular-nums">
                                {formatNumber(head.total_predictions)}
                            </div>
                        </div>

                        {/* Chain head hash */}
                        <div className="rounded-2xl border border-zinc-800 bg-zinc-900/50 p-6 space-y-2">
                            <div className="flex items-center gap-2 text-zinc-500 text-xs font-mono uppercase tracking-widest">
                                <Hash className="w-3.5 h-3.5" />
                                Chain Head Hash
                            </div>
                            <ChainStatusDisplay hash={head.chain_head_hash} />
                        </div>

                        {/* Last added */}
                        <div className="rounded-2xl border border-zinc-800 bg-zinc-900/50 p-6 space-y-2">
                            <div className="flex items-center gap-2 text-zinc-500 text-xs font-mono uppercase tracking-widest">
                                <Clock className="w-3.5 h-3.5" />
                                Last Verified
                            </div>
                            <div className="text-sm font-mono text-zinc-300 break-all">
                                {formatTimestamp(head.last_added_at)}
                            </div>
                        </div>
                    </div>

                    {/* Chain status badge */}
                    <div
                        className={`flex items-center gap-3 rounded-xl border p-4 ${
                            isUnknown
                                ? "border-zinc-700 bg-zinc-900/30"
                                : isIntact
                                ? "border-emerald-500/30 bg-emerald-500/5"
                                : "border-red-500/30 bg-red-500/5"
                        }`}
                    >
                        {isUnknown ? (
                            <Hash className="w-5 h-5 text-zinc-500 shrink-0" />
                        ) : isIntact ? (
                            <ShieldCheck className="w-5 h-5 text-emerald-400 shrink-0" />
                        ) : (
                            <ShieldAlert className="w-5 h-5 text-red-400 shrink-0" />
                        )}
                        <div>
                            <span
                                className={`font-mono font-bold text-sm ${
                                    isUnknown
                                        ? "text-zinc-400"
                                        : isIntact
                                        ? "text-emerald-400"
                                        : "text-red-400"
                                }`}
                            >
                                {head.chain_status}
                            </span>
                            <span className="text-zinc-500 text-sm ml-2">
                                {isUnknown
                                    ? "— Status unavailable. The API may be starting up."
                                    : isIntact
                                    ? "— Every prediction in the chain has a valid hash. No tampering detected."
                                    : "— Chain integrity violation detected. Contact support@cap-alpha.co immediately."}
                            </span>
                        </div>
                    </div>
                </div>
            </section>

            {/* Prediction lookup */}
            <section className="w-full px-6 py-16 border-t border-zinc-900">
                <div className="max-w-3xl mx-auto">
                    <div className="mb-8">
                        <span className="text-sm font-mono uppercase tracking-widest text-zinc-500">
                            Prediction Lookup
                        </span>
                        <h2 className="text-2xl font-bold text-white mt-2">
                            Verify a Specific Prediction
                        </h2>
                        <p className="text-zinc-400 text-sm mt-1">
                            Enter a <code className="text-emerald-400 font-mono">chain_hash</code> or{" "}
                            <code className="text-emerald-400 font-mono">prediction_hash</code> to confirm
                            it exists in the ledger.
                        </p>
                    </div>
                    <HashLookupForm />
                </div>
            </section>

            {/* How to verify independently */}
            <section className="w-full px-6 py-16 border-t border-zinc-900">
                <div className="max-w-3xl mx-auto">
                    <div className="mb-8">
                        <span className="text-sm font-mono uppercase tracking-widest text-zinc-500">
                            DIY Verification
                        </span>
                        <h2 className="text-2xl font-bold text-white mt-2">
                            How to Verify Independently
                        </h2>
                        <p className="text-zinc-400 text-sm mt-1">
                            You don&apos;t need to trust us. Here&apos;s the exact algorithm.
                        </p>
                    </div>

                    <div className="space-y-4">
                        {[
                            {
                                step: 1,
                                title: "Get the canonical payload",
                                description:
                                    "Each prediction's payload is the pipe-delimited concatenation of its core fields:",
                                code: "{timestamp}|{source_url}|{pundit_id}|{raw_assertion_text}",
                            },
                            {
                                step: 2,
                                title: "Compute the SHA-256 hash",
                                description:
                                    "Hash the payload string with no trailing newline:",
                                code: 'echo -n "<payload>" | sha256sum',
                            },
                            {
                                step: 3,
                                title: "Compare to the stored hash",
                                description:
                                    "The output should match the chain_hash returned by the public API:",
                                code: "GET /v1/predictions/{hash}/verify",
                            },
                            {
                                step: 4,
                                title: "Verify the chain link",
                                description:
                                    "Each link in the chain includes the previous hash. The chain hash is:",
                                code: "SHA-256(previous_chain_hash + current_payload)",
                            },
                        ].map(({ step, title, description, code }) => (
                            <div
                                key={step}
                                className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-6 space-y-3"
                            >
                                <div className="flex items-start gap-4">
                                    <span className="w-7 h-7 rounded-full border border-emerald-500/40 bg-emerald-500/10 text-emerald-400 text-xs font-black flex items-center justify-center shrink-0 mt-0.5">
                                        {step}
                                    </span>
                                    <div className="space-y-2 min-w-0">
                                        <h3 className="font-semibold text-white">
                                            {title}
                                        </h3>
                                        <p className="text-sm text-zinc-400">
                                            {description}
                                        </p>
                                        <div className="flex items-start gap-2 bg-zinc-950 border border-zinc-800 rounded-lg px-4 py-3">
                                            <Terminal className="w-3.5 h-3.5 text-emerald-500 shrink-0 mt-0.5" />
                                            <code className="text-xs font-mono text-emerald-300 break-all">
                                                {code}
                                            </code>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>

                    <div className="mt-6 rounded-xl border border-zinc-800 bg-zinc-900/30 p-5 text-sm text-zinc-400 leading-relaxed">
                        <span className="font-semibold text-zinc-200">
                            Why this matters:
                        </span>{" "}
                        The chain structure means that even if someone gained
                        write access to the database, they could not silently
                        alter old predictions — every subsequent hash in the
                        chain would need to be recomputed, and the chain head
                        would change. Anyone polling the public API would detect
                        the change immediately.
                    </div>
                </div>
            </section>

            {/* CTA */}
            <section className="w-full px-6 py-16 border-t border-zinc-900">
                <div className="max-w-3xl mx-auto text-center space-y-4">
                    <h2 className="text-2xl font-bold text-white">
                        See the predictions themselves
                    </h2>
                    <p className="text-zinc-400">
                        Browse every scored prediction and how pundits are
                        performing.
                    </p>
                    <div className="flex flex-wrap items-center justify-center gap-3">
                        <Link
                            href="/ledger"
                            className="inline-flex items-center gap-2 px-6 py-3 rounded-lg bg-emerald-500 text-black text-sm font-semibold hover:bg-emerald-400 transition-colors"
                        >
                            View Leaderboard
                        </Link>
                        <Link
                            href="/methodology"
                            className="inline-flex items-center gap-2 px-6 py-3 rounded-lg border border-zinc-700 text-zinc-300 text-sm font-semibold hover:border-zinc-500 hover:text-white transition-colors"
                        >
                            Read the Methodology
                        </Link>
                    </div>
                </div>
            </section>
        </div>
    );
}
