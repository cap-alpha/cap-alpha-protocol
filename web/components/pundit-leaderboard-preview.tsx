"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Activity, Flame, Snowflake, WifiOff } from "lucide-react";
import { cn } from "@/lib/utils";
import { AnimatedCounter } from "@/components/animated-counter";
import { HoverableRow } from "@/components/hoverable-row";

interface PunditStat {
    pundit_name: string;
    pundit_id: string;
    total_predictions: number;
    resolved_predictions: number;
    correct_predictions: number;
    incorrect_predictions: number;
    accuracy_rate: number | null;
    avg_brier_score: number | null;
    /** Optional 90-day rolling accuracy — populated once #831 lands */
    accuracy_rate_90d?: number | null;
}

const SPORTS = ["ALL", "NFL", "NBA", "MLB"] as const;
type Sport = (typeof SPORTS)[number];

function AccuracyDisplay({ rate }: { rate: number | null }) {
    if (rate === null) return <span className="text-2xl font-black font-mono text-zinc-600 tabular-nums">—</span>;
    const pct = Math.round(rate * 100);
    const colorClass = pct >= 60 ? "text-emerald-400" : pct >= 45 ? "text-yellow-400" : "text-red-400";
    return (
        <AnimatedCounter
            value={pct}
            suffix="%"
            duration={900}
            className={cn("text-2xl font-black font-mono tabular-nums", colorClass)}
        />
    );
}

function AccuracyBadge({ rate }: { rate: number | null }) {
    if (rate === null) return <span className="text-lg font-black font-mono text-zinc-600 tabular-nums">—</span>;
    const pct = Math.round(rate * 100);
    const colorClass = pct >= 60 ? "text-emerald-400" : pct >= 45 ? "text-yellow-400" : "text-red-400";
    return (
        <AnimatedCounter
            value={pct}
            suffix="%"
            duration={900}
            className={cn("text-lg font-black font-mono tabular-nums", colorClass)}
        />
    );
}

/**
 * Hot/cold rolling accuracy badge.
 * Uses 90-day accuracy if available (post-#831), otherwise derives a trend
 * signal by comparing career accuracy to the 60% accuracy threshold as a proxy.
 *
 * - Hot (🔥): pundit is on a strong run (>= 65% career or 90d accuracy >= 65%)
 * - Cold (❄): pundit is struggling (< 45% career or 90d accuracy < 45%)
 * - null: within normal range — no badge shown
 */
function HotColdBadge({ pundit }: { pundit: PunditStat }) {
    // Prefer 90-day accuracy when available (#831); fall back to career
    const rateToUse = pundit.accuracy_rate_90d ?? pundit.accuracy_rate;
    if (rateToUse === null) return null;
    const pct = Math.round(rateToUse * 100);

    if (pct >= 65) {
        return (
            <span
                title={`${pundit.accuracy_rate_90d !== undefined ? "90-day" : "Career"} accuracy: ${pct}%`}
                className="inline-flex items-center gap-0.5 rounded px-1.5 py-0.5 text-[10px] font-mono font-semibold bg-orange-500/15 text-orange-400 border border-orange-500/25 shrink-0"
                aria-label="Hot — above-average accuracy"
            >
                <Flame className="w-2.5 h-2.5" />
                HOT
            </span>
        );
    }
    if (pct < 45) {
        return (
            <span
                title={`${pundit.accuracy_rate_90d !== undefined ? "90-day" : "Career"} accuracy: ${pct}%`}
                className="inline-flex items-center gap-0.5 rounded px-1.5 py-0.5 text-[10px] font-mono font-semibold bg-blue-500/15 text-blue-400 border border-blue-500/25 shrink-0"
                aria-label="Cold — below-average accuracy"
            >
                <Snowflake className="w-2.5 h-2.5" />
                COLD
            </span>
        );
    }
    return null;
}

