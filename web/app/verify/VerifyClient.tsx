"use client";

import { useState, useEffect, useCallback } from "react";
import { Copy, Check, Search, Loader2, ShieldCheck, ShieldAlert, AlertTriangle } from "lucide-react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ChainHead {
    total_predictions: number;
    head_hash: string | null;
    head_timestamp: string | null;
    chain_status: "INTACT" | "UNKNOWN";
    verified_at: string;
    error?: string;
}

interface LookupResult {
    found: boolean;
    prediction_hash: string;
    chain_position?: number | null;
    chain_hash?: string | null;
    ingestion_timestamp?: string | null;
    pundit_name?: string | null;
    extracted_claim?: string | null;
    claim_category?: string | null;
    season_year?: number | null;
    source_url?: string | null;
    error?: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatTimestamp(ts: string | null | undefined): string {
    if (!ts) return "—";
    try {
        return new Date(ts).toLocaleString("en-US", {
            year: "numeric",
            month: "short",
            day: "numeric",
            hour: "2-digit",
            minute: "2-digit",
            timeZoneName: "short",
        });
    } catch {
        return ts;
    }
}

function CopyButton({ text }: { text: string }) {
    const [copied, setCopied] = useState(false);

    const handleCopy = async () => {
        try {
            await navigator.clipboard.writeText(text);
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        } catch {
            // clipboard API unavailable
        }
    };

    return (
        <button
            onClick={handleCopy}
            aria-label="Copy to clipboard"
            className="ml-2 p-1.5 rounded-md bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 transition-colors shrink-0"
        >
            {copied ? (
                <Check className="w-3.5 h-3.5 text-emerald-400" />
            ) : (
                <Copy className="w-3.5 h-3.5 text-zinc-400" />
            )}
        </button>
    );
}

// ---------------------------------------------------------------------------
// Chain Status Widget
// ---------------------------------------------------------------------------

export function ChainStatusWidget() {
    const [data, setData] = useState<ChainHead | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        let cancelled = false;
        setLoading(true);

        fetch("/api/integrity/head", { cache: "no-store" })
            .then((r) => r.json())
            .then((d: ChainHead) => {
                if (!cancelled) {
                    setData(d);
                    setLoading(false);
                }
            })
            .catch(() => {
                if (!cancelled) {
                    setData({
                        total_predictions: 0,
                        head_hash: null,
                        head_timestamp: null,
                        chain_status: "UNKNOWN",
                        verified_at: new Date().toISOString(),
                        error: "Failed to reach integrity endpoint",
                    });
                    setLoading(false);
                }
            });

        return () => {
            cancelled = true;
        };
    }, []);

    if (loading) {
        return (
            <div className="rounded-2xl border border-zinc-800 bg-zinc-900/50 p-8 flex items-center justify-center min-h-[220px]">
                <Loader2 className="w-6 h-6 text-emerald-400 animate-spin" />
                <span className="ml-3 text-zinc-400 text-sm">Fetching chain head&hellip;</span>
            </div>
        );
    }

    const isIntact = data?.chain_status === "INTACT";

    return (
        <div
            className={`rounded-2xl border p-8 space-y-6 ${
                isIntact
                    ? "border-emerald-500/30 bg-emerald-500/5"
                    : "border-zinc-700 bg-zinc-900/50"
            }`}
        >
            {/* Status banner */}
            <div className="flex items-center gap-3">
                {isIntact ? (
                    <ShieldCheck className="w-7 h-7 text-emerald-400 shrink-0" />
                ) : (
                    <ShieldAlert className="w-7 h-7 text-zinc-400 shrink-0" />
                )}
                <div>
                    <span
                        className={`text-2xl font-black font-mono ${
                            isIntact ? "text-emerald-400" : "text-zinc-400"
                        }`}
                    >
                        {data?.chain_status ?? "UNKNOWN"}
                    </span>
                    <p className="text-xs text-zinc-500 mt-0.5">
                        Chain integrity status
                    </p>
                </div>
                {isIntact && (
                    <span className="ml-auto text-xs font-mono uppercase tracking-widest px-2 py-0.5 rounded-full border border-emerald-500/30 bg-emerald-500/10 text-emerald-400">
                        Verified
                    </span>
                )}
            </div>

            {data?.error && (
                <div className="flex items-start gap-2 rounded-lg border border-amber-500/20 bg-amber-500/5 px-4 py-3 text-sm text-amber-400">
                    <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
                    <span>{data.error}</span>
                </div>
            )}

            {/* Stats grid */}
            <div className="grid grid-cols-2 gap-4">
                <div className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-4 space-y-1">
                    <p className="text-xs font-mono uppercase tracking-widest text-zinc-500">
                        Total predictions
                    </p>
                    <p className="text-3xl font-black text-white">
                        {(data?.total_predictions ?? 0).toLocaleString()}
                    </p>
                </div>
                <div className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-4 space-y-1">
                    <p className="text-xs font-mono uppercase tracking-widest text-zinc-500">
                        Last verified
                    </p>
                    <p className="text-sm text-zinc-300 leading-snug">
                        {formatTimestamp(data?.verified_at)}
                    </p>
                </div>
            </div>

            {/* Head hash */}
            {data?.head_hash && (
                <div className="space-y-2">
                    <p className="text-xs font-mono uppercase tracking-widest text-zinc-500">
                        Latest chain head hash
                    </p>
                    <div className="flex items-center gap-0 rounded-xl border border-zinc-800 bg-zinc-950 px-4 py-3">
                        <code className="font-mono text-xs text-emerald-300 break-all flex-1">
                            {data.head_hash}
                        </code>
                        <CopyButton text={data.head_hash} />
                    </div>
                    {data.head_timestamp && (
                        <p className="text-xs text-zinc-600">
                            Latest entry: {formatTimestamp(data.head_timestamp)}
                        </p>
                    )}
                </div>
            )}
        </div>
    );
}

