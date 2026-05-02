"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import {
    Shield,
    CheckCircle2,
    XCircle,
    Clock,
    ArrowRight,
    Activity,
    ExternalLink,
    X,
    ChevronDown,
    ChevronUp,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { PredictionShareButton } from "@/components/prediction-share-button";
import { PunditSearchBar } from "@/components/pundit-search-bar";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface PunditStat {
    pundit_name: string;
    pundit_id: string;
    sport: string;
    total_predictions: number;
    resolved_predictions: number;
    correct_predictions: number;
    incorrect_predictions: number;
    accuracy_rate: number | null;
    avg_brier_score: number | null;
    avg_weighted_score: number | null;
    game_outcome_count: number;
    player_performance_count: number;
    trade_count: number;
    draft_pick_count: number;
    first_seen: string | null;
    last_seen: string | null;
}

interface RecentPrediction {
    pundit_name: string;
    pundit_id: string;
    extracted_claim: string;
    claim_category: string;
    season_year: number | null;
    target_player_id: string | null;
    target_team: string | null;
    sport: string;
    prediction_hash_short: string;
    ingestion_timestamp: string;
    // publication/original date from source (may be absent)
    source_published_at?: string | null;
    resolution_status: string | null;
    brier_score: number | null;
    weighted_score: number | null;
    source_url?: string | null;
    raw_assertion_text?: string | null;
}

// ---------------------------------------------------------------------------
// Small helpers
// ---------------------------------------------------------------------------

function AccuracyBar({ rate }: { rate: number | null }) {
    if (rate === null)
        return <span className="text-xs text-zinc-600 font-mono tabular-nums">—</span>;
    const pct = Math.round(rate * 100);
    const color =
        pct >= 60 ? "bg-emerald-500" : pct >= 45 ? "bg-yellow-500" : "bg-red-500";
    const textColor =
        pct >= 60
            ? "text-emerald-400"
            : pct >= 45
            ? "text-yellow-400"
            : "text-red-400";
    return (
        <div className="flex items-center gap-2">
            <div className="w-16 h-1.5 rounded-full bg-zinc-800 overflow-hidden">
                <div
                    className={cn("h-full rounded-full transition-all", color)}
                    style={{ width: `${pct}%` }}
                />
            </div>
            <span className={cn("text-xs font-mono font-semibold tabular-nums", textColor)}>
                {pct}%
            </span>
        </div>
    );
}

function BrierBadge({ score }: { score: number | null }) {
    if (score === null)
        return <span className="text-xs text-zinc-600 font-mono">—</span>;
    const color =
        score <= 0.1
            ? "text-emerald-400"
            : score <= 0.2
            ? "text-yellow-400"
            : "text-red-400";
    return (
        <span className={cn("text-xs font-mono tabular-nums font-semibold", color)}>
            {score.toFixed(3)}
        </span>
    );
}

function StatusBadge({ status }: { status: string | null }) {
    if (status === "CORRECT")
        return (
            <span className="inline-flex items-center gap-1 rounded-full bg-emerald-900/40 px-2 py-0.5 text-[10px] font-semibold text-emerald-400 ring-1 ring-emerald-500/30">
                <CheckCircle2 className="w-2.5 h-2.5" /> Correct
            </span>
        );
    if (status === "INCORRECT")
        return (
            <span className="inline-flex items-center gap-1 rounded-full bg-red-900/40 px-2 py-0.5 text-[10px] font-semibold text-red-400 ring-1 ring-red-500/30">
                <XCircle className="w-2.5 h-2.5" /> Wrong
            </span>
        );
    return (
        <span className="inline-flex items-center gap-1 rounded-full bg-zinc-800 px-2 py-0.5 text-[10px] font-semibold text-zinc-400 ring-1 ring-zinc-700">
            <Clock className="w-2.5 h-2.5" /> Pending
        </span>
    );
}

function CategoryPill({ category }: { category: string }) {
    const label: Record<string, string> = {
        game_outcome: "Game",
        player_performance: "Player",
        trade: "Trade",
        draft_pick: "Draft",
        injury: "Injury",
        contract: "Contract",
    };
    return (
        <span className="text-[10px] font-mono uppercase tracking-wide text-zinc-500 bg-zinc-900 border border-zinc-800 rounded px-1.5 py-0.5">
            {label[category] ?? category}
        </span>
    );
}

function RankBadge({ rank }: { rank: number }) {
    const color =
        rank === 1
            ? "text-yellow-400"
            : rank === 2
            ? "text-zinc-300"
            : rank === 3
            ? "text-orange-400"
            : "text-zinc-600";
    return (
        <span className={cn("font-mono text-sm font-black w-5 shrink-0 tabular-nums", color)}>
            {rank}
        </span>
    );
}

/** Format a timestamp as "Mon D, YYYY" */
function fmtDate(ts: string | null | undefined): string | null {
    if (!ts) return null;
    try {
        return new Date(ts).toLocaleDateString("en-US", {
            month: "short",
            day: "numeric",
            year: "numeric",
        });
    } catch {
        return null;
    }
}