/** Featured card for #1 ranked pundit — shown on mobile above fold */
function FeaturedPunditCard({ pundit }: { pundit: PunditStat }) {
    const pct = pundit.accuracy_rate !== null ? Math.round(pundit.accuracy_rate * 100) : null;
    return (
        <Link
            href={`/ledger/${encodeURIComponent(pundit.pundit_id)}`}
            className="block rounded-2xl border border-emerald-500/30 bg-emerald-500/5 p-5 hover:bg-emerald-500/8 transition-colors"
        >
            <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                        <span className="font-mono text-xs font-black text-yellow-400">#1</span>
                        <span className="text-[10px] font-mono uppercase tracking-widest text-emerald-400/70">Top Pundit</span>
                        <HotColdBadge pundit={pundit} />
                    </div>
                    <p className="font-display font-black text-xl text-white truncate">{pundit.pundit_name}</p>
                    <p className="text-xs font-mono text-zinc-500 mt-1">
                        {pundit.resolved_predictions} picks · verified
                    </p>
                </div>
                <div className="shrink-0 text-right">
                    <AccuracyDisplay rate={pundit.accuracy_rate} />
                    <p className="text-[10px] font-mono text-zinc-600 mt-0.5">accuracy</p>
                </div>
            </div>
            {pct !== null && (
                <div className="mt-4 w-full h-1 rounded-full bg-zinc-800 overflow-hidden">
                    <div
                        className="h-full rounded-full bg-emerald-500 transition-all duration-700"
                        style={{ width: `${pct}%` }}
                    />
                </div>
            )}
        </Link>
    );
}

interface PunditLeaderboardPreviewProps {
    /**
     * Default sport filter — "ALL" | "NFL" | "NBA" | "MLB".
     * Defaults to "NFL" per issue #883 (topic-agnostic leaderboard with NFL as primary).
     */
    sport?: string;
    /**
     * Pre-fetched pundit data from the server component (SSR).
     * When provided, the component renders immediately without a loading spinner
     * on first contentful paint.  The useEffect re-fetches only when the user
     * switches the sport filter tab.
     */
    initialPundits?: Record<string, unknown>[];
    /**
     * When true, data is served from the static snapshot (backend unavailable).
     * Lowers the resolved-picks threshold from 5 → 3 and renders a staleness badge.
     * Tracks issue #960.
     */
    fallback?: boolean;
}

/** Normalise the raw backend/SSR record into a typed PunditStat. */
function toPunditStat(p: Record<string, unknown>): PunditStat {
    return p as unknown as PunditStat;
}

/** Filter + sort helper — shared between SSR seed and client refetch paths.
 *  When `isFallback` is true, the resolved-picks threshold is lowered from 5 → 3
 *  so all 13 snapshot pundits render (largest corpus has 5 picks).
 */
function processRawPundits(raw: PunditStat[], isFallback = false): PunditStat[] {
    const minPicks = isFallback ? 3 : 5;
    const filtered = raw.filter(
        (p) => p.resolved_predictions >= minPicks && p.accuracy_rate !== null
    );
    filtered.sort((a, b) => (b.accuracy_rate ?? 0) - (a.accuracy_rate ?? 0));
    return filtered.slice(0, 10);
}

const FETCH_TIMEOUT_MS = 10_000;

interface FetchPunditsResult {
    pundits: PunditStat[];
    fallback: boolean;
}

/**
 * Three-state fetch helper.
 *   - resolves with { pundits, fallback } on success (fallback=true when snapshot served)
 *   - rejects on network error, non-ok HTTP status, or timeout
 */
async function fetchPundits(sport: Sport, signal?: AbortSignal): Promise<FetchPunditsResult> {
    const params = new URLSearchParams({ limit: "20", sort: "accuracy" });
    if (sport !== "ALL") {
        params.set("sport", sport.toLowerCase());
    }
    const res = await fetch(`/api/ledger/pundits?${params.toString()}`, { signal });
    if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
    }
    const data = await res.json();
    const isFallback = !!data.fallback;
    return {
        pundits: processRawPundits((data.pundits || []).map(toPunditStat), isFallback),
        fallback: isFallback,
    };
}