// ---------------------------------------------------------------------------
// Single-prediction lookup
// ---------------------------------------------------------------------------

export function PredictionLookup() {
    const [inputHash, setInputHash] = useState("");
    const [result, setResult] = useState<LookupResult | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const handleLookup = useCallback(async () => {
        const hash = inputHash.trim();
        if (!hash) return;

        setLoading(true);
        setError(null);
        setResult(null);

        try {
            const res = await fetch(
                `/api/integrity/lookup?hash=${encodeURIComponent(hash)}`,
                { cache: "no-store" }
            );
            if (!res.ok) {
                const body = await res.json().catch(() => ({}));
                setError(body.error ?? `HTTP ${res.status}`);
            } else {
                const data: LookupResult = await res.json();
                setResult(data);
            }
        } catch {
            setError("Network error — please try again.");
        } finally {
            setLoading(false);
        }
    }, [inputHash]);

    const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
        if (e.key === "Enter") {
            void handleLookup();
        }
    };

    return (
        <div className="space-y-4">
            {/* Input row */}
            <div className="flex gap-3">
                <input
                    type="text"
                    value={inputHash}
                    onChange={(e) => setInputHash(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder="Enter a prediction_hash (64-character hex string)"
                    className="flex-1 rounded-xl border border-zinc-700 bg-zinc-900 px-4 py-3 font-mono text-sm text-zinc-200 placeholder-zinc-600 focus:border-emerald-500/50 focus:outline-none focus:ring-1 focus:ring-emerald-500/30"
                    spellCheck={false}
                    autoComplete="off"
                />
                <button
                    onClick={() => void handleLookup()}
                    disabled={loading || !inputHash.trim()}
                    className="flex items-center gap-2 rounded-xl bg-emerald-500 px-5 py-3 text-sm font-semibold text-black hover:bg-emerald-400 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                    {loading ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                        <Search className="w-4 h-4" />
                    )}
                    Verify
                </button>
            </div>

            {/* Error */}
            {error && (
                <div className="flex items-start gap-2 rounded-xl border border-red-500/20 bg-red-500/5 px-4 py-3 text-sm text-red-400">
                    <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
                    <span>{error}</span>
                </div>
            )}

            {/* Result */}
            {result && !error && (
                <div
                    className={`rounded-2xl border p-6 space-y-4 ${
                        result.found
                            ? "border-emerald-500/30 bg-emerald-500/5"
                            : "border-zinc-700 bg-zinc-900/50"
                    }`}
                >
                    {result.found ? (
                        <>
                            <div className="flex items-center gap-2">
                                <ShieldCheck className="w-5 h-5 text-emerald-400 shrink-0" />
                                <span className="text-sm font-semibold text-emerald-400">
                                    Hash found in ledger
                                </span>
                                {result.chain_position != null && (
                                    <span className="ml-auto text-xs font-mono text-zinc-500">
                                        #{result.chain_position.toLocaleString()} in chain
                                    </span>
                                )}
                            </div>

                            <div className="grid sm:grid-cols-2 gap-3 text-sm">
                                {result.pundit_name && (
                                    <div className="rounded-lg border border-zinc-800 bg-zinc-950/60 px-4 py-3 space-y-0.5">
                                        <p className="text-[11px] font-mono uppercase tracking-widest text-zinc-500">
                                            Pundit
                                        </p>
                                        <p className="text-zinc-200 font-semibold">
                                            {result.pundit_name}
                                        </p>
                                    </div>
                                )}
                                {result.claim_category && (
                                    <div className="rounded-lg border border-zinc-800 bg-zinc-950/60 px-4 py-3 space-y-0.5">
                                        <p className="text-[11px] font-mono uppercase tracking-widest text-zinc-500">
                                            Category
                                        </p>
                                        <p className="text-zinc-200 capitalize">
                                            {result.claim_category.replace(/_/g, " ")}
                                        </p>
                                    </div>
                                )}
                                {result.season_year && (
                                    <div className="rounded-lg border border-zinc-800 bg-zinc-950/60 px-4 py-3 space-y-0.5">
                                        <p className="text-[11px] font-mono uppercase tracking-widest text-zinc-500">
                                            Season
                                        </p>
                                        <p className="text-zinc-200">{result.season_year}</p>
                                    </div>
                                )}
                                {result.ingestion_timestamp && (
                                    <div className="rounded-lg border border-zinc-800 bg-zinc-950/60 px-4 py-3 space-y-0.5">
                                        <p className="text-[11px] font-mono uppercase tracking-widest text-zinc-500">
                                            Recorded at
                                        </p>
                                        <p className="text-zinc-200">
                                            {formatTimestamp(result.ingestion_timestamp)}
                                        </p>
                                    </div>
                                )}
                            </div>

                            {result.extracted_claim && (
                                <div className="rounded-lg border border-zinc-800 bg-zinc-950/60 px-4 py-3 space-y-1">
                                    <p className="text-[11px] font-mono uppercase tracking-widest text-zinc-500">
                                        Prediction summary
                                    </p>
                                    <p className="text-zinc-300 text-sm leading-relaxed">
                                        {result.extracted_claim}
                                    </p>
                                </div>
                            )}

                            {result.chain_hash && (
                                <div className="space-y-1">
                                    <p className="text-[11px] font-mono uppercase tracking-widest text-zinc-500">
                                        Chain hash at this position
                                    </p>
                                    <div className="flex items-center rounded-lg border border-zinc-800 bg-zinc-950 px-4 py-2">
                                        <code className="font-mono text-xs text-emerald-300 break-all flex-1">
                                            {result.chain_hash}
                                        </code>
                                        <CopyButton text={result.chain_hash} />
                                    </div>
                                </div>
                            )}

                            {result.source_url && (
                                <a
                                    href={result.source_url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="inline-flex items-center gap-1.5 text-xs text-emerald-400 hover:text-emerald-300 transition-colors"
                                >
                                    View original source
                                    <svg
                                        xmlns="http://www.w3.org/2000/svg"
                                        className="w-3 h-3"
                                        fill="none"
                                        viewBox="0 0 24 24"
                                        stroke="currentColor"
                                        strokeWidth={2}
                                    >
                                        <path
                                            strokeLinecap="round"
                                            strokeLinejoin="round"
                                            d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6M15 3h6m0 0v6m0-6L10 14"
                                        />
                                    </svg>
                                </a>
                            )}
                        </>
                    ) : (
                        <div className="flex items-center gap-3">
                            <ShieldAlert className="w-5 h-5 text-zinc-400 shrink-0" />
                            <div>
                                <p className="text-sm font-semibold text-zinc-300">
                                    Hash not found in ledger
                                </p>
                                <p className="text-xs text-zinc-500 mt-0.5">
                                    This prediction hash does not exist in the immutable ledger.
                                    Verify the hash is correct, or this prediction may have
                                    been entered before the chain was initialized.
                                </p>
                            </div>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}