/** Format a timestamp with time as a long string */
function fmtDateTime(ts: string | null | undefined): string | null {
    if (!ts) return null;
    try {
        return new Date(ts).toLocaleString("en-US", {
            month: "long",
            day: "numeric",
            year: "numeric",
            hour: "numeric",
            minute: "2-digit",
        });
    } catch {
        return null;
    }
}

// ---------------------------------------------------------------------------
// Dual-timestamp display: "received [date]" + optional "said ~[date]"
// ---------------------------------------------------------------------------

function ClaimTimestamps({
    ingestion_timestamp,
    source_published_at,
}: {
    ingestion_timestamp: string | null | undefined;
    source_published_at?: string | null;
}) {
    const received = fmtDate(ingestion_timestamp);
    const said = fmtDate(source_published_at);
    return (
        <span className="text-[10px] font-mono text-zinc-600 flex flex-wrap gap-2">
            {received && <span>received {received}</span>}
            {said && said !== received && <span>said ~{said}</span>}
        </span>
    );
}

// ---------------------------------------------------------------------------
// Slide-out drawer (details panel)
// ---------------------------------------------------------------------------

function PredictionDrawer({
    prediction,
    allSources,
    onClose,
}: {
    prediction: RecentPrediction;
    /** All members of the group — used to show all source links side-by-side */
    allSources: RecentPrediction[];
    onClose: () => void;
}) {
    const receivedDate = fmtDateTime(prediction.ingestion_timestamp);
    const saidDate = fmtDate(prediction.source_published_at);

    // Close on Escape
    useEffect(() => {
        const handler = (e: KeyboardEvent) => {
            if (e.key === "Escape") onClose();
        };
        window.addEventListener("keydown", handler);
        return () => window.removeEventListener("keydown", handler);
    }, [onClose]);

    return (
        <>
            {/* Backdrop — semi-transparent, ledger remains visible */}
            <div
                className="fixed inset-0 z-40 bg-black/50"
                onClick={onClose}
                aria-hidden="true"
            />

            {/* Drawer panel */}
            <div
                className="fixed top-0 right-0 bottom-0 z-50 w-full max-w-md flex flex-col bg-zinc-950 border-l border-zinc-800 shadow-2xl overflow-y-auto"
                role="dialog"
                aria-modal="true"
                aria-label="Prediction details"
            >
                {/* Drawer header */}
                <div className="flex items-start justify-between p-5 border-b border-zinc-800 sticky top-0 bg-zinc-950 z-10">
                    <div className="flex items-center gap-2">
                        <Shield className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                        <span className="text-[10px] font-mono uppercase tracking-widest text-emerald-400">
                            Sealed Prediction
                        </span>
                    </div>
                    <button
                        onClick={onClose}
                        className="text-zinc-600 hover:text-zinc-300 transition-colors"
                        aria-label="Close details"
                    >
                        <X className="w-4 h-4" />
                    </button>
                </div>

                {/* Drawer body */}
                <div className="p-5 space-y-5 flex-1">
                    {/* Claim text */}
                    <div>
                        <p className="text-base font-semibold text-white leading-snug">
                            {prediction.extracted_claim}
                        </p>
                        {prediction.raw_assertion_text &&
                            prediction.raw_assertion_text !== prediction.extracted_claim && (
                                <p className="mt-2 text-xs text-zinc-500 italic leading-snug">
                                    Original: &ldquo;{prediction.raw_assertion_text}&rdquo;
                                </p>
                            )}
                    </div>

                    {/* Status + Brier */}
                    <div className="flex items-center gap-3">
                        <StatusBadge status={prediction.resolution_status} />
                        {prediction.brier_score !== null && (
                            <span className="text-xs font-mono text-zinc-500">
                                Brier: <BrierBadge score={prediction.brier_score} />
                            </span>
                        )}
                    </div>

                    {/* Metadata grid */}
                    <div className="grid grid-cols-2 gap-3 text-xs font-mono">
                        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 px-3 py-2">
                            <div className="text-zinc-600 uppercase tracking-wide text-[9px] mb-0.5">Pundit</div>
                            <Link
                                href={`/ledger/${encodeURIComponent(prediction.pundit_id)}`}
                                className="text-zinc-200 hover:text-emerald-400 transition-colors font-semibold"
                                onClick={onClose}
                            >
                                {prediction.pundit_name}
                            </Link>
                        </div>
                        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 px-3 py-2">
                            <div className="text-zinc-600 uppercase tracking-wide text-[9px] mb-0.5">Category</div>
                            <CategoryPill category={prediction.claim_category} />
                        </div>
                        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 px-3 py-2">
                            <div className="text-zinc-600 uppercase tracking-wide text-[9px] mb-0.5">Sport</div>
                            <span className="text-zinc-300">{prediction.sport || "—"}</span>
                        </div>
                        {prediction.season_year && (
                            <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 px-3 py-2">
                                <div className="text-zinc-600 uppercase tracking-wide text-[9px] mb-0.5">Season</div>
                                <span className="text-zinc-300">{prediction.season_year}</span>
                            </div>
                        )}

                        {/* Dual timestamps */}
                        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 px-3 py-2 col-span-2">
                            <div className="text-zinc-600 uppercase tracking-wide text-[9px] mb-1">Timestamps</div>
                            <div className="space-y-1">
                                {receivedDate && (
                                    <div>
                                        <span className="text-zinc-600">received </span>
                                        <span className="text-zinc-300">{receivedDate}</span>
                                    </div>
                                )}
                                {saidDate && (
                                    <div>
                                        <span className="text-zinc-600">said ~</span>
                                        <span className="text-zinc-300">{saidDate}</span>
                                    </div>
                                )}
                            </div>
                        </div>
                    </div>

                    {/* All source links side-by-side */}
                    {allSources.some((m) => m.source_url) && (
                        <div>
                            <div className="text-zinc-600 uppercase tracking-wide text-[9px] font-mono mb-2">Sources</div>
                            <div className="flex flex-wrap gap-2">
                                {allSources
                                    .filter((m) => m.source_url)
                                    .map((m, i) => (
                                        <a
                                            key={m.prediction_hash_short}
                                            href={m.source_url!}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            className="inline-flex items-center gap-1 rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-[10px] font-mono text-zinc-400 hover:text-emerald-400 hover:border-emerald-500/40 transition-colors"
                                        >
                                            Source {allSources.filter((x) => x.source_url).length > 1 ? i + 1 : ""}{" "}
                                            <ExternalLink className="w-2.5 h-2.5" />
                                        </a>
                                    ))}
                            </div>
                        </div>
                    )}

                    {/* Hash */}
                    <div className="pt-1">
                        <span className="text-[10px] font-mono text-zinc-700">
                            #{prediction.prediction_hash_short}
                        </span>
                    </div>
                </div>
            </div>
        </>
    );
}

