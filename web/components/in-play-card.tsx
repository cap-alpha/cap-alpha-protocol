"use client";

import Link from "next/link";
import { ExternalLink, ArrowRight, Bell } from "lucide-react";
import { cn } from "@/lib/utils";
import { AffiliateCta } from "@/components/affiliate-cta";
import { PredictionShareButton } from "@/components/prediction-share-button";
import { PredictionOutcomeStamp } from "@/components/prediction-outcome-stamp";
import { ResolutionChip } from "@/components/resolution-chip";
import { deriveResolutionWindow, type PredictionResolutionInput } from "@/lib/resolution-window";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface InPlayPrediction {
    pundit_name: string;
    pundit_id: string;
    extracted_claim: string | null;
    raw_assertion_text?: string | null;
    claim_category: string;
    sport: string;
    season_year: number | null;
    target_player_id?: string | null;
    target_player_name?: string | null;
    target_team?: string | null;
    prediction_hash_short: string;
    ingestion_timestamp: string;
    source_published_at?: string | null;
    source_url?: string | null;
    resolution_status: string | null;
    /** resolved_at is present on recently-resolved picks (24h window) */
    resolved_at?: string | null;
    /** Overall accuracy rate for the pundit (0-1) */
    accuracy_rate?: number | null;
    /** Category-specific accuracy, e.g. { trade: 0.57 } */
    accuracy_by_category?: Record<string, number> | null;
    /** Total resolved predictions for this pundit in this category */
    category_resolved_count?: number | null;
    quality_score?: number | null;
}

interface InPlayCardProps {
    prediction: InPlayPrediction;
    onOpenDrawer?: (prediction: InPlayPrediction) => void;
    className?: string;
    /** Whether the current user follows this pundit (used for + Follow ghost button, #769) */
    isFollowingPundit?: boolean;
    /** Called when user clicks + Follow on a card — parent handles auth redirect or follow action */
    onFollowPundit?: (punditId: string, punditName: string) => void;
}

// ---------------------------------------------------------------------------
// Local helpers
// ---------------------------------------------------------------------------

// Editorial palette (#1068): numbers in ink by default, navy only for top
// decile, semantic red only under 45% — matches AccuracyBar in
// app/ledger/page.tsx.
function AccuracyBadge({ rate }: { rate: number | null | undefined }) {
    if (rate === null || rate === undefined) {
        return (
            <span className="text-[10px] font-mono text-ink-3 tabular-nums">—%</span>
        );
    }
    const pct = Math.round(rate * 100);
    const colorClass =
        pct >= 65
            ? "text-white border-navy bg-navy"
            : pct < 45
            ? "text-incorrect border-incorrect/30 bg-[rgba(185,28,28,0.08)]"
            : "text-ink border-editorial-border bg-editorial-card";
    return (
        <span
            className={cn(
                "inline-flex items-center text-[10px] font-mono font-semibold tabular-nums border rounded px-1.5 py-0.5",
                colorClass
            )}
        >
            {pct}% acc
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
        <span className="text-[10px] font-mono uppercase tracking-wide text-ink-2 bg-editorial-card border border-editorial-border rounded px-1.5 py-0.5">
            {label[category] ?? category}
        </span>
    );
}

function SportPill({ sport }: { sport: string }) {
    return (
        <span className="text-[10px] font-mono uppercase tracking-wide text-ink-3 bg-editorial-card border border-editorial-border rounded px-1.5 py-0.5">
            {sport}
        </span>
    );
}

/** Format relative time: "3 days ago", "2 hours ago" */
function relativeTime(ts: string | null | undefined): string | null {
    if (!ts) return null;
    try {
        const diff = Date.now() - new Date(ts).getTime();
        const minute = 60 * 1000;
        const hour = 60 * minute;
        const day = 24 * hour;
        if (diff < minute) return "just now";
        if (diff < hour) return `${Math.floor(diff / minute)}m ago`;
        if (diff < day) return `${Math.floor(diff / hour)}h ago`;
        if (diff < 30 * day) return `${Math.floor(diff / day)}d ago`;
        return new Date(ts).toLocaleDateString("en-US", {
            month: "short",
            day: "numeric",
        });
    } catch {
        return null;
    }
}

/** Convert a player name to a URL slug for /player/[id] routes */
function slugifyPlayer(name: string): string {
    return encodeURIComponent(name.toLowerCase().replace(/\s+/g, "-"));
}