export function PunditLeaderboardPreview({
    sport: sportProp = "NFL",
    initialPundits,
    fallback = false,
}: PunditLeaderboardPreviewProps) {
    const defaultSport: Sport = SPORTS.includes(sportProp as Sport) ? (sportProp as Sport) : "NFL";
    const [activeSport, setActiveSport] = useState<Sport>(defaultSport);

    // Seed from SSR data when available so the first render is not empty.
    const seedPundits = initialPundits
        ? processRawPundits(initialPundits.map(toPunditStat), fallback)
        : [];
    const [pundits, setPundits] = useState<PunditStat[]>(seedPundits);
    // Track whether currently-displayed data is from the snapshot fallback.
    const [isFallback, setIsFallback] = useState<boolean>(fallback);

    /**
     * Three distinct UI states — never conflate them:
     *   "idle"    — SSR data is present; no background fetch needed on first paint
     *   "loading" — fetch in-flight (initial load or sport switch)
     *   "error"   — fetch failed and retry also failed; show inline message
     */
    type FetchState = "idle" | "loading" | "error";
    const [fetchState, setFetchState] = useState<FetchState>(
        seedPundits.length > 0 ? "idle" : "loading"
    );

    // Track whether a retry is currently scheduled so we don't double-schedule.
    const retryScheduled = useRef(false);

    useEffect(() => {
        // Skip the initial client fetch for the default sport when SSR data was
        // provided — the page already rendered with real data.  Re-fetch only
        // when the user switches to a different sport tab.
        if (activeSport === defaultSport && seedPundits.length > 0) {
            return;
        }

        let cancelled = false;
        retryScheduled.current = false;

        setFetchState("loading");

        const attemptFetch = (isRetry: boolean) => {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
            fetchPundits(activeSport, controller.signal)
                .then((result) => {
                    clearTimeout(timeoutId);
                    if (cancelled) return;
                    setPundits(result.pundits);
                    setIsFallback(result.fallback);
                    setFetchState("idle");
                })
                .catch((err) => {
                    clearTimeout(timeoutId);
                    if (cancelled) return;
                    console.error(`[Leaderboard] Fetch${isRetry ? " retry" : ""} error:`, err);
                    if (!isRetry && !retryScheduled.current) {
                        // First attempt failed — schedule a single retry after 3 s.
                        retryScheduled.current = true;
                        setTimeout(() => {
                            if (!cancelled) attemptFetch(true);
                        }, 3000);
                    } else {
                        // Retry also failed — surface the error state.
                        setFetchState("error");
                    }
                });
        };

        attemptFetch(false);

        return () => {
            cancelled = true;
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [activeSport]);

    /**
     * Featured pundit = highest-accuracy pundit with >= 20 resolved picks.
     * Falls back to #1 in the list if no pundit meets the threshold (sparse data).
     */
    const featuredPundit = pundits.find((p) => p.resolved_predictions >= 20) ?? pundits[0];

    const rankColor = (idx: number) =>
        idx === 0 ? "text-yellow-400"
        : idx === 1 ? "text-zinc-300"
        : idx === 2 ? "text-orange-400"
        : "text-zinc-600";

    return (
        <div className="space-y-4">
            {/* Staleness badge — shown when data is from the snapshot fallback (issue #960).
                Uses reactive isFallback state so it updates correctly on sport-tab switches. */}
            {isFallback && (
                <div className="flex items-center gap-2 px-3 py-2 rounded-lg border border-amber-500/20 bg-amber-500/5 text-amber-400/80">
                    <span className="w-1.5 h-1.5 rounded-full bg-amber-400/60 shrink-0" />
                    <span className="text-[11px] font-mono tracking-wide">
                        Data archive · Apr 2025 · refresh paused
                    </span>
                </div>
            )}

            {/* Sport filter pills */}
            <div className="flex items-center gap-2">
                <span className="text-[10px] font-mono uppercase tracking-widest text-zinc-600 mr-1 hidden sm:inline">
                    Sport:
                </span>
                {SPORTS.map((s) => (
                    <button
                        key={s}
                        onClick={() => setActiveSport(s)}
                        className={cn(
                            "px-3 py-1 min-h-[44px] inline-flex items-center justify-center rounded text-xs font-mono font-semibold uppercase tracking-wide transition-colors border",
                            activeSport === s
                                ? "bg-emerald-500/15 border-emerald-500/40 text-emerald-400"
                                : "bg-zinc-900 border-zinc-800 text-zinc-500 hover:text-zinc-300 hover:border-zinc-700"
                        )}
                        aria-pressed={activeSport === s}
                    >
                        {s}
                    </button>
                ))}
            </div>

            {fetchState === "loading" ? (
                <div className="flex items-center justify-center h-40">
                    <div className="flex items-center gap-2 text-zinc-400">
                        <Activity className="w-4 h-4 animate-pulse" />
                        <span className="text-sm font-mono">Loading ledger…</span>
                    </div>
                </div>
            ) : fetchState === "error" ? (
                <div className="flex items-center justify-center h-40">
                    <div className="flex flex-col items-center gap-3 text-center px-4">
                        <WifiOff className="w-5 h-5 text-zinc-600" />
                        <p className="text-sm font-mono text-zinc-500">
                            Ledger temporarily unavailable.
                        </p>
                        <button
                            onClick={() => {
                                const controller = new AbortController();
                                const timeoutId = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
                                setFetchState("loading");
                                fetchPundits(activeSport, controller.signal)
                                    .then((result) => {
                                        clearTimeout(timeoutId);
                                        setPundits(result.pundits);
                                        setIsFallback(result.fallback);
                                        setFetchState("idle");
                                    })
                                    .catch(() => {
                                        clearTimeout(timeoutId);
                                        setFetchState("error");
                                    });
                            }}
                            className="text-xs font-mono text-emerald-500 hover:text-emerald-400 underline underline-offset-2 transition-colors"
                        >
                            Try again
                        </button>
                    </div>
                </div>
            ) : pundits.length === 0 ? (
                <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 py-12 text-center text-zinc-600 text-sm">
                    No pundit data yet — pipeline populating soon.
                </div>
            ) : (
                <>
                    {/* Mobile: featured #1 card (>= 20 picks) + compact list 2–10 */}
                    <div className="sm:hidden space-y-3">
                        {featuredPundit && <FeaturedPunditCard pundit={featuredPundit} />}
                        {pundits
                            .filter((p) => p.pundit_id !== featuredPundit?.pundit_id)
                            .map((p, i) => (
                                <Link
                                    key={p.pundit_id}
                                    href={`/ledger/${encodeURIComponent(p.pundit_id)}`}
                                    className="flex items-center gap-3 rounded-xl border border-zinc-800 bg-zinc-900/50 px-4 py-3 hover:border-zinc-700 transition-colors"
                                >
                                    <span className={cn("font-mono text-sm font-black w-5 shrink-0 tabular-nums", rankColor(i + 1))}>
                                        {i + 2}
                                    </span>
                                    <span className="font-semibold text-white flex-1 truncate text-sm">{p.pundit_name}</span>
                                    <AccuracyBadge rate={p.accuracy_rate} />
                                    <HotColdBadge pundit={p} />
                                    <span className="text-xs font-mono text-zinc-600 shrink-0">{p.resolved_predictions} picks</span>
                                </Link>
                            ))}
                    </div>

                    {/* Desktop: full table — top 10 */}
                    <div className="hidden sm:block space-y-2">
                        {pundits.map((p, idx) => (
                            <HoverableRow
                                key={p.pundit_id}
                                className="flex items-center gap-4 rounded-xl border border-zinc-800 bg-zinc-900/50 px-5 py-4"
                            >
                                {/* Rank */}
                                <span className={cn(
                                    "font-mono text-base font-black w-6 shrink-0 tabular-nums",
                                    rankColor(idx)
                                )}>
                                    {idx + 1}
                                </span>

                                {/* Name — linked */}
                                <Link
                                    href={`/ledger/${encodeURIComponent(p.pundit_id)}`}
                                    className="font-semibold text-white flex-1 truncate hover:text-emerald-400 transition-colors"
                                >
                                    {p.pundit_name}
                                </Link>

                                {/* Hot/cold badge */}
                                <HotColdBadge pundit={p} />

                                {/* Accuracy — large, colored */}
                                <AccuracyBadge rate={p.accuracy_rate} />

                                {/* Pick count */}
                                <span className="text-sm font-mono text-zinc-500 shrink-0 w-24 text-right">
                                    {p.resolved_predictions} picks
                                </span>
                            </HoverableRow>
                        ))}
                    </div>
                </>
            )}

            {/* "View full ledger" link */}
            <div className="pt-1 text-center">
                <Link
                    href="/ledger"
                    className="inline-flex items-center gap-1.5 min-h-[44px] text-sm font-semibold text-emerald-400 hover:text-emerald-300 transition-colors"
                >
                    View full ledger →
                </Link>
            </div>
        </div>
    );
}