// ---------------------------------------------------------------------------
// Semantic similarity grouping (client-side cosine similarity on word vectors)
// ---------------------------------------------------------------------------
// We use a lightweight TF-IDF-style approach: build word frequency vectors for
// each claim and compute cosine similarity. This is "semantic" in the sense
// that word overlap is meaning-relevant, and far better than raw prefix matching.
// True LLM embeddings would require a backend round-trip; this gives good
// grouping with zero latency for the front-end.

function tokenize(text: string): string[] {
    return text
        .toLowerCase()
        .replace(/[^a-z0-9\s]/g, " ")
        .split(/\s+/)
        .filter((t) => t.length > 2);
}

// Common stop words to ignore in similarity
const STOP_WORDS = new Set([
    "the", "and", "for", "are", "but", "not", "you", "all", "any", "can",
    "had", "her", "was", "one", "our", "out", "day", "get", "has", "him",
    "his", "how", "its", "may", "new", "now", "old", "see", "two", "way",
    "who", "did", "with", "this", "that", "they", "will", "from", "been",
    "have", "said", "each", "she", "which", "their", "would", "make", "like",
    "into", "time", "has", "look", "more", "write", "than", "first", "over",
    "also", "very", "when", "come", "here", "just", "know", "long", "your",
    "around", "another", "came", "could", "much", "should", "these", "those",
]);

function buildVector(tokens: string[]): Map<string, number> {
    const vec = new Map<string, number>();
    for (const t of tokens) {
        if (!STOP_WORDS.has(t)) {
            vec.set(t, (vec.get(t) ?? 0) + 1);
        }
    }
    return vec;
}

function cosineSimilarity(a: Map<string, number>, b: Map<string, number>): number {
    if (a.size === 0 || b.size === 0) return 0;
    let dot = 0;
    let normA = 0;
    let normB = 0;
    for (const [term, count] of a) {
        normA += count * count;
        const bCount = b.get(term);
        if (bCount !== undefined) dot += count * bCount;
    }
    for (const [, count] of b) normB += count * count;
    if (normA === 0 || normB === 0) return 0;
    return dot / (Math.sqrt(normA) * Math.sqrt(normB));
}

/** Threshold above which two claims are "semantically equivalent" */
const SIMILARITY_THRESHOLD = 0.72;

interface PredictionGroup {
    key: string;
    representative: RecentPrediction;
    /** Same pundit, semantically equivalent, ingested at ~same time (same-source pickup) */
    sameTimeSources: RecentPrediction[];
    /** Same pundit, semantically equivalent, different timestamps (pundit said it again) */
    repeatOccurrences: RecentPrediction[];
}