/** Initials avatar — matches pundit-card.tsx style */
function InitialsAvatar({ name }: { name: string }) {
    const parts = name.trim().split(/\s+/);
    const initials =
        parts.length >= 2
            ? `${parts[0][0]}${parts[parts.length - 1][0]}`
            : parts[0]?.slice(0, 2) ?? "?";
    return (
        <div
            className="w-8 h-8 rounded-full bg-editorial-border border border-editorial-border flex items-center justify-center shrink-0"
            aria-hidden
        >
            <span className="text-[10px] font-bold font-mono text-ink-2 uppercase">
                {initials.toUpperCase()}
            </span>
        </div>
    );
}

/** Category-specific accuracy display */
function CategoryAccuracy({
    category,
    accuracyByCategory,
    categoryResolvedCount,
}: {
    category: string;
    accuracyByCategory?: Record<string, number> | null;
    categoryResolvedCount?: number | null;
}) {
    const CATEGORY_LABELS: Record<string, string> = {
        game_outcome: "Games",
        player_performance: "Player",
        trade: "Trades",
        draft_pick: "Draft",
        injury: "Injury",
        contract: "Contracts",
    };
    const label = CATEGORY_LABELS[category] ?? category;
    const rate = accuracyByCategory?.[category];
    if (rate === undefined || rate === null) return null;

    const pct = Math.round(rate * 100);
    // --pos/--warn/--neg are now stored as HSL triples (#1113 fix), so raw
    // `var(--x)` is not a valid standalone color value anymore — must wrap.
    const colorStyle =
        pct >= 60
            ? { color: "hsl(var(--pos))" }
            : pct >= 45
            ? { color: "hsl(var(--warn))" }
            : { color: "hsl(var(--neg))" };

    return (
        <span className="text-[10px] font-mono text-ink-2">
            {categoryResolvedCount ? `${categoryResolvedCount} on ` : ""}
            {label}{" "}
            <span className="font-semibold" style={colorStyle}>
                {pct}%
            </span>
        </span>
    );
}

// ---------------------------------------------------------------------------
// Main InPlayCard component
// ---------------------------------------------------------------------------

/**
 * Card for a single pending (or just-resolved) prediction in the In Play tab.
 *
 * Layout: pundit header → claim text → resolution chip + category accuracy
 * → source → affiliate CTA (game_outcome only) → share / details buttons.
 *
 * Issue: #770
 */
