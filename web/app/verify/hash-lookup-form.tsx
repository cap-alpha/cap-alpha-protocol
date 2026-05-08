"use client";

import { useState, useTransition, FormEvent } from "react";
import {
    Search,
    ShieldCheck,
    ShieldAlert,
    Loader2,
    ExternalLink,
} from "lucide-react";

interface VerifyResult {
    found: boolean;
    chain_position?: number | null;
    added_at?: string | null;
    pundit_id?: string | null;
    pundit_name?: string | null;
    raw_assertion?: string | null;
    extracted_claim?: string | null;
    prediction_date?: string | null;
    error?: string;
}

function formatDate(iso: string | null | undefined): string {
    if (!iso) return "—";
    try {
        return new Date(iso).toLocaleDateString("en-US", {
            month: "short",
            day: "numeric",
            year: "numeric",
        });
    } catch {
        return iso;
    }
}

export function HashLookupForm() {
    const [hash, setHash] = useState("");
    const [result, setResult] = useState<VerifyResult | null>(null);
    const [isPending, startTransition] = useTransition();

    const handleSubmit = (e: FormEvent<HTMLFormElement>) => {
        e.preventDefault();
        const trimmed = hash.trim();
        if (!trimmed || trimmed.length < 8) return;

        setResult(null);
        startTransition(async () => {
            try {
                const res = await fetch(
                    `/api/predictions/verify/${encodeURIComponent(trimmed)}`
                );
                if (!res.ok) {
                    setResult({ found: false, error: `HTTP ${res.status}` });
                    return;
                }
                const data: VerifyResult = await res.json();
                setResult(data);
            } catch (err) {
                setResult({
                    found: false,
                    error: err instanceof Error ? err.message : "Network error",
                });
            }
        });
    };

    return (
        <div className="space-y-4">
            <form onSubmit={handleSubmit} className="flex gap-3">
                <div className="flex-1 relative">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500 pointer-events-none" />
                    <input
                        type="text"
                        value={hash}
                        onChange={(e) => setHash(e.target.value)}
                        placeholder="Enter chain_hash or prediction_hash…"
                        className="w-full bg-zinc-900 border border-zinc-700 rounded-lg pl-10 pr-4 py-3 text-sm font-mono text-zinc-200 placeholder-zinc-600 focus:outline-none focus:ring-1 focus:ring-emerald-500 focus:border-emerald-500 transition-colors"
                        spellCheck={false}
                        autoCorrect="off"
                        autoCapitalize="off"
                    />
                </div>
                <button
                    type="submit"
                    disabled={isPending || hash.trim().length < 8}
                    className="px-5 py-3 rounded-lg bg-emerald-500 text-black text-sm font-semibold hover:bg-emerald-400 transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2"
                >
                    {isPending ? (
                        <>
                            <Loader2 className="w-4 h-4 animate-spin" />
                            Verifying…
                        </>
                    ) : (
                        "Verify"
                    )}
                </button>
            </form>

            {/* Result */}
            {result && (
                <div
                    className={`rounded-xl border p-5 space-y-4 transition-all ${
                        result.found
                            ? "border-emerald-500/30 bg-emerald-500/5"
                            : "border-zinc-700 bg-zinc-900/40"
                    }`}
                >
                    {result.found ? (
                        <>
                            <div className="flex items-center gap-2">
                                <ShieldCheck className="w-5 h-5 text-emerald-400 shrink-0" />
                                <span className="font-semibold text-emerald-400">
                                    Prediction found in ledger
                                </span>
                                {result.chain_position != null && (
                                    <span className="ml-auto text-xs font-mono text-zinc-500">
                                        #{result.chain_position.toLocaleString()}
                                    </span>
                                )}
                            </div>
                            <div className="grid sm:grid-cols-2 gap-3 text-sm">
                                <div>
                                    <span className="text-zinc-500 text-xs font-mono uppercase tracking-wider">
                                        Pundit
                                    </span>
                                    <p className="text-zinc-200 mt-0.5">
                                        {result.pundit_name || result.pundit_id || "—"}
                                    </p>
                                </div>
                                <div>
                                    <span className="text-zinc-500 text-xs font-mono uppercase tracking-wider">
                                        Prediction Date
                                    </span>
                                    <p className="text-zinc-200 mt-0.5">
                                        {formatDate(result.prediction_date)}
                                    </p>
                                </div>
                                <div>
                                    <span className="text-zinc-500 text-xs font-mono uppercase tracking-wider">
                                        Added to Ledger
                                    </span>
                                    <p className="text-zinc-200 mt-0.5">
                                        {formatDate(result.added_at)}
                                    </p>
                                </div>
                            </div>
                            {result.extracted_claim && (
                                <div>
                                    <span className="text-zinc-500 text-xs font-mono uppercase tracking-wider">
                                        Extracted Claim
                                    </span>
                                    <p className="text-zinc-300 text-sm mt-1 leading-relaxed italic">
                                        &ldquo;{result.extracted_claim}&rdquo;
                                    </p>
                                </div>
                            )}
                            {result.raw_assertion && (
                                <div>
                                    <span className="text-zinc-500 text-xs font-mono uppercase tracking-wider">
                                        Original Assertion
                                    </span>
                                    <p className="text-zinc-400 text-xs mt-1 leading-relaxed">
                                        {result.raw_assertion}
                                    </p>
                                </div>
                            )}
                            {result.pundit_id && (
                                <a
                                    href={`/pundits/${result.pundit_id}`}
                                    className="inline-flex items-center gap-1.5 text-xs text-emerald-400 hover:text-emerald-300 transition-colors"
                                >
                                    View pundit profile{" "}
                                    <ExternalLink className="w-3 h-3" />
                                </a>
                            )}
                        </>
                    ) : (
                        <div className="flex items-center gap-2">
                            <ShieldAlert className="w-5 h-5 text-zinc-500 shrink-0" />
                            <div>
                                <span className="font-semibold text-zinc-300">
                                    Not found in ledger
                                </span>
                                {result.error && (
                                    <p className="text-xs text-zinc-500 mt-0.5">
                                        {result.error}
                                    </p>
                                )}
                                <p className="text-xs text-zinc-500 mt-0.5">
                                    This hash does not match any prediction or
                                    chain hash in our database.
                                </p>
                            </div>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}