function groupPredictions(predictions: RecentPrediction[]): PredictionGroup[] {
    // Pre-compute vectors
    const vectors = predictions.map((p) =>
        buildVector(tokenize(p.extracted_claim ?? ""))
    );

    // NOTE: The 48h same-time window is measured relative to the *first* (representative)
    // prediction in each group, not each occurrence independently. A multi-occurrence
    // prediction where occurrence 2 has its own same-time pickups within 48h of occurrence 2
    // (but >48h from the representative) will not be clustered correctly — those pickups will
    // appear as additional repeat occurrences. A proper fix would cluster by sorted
    // ingestion time (new bucket when gap > 48h). Deferred for now.
    const groups: PredictionGroup[] = [];
    const assigned = new Set<string>();

    for (let i = 0; i < predictions.length; i++) {
        const pred = predictions[i];
        if (assigned.has(pred.prediction_hash_short)) continue;

        assigned.add(pred.prediction_hash_short);

        const rawIngestMs = pred.ingestion_timestamp
            ? new Date(pred.ingestion_timestamp).getTime()
            : null;
        // Normalize NaN (invalid timestamps) to null so time-window comparisons
        // behave correctly instead of silently treating NaN as "present".
        const ingestMs = rawIngestMs !== null && Number.isFinite(rawIngestMs) ? rawIngestMs : null;

        const sameTimeSources: RecentPrediction[] = [];
        const repeatOccurrences: RecentPrediction[] = [];

        for (let j = i + 1; j < predictions.length; j++) {
            const other = predictions[j];
            if (assigned.has(other.prediction_hash_short)) continue;
            if (other.pundit_id !== pred.pundit_id) continue;

            const sim = cosineSimilarity(vectors[i], vectors[j]);
            if (sim < SIMILARITY_THRESHOLD) continue;

            // Determine same-time vs repeat
            const rawOtherIngestMs = other.ingestion_timestamp
                ? new Date(other.ingestion_timestamp).getTime()
                : null;
            const otherIngestMs =
                rawOtherIngestMs !== null && Number.isFinite(rawOtherIngestMs)
                    ? rawOtherIngestMs
                    : null;

            const SAME_TIME_WINDOW_MS = 48 * 60 * 60 * 1000; // 48h
            const isSameTime =
                ingestMs !== null &&
                otherIngestMs !== null &&
                Math.abs(ingestMs - otherIngestMs) <= SAME_TIME_WINDOW_MS;

            if (isSameTime) {
                sameTimeSources.push(other);
            } else {
                repeatOccurrences.push(other);
            }
            assigned.add(other.prediction_hash_short);
        }

        groups.push({
            key: pred.prediction_hash_short,
            representative: pred,
            sameTimeSources,
            repeatOccurrences,
        });
    }

    return groups;
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function LedgerPage() {
    const [pundits, setPundits] = useState<PunditStat[]>([]);
    const [recent, setRecent] = useState<RecentPrediction[]>([]);
    const [loading, setLoading] = useState(true);
    const [sportFilter, setSportFilter] = useState<string>("ALL");
    const [activeTab, setActiveTab] = useState<"leaderboard" | "recent">(
        "leaderboard"
    );
    const [drawerPrediction, setDrawerPrediction] = useState<RecentPrediction | null>(null);
    const [drawerSources, setDrawerSources] = useState<RecentPrediction[]>([]);

    const openDrawer = (prediction: RecentPrediction, sources: RecentPrediction[]) => {
        setDrawerPrediction(prediction);
        setDrawerSources(sources);
    };

    const closeDrawer = () => {
        setDrawerPrediction(null);
        setDrawerSources([]);
    };

    useEffect(() => {
        const sportParam =
            sportFilter !== "ALL" ? `?sport=${sportFilter}` : "";
        Promise.all([
            fetch(`/api/ledger/pundits${sportParam}`).then((r) => r.json()),
            fetch(`/api/ledger/recent?limit=30${sportFilter !== "ALL" ? `&sport=${sportFilter}` : ""}`).then((r) =>
                r.json()
            ),
        ]).then(([punditsData, recentData]) => {
            setPundits(punditsData.pundits || []);
            setRecent(recentData.predictions || []);
        }).catch((err) => {
            console.error("[Ledger] Failed to load data:", err);
        }).finally(() => {
            setLoading(false);
        });
    }, [sportFilter]);

    // Sort leaderboard: resolved first (by accuracy desc), then unresolved (by total desc)
    const sorted = [...pundits].sort((a, b) => {
        const aResolved = a.resolved_predictions > 0;
        const bResolved = b.resolved_predictions > 0;
        if (aResolved && !bResolved) return -1;
        if (!aResolved && bResolved) return 1;
        if (aResolved && bResolved) {
            const accDiff = (b.accuracy_rate ?? 0) - (a.accuracy_rate ?? 0);
            if (accDiff !== 0) return accDiff;
            return (a.avg_brier_score ?? 1) - (b.avg_brier_score ?? 1);
        }
        return b.total_predictions - a.total_predictions;
    });

    const totalPredictions = pundits.reduce((s, p) => s + p.total_predictions, 0);
    const totalResolved = pundits.reduce((s, p) => s + p.resolved_predictions, 0);
    const resolvedFeed = recent.filter(
        (r) => r.resolution_status === "CORRECT" || r.resolution_status === "INCORRECT"
    );

    const SPORTS = ["ALL", "NFL", "NBA", "MLB"];

    return (
        <div className="min-h-screen bg-black text-white">
            {/* Slide-out detail drawer */}
            {drawerPrediction && (
                <PredictionDrawer
                    prediction={drawerPrediction}
                    allSources={drawerSources}
                    onClose={closeDrawer}
                />
            )}

            {/* Header */}
            <div className="border-b border-zinc-900 bg-zinc-950/50">
                <div className="max-w-6xl mx-auto px-4 py-8">
                    <div className="flex items-start justify-between gap-4">
                        <div>
                            <div className="flex items-center gap-2 mb-2">
                                <Shield className="w-4 h-4 text-emerald-400" />
                                <span className="text-xs font-mono uppercase tracking-widest text-emerald-400">
                                    Cryptographically Sealed
                                </span>
                            </div>
                            <h1 className="text-3xl font-black tracking-tight text-white">
                                Pundit Ledger
                            </h1>
                            <p className="mt-1 text-sm text-zinc-400 max-w-lg">
                                Every public sports prediction tracked, scored, and sealed on-chain
                                — so no one can rewrite history.
                            </p>
                        </div>

                        {/* Aggregate stats */}
                        <div className="hidden sm:flex items-center gap-6 text-right shrink-0">
                            <div>
                                <div className="text-2xl font-black font-mono text-white tabular-nums">
                                    {pundits.length}
                                </div>
                                <div className="text-xs text-zinc-500 font-mono">Pundits</div>
                            </div>
                            <div>
                                <div className="text-2xl font-black font-mono text-white tabular-nums">
                                    {totalPredictions.toLocaleString()}
                                </div>
                                <div className="text-xs text-zinc-500 font-mono">Predictions</div>
                            </div>
                            <div>
                                <div className="text-2xl font-black font-mono text-emerald-400 tabular-nums">
                                    {totalResolved.toLocaleString()}
                                </div>
                                <div className="text-xs text-zinc-500 font-mono">Resolved</div>
                            </div>
                        </div>
                    </div>

                    {/* Pundit search — primary navigation */}
                    <div className="mt-6 max-w-md">
                        <PunditSearchBar placeholder="Search pundits..." />
                    </div>

                    {/* Sport filter — applies to both tabs */}
                    <div className="flex items-center gap-2 mt-4">
                        <span className="text-[10px] font-mono uppercase tracking-widest text-zinc-600 mr-1">
                            Sport:
                        </span>
                        {SPORTS.map((s) => (
                            <button
                                key={s}
                                onClick={() => setSportFilter(s)}
                                className={cn(
                                    "px-3 py-1 rounded text-xs font-mono font-semibold uppercase tracking-wide transition-colors border",
                                    sportFilter === s
                                        ? "bg-emerald-500/15 border-emerald-500/40 text-emerald-400"
                                        : "bg-zinc-900 border-zinc-800 text-zinc-500 hover:text-zinc-300 hover:border-zinc-700"
                                )}
                            >
                                {s}
                            </button>
                        ))}
                        {sportFilter !== "ALL" && (
                            <span className="text-[10px] font-mono text-zinc-600 ml-1">
                                — filtering leaderboard &amp; recent predictions
                            </span>
                        )}
                    </div>
                </div>
            </div>

            {/* Tabs */}
            <div className="border-b border-zinc-900">
                <div className="max-w-6xl mx-auto px-4">
                    <div className="flex gap-0">
                        {(["leaderboard", "recent"] as const).map((tab) => (
                            <button
                                key={tab}
                                onClick={() => setActiveTab(tab)}
                                className={cn(
                                    "px-5 py-3 text-sm font-semibold uppercase tracking-wide transition-colors border-b-2",
                                    activeTab === tab
                                        ? "border-emerald-500 text-emerald-400"
                                        : "border-transparent text-zinc-500 hover:text-zinc-300"
                                )}
                            >
                                {tab === "leaderboard" ? "Leaderboard" : `Recent (${resolvedFeed.length})`}
                            </button>
                        ))}
                    </div>
                </div>
            </div>

            {/* Content */}
            <div className="max-w-6xl mx-auto px-4 py-8">
                {loading ? (
                    <div className="flex items-center justify-center h-48 text-zinc-600">
                        <Activity className="w-4 h-4 animate-pulse mr-2" />
                        <span className="font-mono text-sm">Loading ledger…</span>
                    </div>
                ) : (
                    <TabContent
                        activeTab={activeTab}
                        pundits={sorted}
                        recent={recent}
                        onOpenDrawer={openDrawer}
                    />
                )}
            </div>
        </div>
    );
}

// ---------------------------------------------------------------------------
// Tab content — AnimatePresence for cross-fade + slide between tabs
// ---------------------------------------------------------------------------

function TabContent({
    activeTab,
    pundits,
    recent,
    onOpenDrawer,
}: {
    activeTab: "leaderboard" | "recent";
    pundits: PunditStat[];
    recent: RecentPrediction[];
    onOpenDrawer: (p: RecentPrediction, sources: RecentPrediction[]) => void;
}) {
    const shouldReduceMotion = useReducedMotion();

    const variants = shouldReduceMotion
        ? {
              initial: { opacity: 0 },
              animate: { opacity: 1 },
              exit: { opacity: 0 },
          }
        : {
              initial: { opacity: 0, y: 8 },
              animate: { opacity: 1, y: 0 },
              exit: { opacity: 0, y: -8 },
          };

    return (
        <AnimatePresence mode="wait" initial={false}>
            <motion.div
                key={activeTab}
                variants={variants}
                initial="initial"
                animate="animate"
                exit="exit"
                transition={{ duration: 0.2 }}
            >
                {activeTab === "leaderboard" ? (
                    <LeaderboardTab pundits={pundits} />
                ) : (
                    <RecentTab predictions={recent} onOpenDrawer={onOpenDrawer} />
                )}
            </motion.div>
        </AnimatePresence>
    );
}

// ---------------------------------------------------------------------------
// Leaderboard tab
// ---------------------------------------------------------------------------

function LeaderboardTab({ pundits }: { pundits: PunditStat[] }) {
    if (pundits.length === 0) {
        return (
            <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 py-16 text-center text-zinc-500 text-sm">
                No pundit data yet — pipeline populating soon.
            </div>
        );
    }

    return (
        <div className="space-y-2">
            {/* Column headers */}
            <div className="hidden md:grid grid-cols-[32px_1fr_130px_90px_80px_70px_90px_80px] gap-3 px-4 pb-1 text-[10px] font-mono uppercase tracking-widest text-zinc-600">
                <span>#</span>
                <span>Pundit</span>
                <span>Accuracy</span>
                <span className="text-right">Correct</span>
                <span className="text-right">Wrong</span>
                <span className="text-right">Brier ↓</span>
                <span className="text-right">Picks</span>
                <span className="text-right"></span>
            </div>

            {pundits.map((p, idx) => (
                <div
                    key={`${p.pundit_id}-${p.sport}`}
                    className={cn(
                        "rounded-xl border bg-zinc-900/50 px-4 py-3 transition-colors",
                        idx < 3
                            ? "border-zinc-700/70"
                            : "border-zinc-800/60"
                    )}
                >
                    {/* Desktop layout */}
                    <div className="hidden md:grid grid-cols-[32px_1fr_130px_90px_80px_70px_90px_80px] gap-3 items-center">
                        <RankBadge rank={idx + 1} />

                        <div className="min-w-0">
                            {p.pundit_id && p.pundit_id !== "None" ? (
                                <Link
                                    href={`/ledger/${encodeURIComponent(p.pundit_id)}`}
                                    className="font-semibold text-white truncate text-sm hover:text-emerald-400 transition-colors block"
                                >
                                    {p.pundit_name}
                                </Link>
                            ) : (
                                <div className="font-semibold text-white truncate text-sm">
                                    {p.pundit_name}
                                </div>
                            )}
                            <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                                <CategoryBreakdown p={p} />
                            </div>
                        </div>

                        <AccuracyBar rate={p.accuracy_rate} />

                        <span className="text-right text-sm font-mono font-semibold text-emerald-400 tabular-nums">
                            {p.correct_predictions > 0 ? p.correct_predictions : "—"}
                        </span>
                        <span className="text-right text-sm font-mono font-semibold text-red-400 tabular-nums">
                            {p.incorrect_predictions > 0 ? p.incorrect_predictions : "—"}
                        </span>
                        <div className="flex justify-end">
                            <BrierBadge score={p.avg_brier_score} />
                        </div>
                        <span className="text-right text-xs font-mono text-zinc-500 tabular-nums">
                            {p.total_predictions}
                        </span>
                        <div className="flex justify-end">
                            {p.pundit_id && p.pundit_id !== "None" ? (
                                <Link
                                    href={`/ledger/${encodeURIComponent(p.pundit_id)}`}
                                    className="text-[10px] font-mono text-zinc-600 hover:text-emerald-400 transition-colors inline-flex items-center gap-0.5"
                                >
                                    Card <ArrowRight className="w-2.5 h-2.5" />
                                </Link>
                            ) : null}
                        </div>
                    </div>

                    {/* Mobile layout */}
                    <div className="flex md:hidden items-center gap-3">
                        <RankBadge rank={idx + 1} />
                        <div className="flex-1 min-w-0">
                            {p.pundit_id && p.pundit_id !== "None" ? (
                                <Link
                                    href={`/ledger/${encodeURIComponent(p.pundit_id)}`}
                                    className="font-semibold text-white text-sm truncate block hover:text-emerald-400 transition-colors"
                                >
                                    {p.pundit_name}
                                </Link>
                            ) : (
                                <div className="font-semibold text-white text-sm truncate">
                                    {p.pundit_name}
                                </div>
                            )}
                            <AccuracyBar rate={p.accuracy_rate} />
                        </div>
                        <div className="text-right shrink-0">
                            <div className="text-xs font-mono text-zinc-400">
                                {p.total_predictions} picks
                            </div>
                            <div className="flex items-center gap-1.5 justify-end mt-0.5">
                                {p.correct_predictions > 0 && (
                                    <span className="text-xs font-mono text-emerald-400">
                                        ✓{p.correct_predictions}
                                    </span>
                                )}
                                {p.incorrect_predictions > 0 && (
                                    <span className="text-xs font-mono text-red-400">
                                        ✗{p.incorrect_predictions}
                                    </span>
                                )}
                            </div>
                            {p.pundit_id && p.pundit_id !== "None" && (
                                <Link
                                    href={`/ledger/${encodeURIComponent(p.pundit_id)}`}
                                    className="text-[10px] font-mono text-zinc-600 hover:text-emerald-400 transition-colors inline-flex items-center gap-0.5 mt-1"
                                >
                                    Card <ArrowRight className="w-2.5 h-2.5" />
                                </Link>
                            )}
                        </div>
                    </div>
                </div>
            ))}

            <p className="text-xs text-zinc-600 font-mono text-center pt-4">
                Brier score: lower is better (0 = perfect). Ranked by accuracy, then Brier score.
            </p>
        </div>
    );
}

function CategoryBreakdown({ p }: { p: PunditStat }) {
    const cats = [
        { key: "game_outcome_count", label: "Game" },
        { key: "player_performance_count", label: "Player" },
        { key: "trade_count", label: "Trade" },
        { key: "draft_pick_count", label: "Draft" },
    ] as const;

    const nonZero = cats.filter(
        (c) => (p[c.key as keyof PunditStat] as number) > 0
    );
    if (nonZero.length === 0) return null;

    return (
        <>
            {nonZero.map((c) => (
                <span
                    key={c.key}
                    className="text-[10px] font-mono text-zinc-600 leading-none"
                >
                    {c.label}:{" "}
                    <span className="text-zinc-400">
                        {p[c.key as keyof PunditStat] as number}
                    </span>
                </span>
            ))}
        </>
    );
}

// ---------------------------------------------------------------------------
// Recent tab
// ---------------------------------------------------------------------------

function RecentTab({
    predictions,
    onOpenDrawer,
}: {
    predictions: RecentPrediction[];
    onOpenDrawer: (p: RecentPrediction, sources: RecentPrediction[]) => void;
}) {
    const resolved = predictions.filter(
        (p) =>
            p.resolution_status === "CORRECT" || p.resolution_status === "INCORRECT"
    );
    const pending = predictions.filter(
        (p) => !p.resolution_status || p.resolution_status === "PENDING"
    );

    if (predictions.length === 0) {
        return (
            <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 py-16 text-center text-zinc-500 text-sm">
                No recent predictions yet.
            </div>
        );
    }

    const resolvedGroups = groupPredictions(resolved);
    const pendingGroups = groupPredictions(pending);

    return (
        <div className="space-y-6">
            {resolvedGroups.length > 0 && (
                <div>
                    <h3 className="text-xs font-mono uppercase tracking-widest text-zinc-500 mb-3">
                        Recently Resolved
                    </h3>
                    <div className="space-y-2">
                        {resolvedGroups.map((g) => (
                            <PredictionGroupRow
                                key={g.key}
                                group={g}
                                onOpenDrawer={onOpenDrawer}
                            />
                        ))}
                    </div>
                </div>
            )}

            {pendingGroups.length > 0 && (
                <div>
                    <h3 className="text-xs font-mono uppercase tracking-widest text-zinc-500 mb-3">
                        Awaiting Resolution
                    </h3>
                    <div className="space-y-2">
                        {pendingGroups.slice(0, 10).map((g) => (
                            <PredictionGroupRow
                                key={g.key}
                                group={g}
                                onOpenDrawer={onOpenDrawer}
                            />
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}

// ---------------------------------------------------------------------------
// Prediction group row — inline expand + "Details →" button for drawer
// ---------------------------------------------------------------------------

function PredictionGroupRow({
    group,
    onOpenDrawer,
}: {
    group: PredictionGroup;
    onOpenDrawer: (p: RecentPrediction, sources: RecentPrediction[]) => void;
}) {
    const [expanded, setExpanded] = useState(false);
    const { representative: p, sameTimeSources, repeatOccurrences } = group;

    // Sources for the main row's inline links and detail drawer.
    // Only includes the representative + same-time pickups of the same statement.
    // Repeat occurrences are separate rows and carry their own source context.
    const mainRowSources = [p, ...sameTimeSources];
    const hasRepeats = repeatOccurrences.length > 0;

    return (
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 overflow-hidden">
            {/* Main row */}
            <div className="px-4 py-3 flex items-start gap-3">
                <StatusBadge status={p.resolution_status} />
                <div className="flex-1 min-w-0">
                    <p className="text-sm text-white leading-snug line-clamp-2">
                        {p.extracted_claim}
                    </p>
                    <div className="flex items-center gap-3 mt-1.5 flex-wrap">
                        <Link
                            href={`/ledger/${encodeURIComponent(p.pundit_id)}`}
                            className="text-xs font-semibold text-zinc-300 hover:text-emerald-400 transition-colors"
                        >
                            {p.pundit_name}
                        </Link>
                        <CategoryPill category={p.claim_category} />
                        {p.season_year && (
                            <span className="text-[10px] font-mono text-zinc-600">
                                {p.season_year}
                            </span>
                        )}
                        <ClaimTimestamps
                            ingestion_timestamp={p.ingestion_timestamp}
                            source_published_at={p.source_published_at}
                        />
                        {p.brier_score !== null && (
                            <span className="text-[10px] font-mono text-zinc-500">
                                Brier: <BrierBadge score={p.brier_score} />
                            </span>
                        )}
                        {/* Show same-time source links inline (same statement, multiple pickups) */}
                        {mainRowSources
                            .filter((m) => m.source_url)
                            .map((m) => (
                                <a
                                    key={m.prediction_hash_short}
                                    href={m.source_url!}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="text-[10px] font-mono text-zinc-600 hover:text-zinc-400 inline-flex items-center gap-0.5"
                                >
                                    source <ExternalLink className="w-2.5 h-2.5" />
                                </a>
                            ))}
                    </div>
                </div>
                <div className="flex flex-col items-end gap-1.5 shrink-0">
                    {/* Details button → opens drawer */}
                    <button
                        className="inline-flex items-center gap-1 text-[10px] font-mono text-zinc-500 hover:text-emerald-400 transition-colors border border-zinc-800 hover:border-emerald-500/40 rounded px-2 py-0.5"
                        onClick={() => onOpenDrawer(p, mainRowSources)}
                        aria-label="Open details drawer"
                    >
                        Details <ArrowRight className="w-2.5 h-2.5" />
                    </button>
                    {/* Share button */}
                    <PredictionShareButton predictionId={p.prediction_hash_short} />
                    {/* Expand/collapse for repeat occurrences */}
                    {hasRepeats && (
                        <button
                            className="inline-flex items-center gap-0.5 text-[10px] font-mono text-zinc-500 hover:text-zinc-300 transition-colors"
                            onClick={() => setExpanded((v) => !v)}
                            aria-label={expanded ? "Collapse repeat occurrences" : "Show repeat occurrences"}
                        >
                            {repeatOccurrences.length} repeat{repeatOccurrences.length !== 1 ? "s" : ""}
                            {expanded ? (
                                <ChevronUp className="w-2.5 h-2.5" />
                            ) : (
                                <ChevronDown className="w-2.5 h-2.5" />
                            )}
                        </button>
                    )}
                    <span className="text-[10px] font-mono text-zinc-700 hidden sm:block">
                        #{p.prediction_hash_short}
                    </span>
                </div>
            </div>

            {/* Inline expanded summary (one-liner) */}
            {expanded && (
                <div className="border-t border-zinc-800/60 px-4 py-2.5 bg-zinc-900/20">
                    <p className="text-[10px] font-mono text-zinc-500 mb-2 uppercase tracking-wide">
                        {p.pundit_name} said this again on different occasions:
                    </p>
                    <div className="space-y-2">
                        {repeatOccurrences.map((variant) => (
                            <div
                                key={variant.prediction_hash_short}
                                className="flex items-start gap-3 rounded-lg border border-zinc-800/60 bg-zinc-900/30 px-3 py-2"
                            >
                                <StatusBadge status={variant.resolution_status} />
                                <div className="flex-1 min-w-0">
                                    {/* One-liner summary */}
                                    <p className="text-xs text-zinc-300 leading-snug line-clamp-1">
                                        {variant.extracted_claim}
                                    </p>
                                    <div className="flex items-center gap-2 mt-1 flex-wrap">
                                        <ClaimTimestamps
                                            ingestion_timestamp={variant.ingestion_timestamp}
                                            source_published_at={variant.source_published_at}
                                        />
                                        {variant.source_url && (
                                            <a
                                                href={variant.source_url}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                className="text-[10px] font-mono text-zinc-600 hover:text-zinc-400 inline-flex items-center gap-0.5"
                                            >
                                                source <ExternalLink className="w-2.5 h-2.5" />
                                            </a>
                                        )}
                                    </div>
                                </div>
                                <button
                                    className="inline-flex items-center gap-1 text-[10px] font-mono text-zinc-600 hover:text-emerald-400 transition-colors shrink-0"
                                    onClick={() => onOpenDrawer(variant, [variant])}
                                    aria-label="Open details for this occurrence"
                                >
                                    Details <ArrowRight className="w-2.5 h-2.5" />
                                </button>
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}