export function InPlayCard({
    prediction,
    onOpenDrawer,
    className,
    isFollowingPundit = false,
    onFollowPundit,
}: InPlayCardProps) {
    const claimText =
        prediction.extracted_claim || prediction.raw_assertion_text || "—";

    const resolutionInput: PredictionResolutionInput = {
        claim_category: prediction.claim_category,
        sport: prediction.sport,
        season_year: prediction.season_year,
        raw_assertion_text: prediction.raw_assertion_text,
        target_team: prediction.target_team,
    };
    const resolutionWindow = deriveResolutionWindow(resolutionInput);

    const sourceTimestamp = prediction.source_published_at || prediction.ingestion_timestamp;
    const relTime = relativeTime(sourceTimestamp);

    // Determine if this is a recently-resolved card (show overlay, don't hide yet)
    const isJustResolved =
        prediction.resolution_status === "CORRECT" ||
        prediction.resolution_status === "INCORRECT";

    const outcomeStamp =
        prediction.resolution_status === "CORRECT"
            ? ("correct" as const)
            : prediction.resolution_status === "INCORRECT"
            ? ("incorrect" as const)
            : null;

    return (
        <div
            className={cn(
                "relative flex flex-col gap-3 rounded-xl border bg-editorial-card p-4 transition-colors hover:border-pending/40",
                isJustResolved
                    ? "border-editorial-border"
                    : "border-pending/25 bg-[rgba(146,64,14,0.03)]",
                className
            )}
            data-testid="in-play-card"
            data-category={prediction.claim_category}
            data-prediction-id={prediction.prediction_hash_short}
        >
            {/* Just-resolved overlay stamp */}
            {outcomeStamp && (
                <div className="absolute top-3 right-3">
                    <PredictionOutcomeStamp outcome={outcomeStamp} size="sm" />
                </div>
            )}

            {/* --- Header: pundit name + accuracy badge --- */}
            <div className="flex items-center gap-2 min-w-0">
                <InitialsAvatar name={prediction.pundit_name} />
                <div className="flex flex-col min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-2">
                        <Link
                            href={`/ledger/${prediction.pundit_id}`}
                            className="text-sm font-semibold text-ink hover:text-pending transition-colors truncate"
                        >
                            {prediction.pundit_name}
                        </Link>
                        <AccuracyBadge rate={prediction.accuracy_rate} />
                    </div>
                    <div className="flex items-center gap-1.5 mt-0.5 flex-wrap">
                        <CategoryPill category={prediction.claim_category} />
                        <SportPill sport={prediction.sport} />
                    </div>
                </div>
            </div>

            {/* --- Claim text (hero) --- */}
            <p className="text-sm text-ink leading-relaxed line-clamp-3">
                {claimText}
            </p>

            {/* --- Entity chips: link player/team names to their pages --- */}
            {(prediction.target_player_name || prediction.target_player_id || prediction.target_team) && (
                <div className="flex items-center gap-1.5 flex-wrap">
                    {(prediction.target_player_name || prediction.target_player_id) && (
                        <Link
                            href={`/player/${slugifyPlayer(prediction.target_player_name ?? prediction.target_player_id!)}`}
                            className="inline-flex items-center text-[10px] font-mono font-semibold text-amber-500/80 hover:text-amber-400 border border-amber-500/20 hover:border-amber-500/40 bg-amber-500/5 rounded px-1.5 py-0.5 transition-colors"
                        >
                            {prediction.target_player_name ?? prediction.target_player_id}
                        </Link>
                    )}
                    {prediction.target_team && (
                        <Link
                            href={`/team/${encodeURIComponent(prediction.target_team)}`}
                            className="inline-flex items-center text-[10px] font-mono font-semibold text-sky-500/80 hover:text-sky-400 border border-sky-500/20 hover:border-sky-500/40 bg-sky-500/5 rounded px-1.5 py-0.5 transition-colors"
                        >
                            {prediction.target_team}
                        </Link>
                    )}
                </div>
            )}

            {/* --- Resolution window + category accuracy --- */}
            <div className="flex flex-col gap-1">
                <ResolutionChip window={resolutionWindow} />
                <CategoryAccuracy
                    category={prediction.claim_category}
                    accuracyByCategory={prediction.accuracy_by_category}
                    categoryResolvedCount={prediction.category_resolved_count}
                />
            </div>

            {/* --- Source link --- */}
            {prediction.source_url && (
                <a
                    href={prediction.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-[10px] font-mono text-ink-3 hover:text-ink-2 transition-colors truncate"
                >
                    <ExternalLink className="w-2.5 h-2.5 shrink-0" />
                    <span className="truncate">
                        Source
                        {relTime ? ` · said ${relTime}` : ""}
                    </span>
                </a>
            )}
            {!prediction.source_url && relTime && (
                <span className="text-[10px] font-mono text-ink-3">
                    said {relTime}
                </span>
            )}

            {/* --- Affiliate CTA — game_outcome predictions only --- */}
            {prediction.claim_category === "game_outcome" && (
                <AffiliateCta
                    platform="draftkings"
                    context="ledger"
                    className="!py-2 !px-3"
                />
            )}

            {/* --- Footer: share + follow + details --- */}
            <div className="flex items-center justify-between gap-2 pt-1 border-t border-editorial-border">
                <div className="flex items-center gap-2">
                    <PredictionShareButton
                        predictionId={prediction.prediction_hash_short}
                    />
                    {/* + Follow ghost button — only when not already following (#769) */}
                    {!isFollowingPundit && onFollowPundit && (
                        <button
                            onClick={() => onFollowPundit(prediction.pundit_id, prediction.pundit_name)}
                            className="inline-flex items-center gap-1 text-[10px] font-mono text-pending/80 hover:text-pending border border-pending/25 hover:border-pending/50 rounded px-1.5 py-0.5 transition-colors"
                            aria-label={`Follow ${prediction.pundit_name} — get notified when predictions resolve`}
                            title={`Get an email when ${prediction.pundit_name}'s predictions resolve. Free.`}
                        >
                            <Bell className="w-2.5 h-2.5" />
                            + Follow
                        </button>
                    )}
                </div>
                {onOpenDrawer && (
                    <button
                        onClick={() => onOpenDrawer(prediction)}
                        className="inline-flex items-center gap-1 text-[10px] font-mono text-ink-2 hover:text-ink transition-colors"
                    >
                        Details
                        <ArrowRight className="w-2.5 h-2.5" />
                    </button>
                )}
            </div>
        </div>
    );
}
