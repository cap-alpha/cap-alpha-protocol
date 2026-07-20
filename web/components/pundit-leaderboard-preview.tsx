"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Activity, Flame, Snowflake, WifiOff } from "lucide-react";
import { wilsonLowerBound } from "@/lib/wilson";
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

/** Aggregated staff buckets — excluded from individual rankings (distort accuracy). */
const STAFF_BUCKET_IDS = new Set([
    "espn_nfl_staff",
    "pft_staff",
    "athletic_nfl_staff",
]);

// Editorial palette (#1069): numbers in ink by default, navy only for top
// decile, semantic red only under 45% — matches AccuracyBar on /ledger (#1068).
function AccuracyDisplay({ rate }: { rate: number | null }) {
    if (rate === null) return <span className="text-2xl font-bold font-mono text-ink-3 tabular-nums">—</span>;
    const pct = Math.round(rate * 100);
    const colorClass = pct >= 65 ? "text-navy" : pct < 45 ? "text-incorrect" : "text-ink";
    return (
        <AnimatedCounter
            value={pct}
            suffix="%"
            duration={900}
            className={cn("text-2xl font-bold font-mono tabular-nums", colorClass)}
        />
    );
}

function AccuracyBadge({ rate }: { rate: number | null }) {
    if (rate === null) return <span className="text-lg font-bold font-mono text-ink-3 tabular-nums">—</span>;
    const pct = Math.round(rate * 100);
    const colorClass = pct >= 65 ? "text-navy" : pct < 45 ? "text-incorrect" : "text-ink";
    return (
        <AnimatedCounter
            value={pct}
            suffix="%"
            duration={900}
            className={cn("text-lg font-bold font-mono tabular-nums", colorClass)}
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

    // Editorial palette (#1069, ex-#1068 AC): no background/border pill —
    // uppercase mono text only. HOT keeps a warm (gold) cue, COLD a muted
    // ink-3 cue, so the two remain distinguishable without adding another
    // saturated accent color to the page.
    if (pct >= 65) {
        return (
            <span
                title={`${pundit.accuracy_rate_90d !== undefined ? "90-day" : "Career"} accuracy: ${pct}%`}
                className="inline-flex items-center gap-0.5 text-[10px] font-mono font-semibold uppercase tracking-wide text-gold shrink-0"
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
                className="inline-flex items-center gap-0.5 text-[10px] font-mono font-semibold uppercase tracking-wide text-ink-3 shrink-0"
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
            className="block rounded-2xl border border-navy/20 bg-navy/5 p-5 hover:bg-navy/8 transition-colors"
        >
            <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                        <span className="font-mono text-xs font-bold text-gold">#1</span>
                        <span className="text-[10px] font-mono uppercase tracking-widest text-navy/70">Top Pundit</span>
                        <HotColdBadge pundit={pundit} />
                    </div>
                    <p className="font-display font-bold text-xl text-ink truncate">{pundit.pundit_name}</p>
                    <p className="text-xs font-mono text-ink-2 mt-1">
                        {pundit.resolved_predictions} picks · verified
                    </p>
                </div>
                <div className="shrink-0 text-right">
                    <AccuracyDisplay rate={pundit.accuracy_rate} />
                    <p className="text-[10px] font-mono text-ink-3 mt-0.5">accuracy</p>
                </div>
            </div>
            {pct !== null && (
                <div className="mt-4 w-full h-1 rounded-full bg-editorial-border overflow-hidden">
                    <div
                        className="h-full rounded-full bg-navy transition-all duration-700"
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
 *
 * Volume floor: pundits with fewer than MIN_PICKS graded predictions are hidden
 * so that a 1/1 (100%) outlier cannot top the leaderboard over a 9/10 (90%) pundit.
 *
 * Sort key: Wilson score lower bound at 95% CI — not raw accuracy_rate.
 * Wilson LB penalises small samples: 1/1 → ~0.025, 9/10 → ~0.55, 99/100 → ~0.94.
 * The user-facing columns (accuracy_rate, pick count) are unchanged.
 */
const MIN_PICKS = 5;

function processRawPundits(raw: PunditStat[]): PunditStat[] {
    const filtered = raw.filter(
        (p) =>
            !STAFF_BUCKET_IDS.has(p.pundit_id) &&
            p.resolved_predictions >= MIN_PICKS &&
            p.accuracy_rate !== null
    );
    filtered.sort((a, b) => {
        const wbA = wilsonLowerBound(a.correct_predictions, a.resolved_predictions);
        const wbB = wilsonLowerBound(b.correct_predictions, b.resolved_predictions);
        return wbB - wbA;
    });
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
        pundits: processRawPundits((data.pundits || []).map(toPunditStat)),
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
        ? processRawPundits(initialPundits.map(toPunditStat))
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
                        // Retry also failed — surface the error state; clear stale tab data.
                        setPundits([]);
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

    // Editorial palette (#1069): matches RankBadge on /ledger (#1068) — rank 1
    // gets the kept editorial gold accent, everything else is neutral ink.
    const rankColor = (idx: number) =>
        idx === 0 ? "text-gold"
        : idx <= 2 ? "text-ink"
        : "text-ink-3";

    return (
        <div className="space-y-4">
            {/* Sport filter pills */}
            <div className="flex items-center gap-2">
                <span className="text-[10px] font-mono uppercase tracking-widest text-ink-3 mr-1 hidden sm:inline">
                    Sport:
                </span>
                {SPORTS.map((s) => (
                    <button
                        key={s}
                        onClick={() => setActiveSport(s)}
                        className={cn(
                            "px-3 py-1 min-h-[44px] inline-flex items-center justify-center rounded text-xs font-mono font-semibold uppercase tracking-wide transition-colors border",
                            activeSport === s
                                ? "bg-navy/10 border-navy/40 text-navy"
                                : "bg-editorial-card border-editorial-border text-ink-2 hover:text-ink"
                        )}
                        aria-pressed={activeSport === s}
                    >
                        {s}
                    </button>
                ))}
            </div>

            {fetchState === "loading" ? (
                <div className="flex items-center justify-center h-40">
                    <div className="flex items-center gap-2 text-ink-2">
                        <Activity className="w-4 h-4 animate-pulse" />
                        <span className="text-sm font-mono">Loading ledger…</span>
                    </div>
                </div>
            ) : fetchState === "error" ? (
                <div className="flex items-center justify-center h-40">
                    <div className="flex flex-col items-center gap-3 text-center px-4">
                        <WifiOff className="w-5 h-5 text-ink-3" />
                        <p className="text-sm font-mono text-ink-2">
                            Data temporarily unavailable.
                        </p>
                        <div className="flex flex-wrap items-center justify-center gap-x-3 gap-y-1 text-xs font-mono">
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
                                className="text-navy hover:text-accent-editorial-light underline underline-offset-2 transition-colors"
                            >
                                Try again
                            </button>
                            <span className="text-ink-3" aria-hidden="true">
                                ·
                            </span>
                            <Link
                                href="/status"
                                className="text-navy hover:text-accent-editorial-light underline underline-offset-2 transition-colors"
                            >
                                System status
                            </Link>
                        </div>
                    </div>
                </div>
            ) : pundits.length === 0 ? (
                <div className="rounded-xl border border-editorial-border bg-editorial-card py-12 text-center text-sm">
                    <p className="text-ink-2">No scored pundits for this sport yet.</p>
                    <p className="mt-2 text-xs text-ink-3">
                        Check{" "}
                        <Link
                            href="/status"
                            className="text-navy hover:text-accent-editorial-light underline underline-offset-2"
                        >
                            /status
                        </Link>{" "}
                        for pipeline health.
                    </p>
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
                                    className="flex items-center gap-3 rounded-xl border border-editorial-border bg-editorial-card px-4 py-3 hover:border-navy/30 transition-colors"
                                >
                                    <span className={cn("font-mono text-sm font-bold w-5 shrink-0 tabular-nums", rankColor(i + 1))}>
                                        {i + 2}
                                    </span>
                                    <span className="font-semibold text-ink flex-1 truncate text-sm">{p.pundit_name}</span>
                                    <AccuracyBadge rate={p.accuracy_rate} />
                                    <HotColdBadge pundit={p} />
                                    <span className="text-xs font-mono text-ink-3 shrink-0">{p.resolved_predictions} picks</span>
                                </Link>
                            ))}
                    </div>

                    {/* Desktop: full table — top 10 */}
                    <div className="hidden sm:block space-y-2">
                        {pundits.map((p, idx) => (
                            <HoverableRow
                                key={p.pundit_id}
                                className="flex items-center gap-4 rounded-xl border border-editorial-border bg-editorial-card px-5 py-4"
                            >
                                {/* Rank */}
                                <span className={cn(
                                    "font-mono text-base font-bold w-6 shrink-0 tabular-nums",
                                    rankColor(idx)
                                )}>
                                    {idx + 1}
                                </span>

                                {/* Name — linked */}
                                <Link
                                    href={`/ledger/${encodeURIComponent(p.pundit_id)}`}
                                    className="font-semibold text-ink flex-1 truncate hover:text-navy transition-colors"
                                >
                                    {p.pundit_name}
                                </Link>

                                {/* Hot/cold badge */}
                                <HotColdBadge pundit={p} />

                                {/* Accuracy — large, colored */}
                                <AccuracyBadge rate={p.accuracy_rate} />

                                {/* Pick count */}
                                <span className="text-sm font-mono text-ink-2 shrink-0 w-24 text-right">
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
                    className="inline-flex items-center gap-1.5 min-h-[44px] text-sm font-semibold text-navy hover:text-accent-editorial-light transition-colors"
                >
                    View full ledger →
                </Link>
            </div>

            {/* Methodology disclaimer — context for what "accuracy" means here. #993 */}
            {pundits.length > 0 && (
                <p className="pt-2 text-center text-[11px] leading-relaxed text-ink-3 max-w-2xl mx-auto">
                    Accuracy = predictions resolved CORRECT ÷ total resolved (VOID excluded).
                    Some entries aggregate multiple writers under a publication byline; individual writers may differ.
                    Click any name to see the underlying claims and how each was resolved.
                </p>
            )}
        </div>
    );
}
