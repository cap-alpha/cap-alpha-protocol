"use client";

import { cn } from "@/lib/utils";
import { type WindowBucket } from "@/lib/resolution-window";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type InPlaySortKey =
    | "resolution_proximity"
    | "pundit_accuracy"
    | "most_recent";

export interface InPlayFilterState {
    category: string; // "" = all
    sport: string; // "" = all
    punditQuery: string;
    windowBucket: WindowBucket;
    sort: InPlaySortKey;
}

export const DEFAULT_IN_PLAY_FILTERS: InPlayFilterState = {
    category: "",
    sport: "",
    punditQuery: "",
    windowBucket: "all",
    sort: "resolution_proximity",
};

interface InPlayFiltersProps {
    filters: InPlayFilterState;
    onChange: (filters: InPlayFilterState) => void;
    totalCount?: number;
    className?: string;
}

// ---------------------------------------------------------------------------
// Filter pill data
// ---------------------------------------------------------------------------

const CATEGORY_OPTIONS: Array<{ value: string; label: string }> = [
    { value: "", label: "All" },
    { value: "game_outcome", label: "Game" },
    { value: "player_performance", label: "Player" },
    { value: "trade", label: "Trade" },
    { value: "draft_pick", label: "Draft" },
    { value: "injury", label: "Injury" },
    { value: "contract", label: "Contract" },
];

const SPORT_OPTIONS: Array<{ value: string; label: string }> = [
    { value: "", label: "All" },
    { value: "NFL", label: "NFL" },
    { value: "NBA", label: "NBA" },
    { value: "MLB", label: "MLB" },
];

const WINDOW_OPTIONS: Array<{ value: WindowBucket; label: string }> = [
    { value: "all", label: "All" },
    { value: "week", label: "This Week" },
    { value: "month", label: "This Month" },
    { value: "season", label: "This Season" },
];

const SORT_OPTIONS: Array<{ value: InPlaySortKey; label: string }> = [
    { value: "resolution_proximity", label: "Soonest" },
    { value: "pundit_accuracy", label: "Pundit Accuracy" },
    { value: "most_recent", label: "Most Recent" },
];

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function PillRow<T extends string>({
    label,
    options,
    value,
    onChange,
}: {
    label: string;
    options: Array<{ value: T; label: string }>;
    value: T;
    onChange: (v: T) => void;
}) {
    return (
        <div className="flex items-center gap-1.5 flex-wrap">
            <span className="text-[10px] font-mono uppercase tracking-widest text-zinc-600 mr-0.5 shrink-0">
                {label}:
            </span>
            {options.map((opt) => (
                <button
                    key={opt.value}
                    onClick={() => onChange(opt.value)}
                    className={cn(
                        "px-2.5 py-1 rounded text-[10px] font-mono font-semibold uppercase tracking-wide transition-colors border",
                        value === opt.value
                            ? "bg-amber-500/15 border-amber-500/40 text-amber-400"
                            : "bg-zinc-900 border-zinc-800 text-zinc-500 hover:text-zinc-300 hover:border-zinc-700"
                    )}
                >
                    {opt.label}
                </button>
            ))}
        </div>
    );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

/**
 * Filter + sort bar for the In Play tab.
 *
 * All filtering is client-side in Phase 1; Category, Sport, Pundit are
 * forwarded to the API in Phase 2 when the backend supports them.
 *
 * URL persistence is handled by the parent page via useSearchParams.
 *
 * Issue: #770
 */
export function InPlayFilters({
    filters,
    onChange,
    totalCount,
    className,
}: InPlayFiltersProps) {
    const update = (partial: Partial<InPlayFilterState>) =>
        onChange({ ...filters, ...partial });

    return (
        <div className={cn("flex flex-col gap-3", className)}>
            {/* FTC note + count */}
            <div className="flex items-center justify-between flex-wrap gap-2">
                <p className="text-[10px] font-mono text-zinc-600 max-w-lg">
                    Bet-related links shown only for game-outcome predictions on legal US
                    sportsbooks.
                </p>
                {totalCount !== undefined && (
                    <span className="text-[10px] font-mono text-zinc-500 shrink-0">
                        {totalCount} open pick{totalCount !== 1 ? "s" : ""}
                    </span>
                )}
            </div>

            {/* Category pills */}
            <PillRow
                label="Category"
                options={CATEGORY_OPTIONS}
                value={filters.category}
                onChange={(v) => update({ category: v })}
            />

            {/* Sport pills */}
            <PillRow
                label="Sport"
                options={SPORT_OPTIONS}
                value={filters.sport}
                onChange={(v) => update({ sport: v })}
            />

            {/* Resolution window pills */}
            <PillRow
                label="Resolves"
                options={WINDOW_OPTIONS}
                value={filters.windowBucket}
                onChange={(v) => update({ windowBucket: v })}
            />

            {/* Pundit text filter + sort dropdown — row */}
            <div className="flex items-center gap-3 flex-wrap">
                <div className="flex items-center gap-1.5">
                    <span className="text-[10px] font-mono uppercase tracking-widest text-zinc-600 shrink-0">
                        Pundit:
                    </span>
                    <input
                        type="text"
                        value={filters.punditQuery}
                        onChange={(e) => update({ punditQuery: e.target.value })}
                        placeholder="Search…"
                        className="bg-zinc-900 border border-zinc-800 rounded px-2.5 py-1 text-[11px] font-mono text-white placeholder-zinc-600 focus:outline-none focus:border-amber-500/50 focus:ring-1 focus:ring-amber-500/20 transition-colors w-32"
                    />
                </div>

                <div className="flex items-center gap-1.5">
                    <span className="text-[10px] font-mono uppercase tracking-widest text-zinc-600 shrink-0">
                        Sort:
                    </span>
                    <select
                        value={filters.sort}
                        onChange={(e) =>
                            update({ sort: e.target.value as InPlaySortKey })
                        }
                        className="bg-zinc-900 border border-zinc-800 rounded px-2 py-1 text-[11px] font-mono text-zinc-300 focus:outline-none focus:border-amber-500/50 transition-colors cursor-pointer"
                    >
                        {SORT_OPTIONS.map((opt) => (
                            <option key={opt.value} value={opt.value}>
                                {opt.label}
                            </option>
                        ))}
                    </select>
                </div>
            </div>
        </div>
    );
}
