"use client";

import * as React from "react";
import { Search, Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { cn } from "@/lib/utils";
import type { PunditSearchResult } from "@/app/api/search/pundits/route";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface PunditSearchBarProps {
    placeholder?: string;
    onSelect?: (pundit: PunditSearchResult) => void;
    className?: string;
    autoFocus?: boolean;
}

// ---------------------------------------------------------------------------
// Avatar/initials helper
// ---------------------------------------------------------------------------

function PunditAvatar({ name, avatarUrl }: { name: string; avatarUrl?: string }) {
    const initials = name
        .split(" ")
        .slice(0, 2)
        .map((w) => w[0] ?? "")
        .join("")
        .toUpperCase();

    if (avatarUrl) {
        return (
            // eslint-disable-next-line @next/next/no-img-element
            <img
                src={avatarUrl}
                alt={name}
                className="w-8 h-8 rounded-full object-cover shrink-0"
            />
        );
    }

    return (
        <div
            className="w-8 h-8 rounded-full bg-emerald-900/60 border border-emerald-700/40 flex items-center justify-center shrink-0"
            aria-hidden="true"
        >
            <span className="text-[10px] font-mono font-bold text-emerald-400">{initials}</span>
        </div>
    );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function PunditSearchBar({
    placeholder = "Search pundits...",
    onSelect,
    className,
    autoFocus = false,
}: PunditSearchBarProps) {
    const router = useRouter();
    const [query, setQuery] = React.useState("");
    const [results, setResults] = React.useState<PunditSearchResult[]>([]);
    const [loading, setLoading] = React.useState(false);
    const [open, setOpen] = React.useState(false);
    const [activeIndex, setActiveIndex] = React.useState(-1);

    const inputRef = React.useRef<HTMLInputElement>(null);
    const listRef = React.useRef<HTMLUListElement>(null);
    const containerRef = React.useRef<HTMLDivElement>(null);
    const debounceRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);
    const abortRef = React.useRef<AbortController | null>(null);

    const comboId = React.useId();
    const listboxId = `${comboId}-listbox`;
    const optionId = (i: number) => `${comboId}-option-${i}`;

    // Debounced search
    React.useEffect(() => {
        if (debounceRef.current) clearTimeout(debounceRef.current);

        if (query.length < 2) {
            setResults([]);
            setOpen(false);
            setLoading(false);
            return;
        }

        debounceRef.current = setTimeout(async () => {
            // Cancel in-flight request
            if (abortRef.current) abortRef.current.abort();
            abortRef.current = new AbortController();

            setLoading(true);
            try {
                const res = await fetch(
                    `/api/search/pundits?q=${encodeURIComponent(query)}`,
                    { signal: abortRef.current.signal }
                );
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const data = await res.json();
                const items: PunditSearchResult[] = data.results ?? [];
                setResults(items);
                setOpen(true);
                setActiveIndex(-1);
            } catch (err: unknown) {
                if (err instanceof Error && err.name === "AbortError") return;
                console.error("[PunditSearchBar] Fetch error:", err);
                setResults([]);
            } finally {
                setLoading(false);
            }
        }, 300);

        return () => {
            if (debounceRef.current) clearTimeout(debounceRef.current);
        };
    }, [query]);

    // Close dropdown when clicking outside
    React.useEffect(() => {
        const handler = (e: MouseEvent) => {
            if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
                setOpen(false);
            }
        };
        document.addEventListener("mousedown", handler);
        return () => document.removeEventListener("mousedown", handler);
    }, []);

    const handleSelect = React.useCallback(
        (pundit: PunditSearchResult) => {
            setOpen(false);
            setQuery("");
            setResults([]);
            if (onSelect) {
                onSelect(pundit);
            } else {
                router.push(`/ledger/${encodeURIComponent(pundit.slug)}`);
            }
        },
        [onSelect, router]
    );

    const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
        if (!open) return;

        if (e.key === "ArrowDown") {
            e.preventDefault();
            setActiveIndex((prev) => Math.min(results.length - 1, prev + 1));
        } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setActiveIndex((prev) => Math.max(-1, prev - 1));
        } else if (e.key === "Enter") {
            e.preventDefault();
            if (activeIndex >= 0 && results[activeIndex]) {
                handleSelect(results[activeIndex]);
            }
        } else if (e.key === "Escape") {
            e.preventDefault();
            setOpen(false);
            setActiveIndex(-1);
            // Keep value in input — just close dropdown
        }
    };

    const showEmpty = open && !loading && query.length >= 2 && results.length === 0;

    return (
        <div ref={containerRef} className={cn("relative", className)}>
            {/* Input */}
            <div className="relative flex items-center">
                <Search className="absolute left-3 h-4 w-4 text-zinc-500 pointer-events-none" />
                {loading && (
                    <Loader2 className="absolute right-3 h-4 w-4 text-zinc-500 animate-spin pointer-events-none" />
                )}
                <input
                    ref={inputRef}
                    type="search"
                    role="combobox"
                    aria-expanded={open}
                    aria-controls={listboxId}
                    aria-activedescendant={activeIndex >= 0 ? optionId(activeIndex) : undefined}
                    aria-label="Search pundits"
                    autoComplete="off"
                    autoFocus={autoFocus}
                    value={query}
                    placeholder={placeholder}
                    onChange={(e) => setQuery(e.target.value)}
                    onFocus={() => {
                        if (results.length > 0) setOpen(true);
                    }}
                    onKeyDown={handleKeyDown}
                    className={cn(
                        "w-full rounded-lg border border-zinc-800 bg-zinc-950 pl-9 pr-9 py-2 text-sm text-white",
                        "placeholder:text-zinc-500 focus:outline-none focus:ring-2 focus:ring-emerald-500/40 focus:border-emerald-500/50",
                        "transition-colors"
                    )}
                />
            </div>

            {/* Dropdown */}
            {(open && (results.length > 0 || showEmpty)) && (
                <ul
                    ref={listRef}
                    id={listboxId}
                    role="listbox"
                    aria-label="Pundit search results"
                    className="absolute z-50 mt-1 w-full rounded-lg border border-zinc-800 bg-zinc-950 shadow-xl overflow-hidden"
                >
                    {results.map((pundit, idx) => {
                        const accuracyPct = Math.round(pundit.accuracy * 100);
                        const isActive = idx === activeIndex;
                        return (
                            <li
                                key={pundit.id}
                                id={optionId(idx)}
                                role="option"
                                aria-selected={isActive}
                                className={cn(
                                    "flex items-center gap-3 px-4 py-2.5 cursor-pointer transition-colors",
                                    isActive
                                        ? "bg-zinc-800 border-l-2 border-emerald-500"
                                        : "hover:bg-zinc-900 border-l-2 border-transparent"
                                )}
                                onMouseDown={(e) => {
                                    // prevent blur-before-click
                                    e.preventDefault();
                                    handleSelect(pundit);
                                }}
                                onMouseEnter={() => setActiveIndex(idx)}
                            >
                                <PunditAvatar name={pundit.name} avatarUrl={pundit.avatarUrl} />
                                <div className="flex-1 min-w-0">
                                    <div
                                        className={cn(
                                            "text-sm font-semibold truncate transition-colors",
                                            isActive ? "text-emerald-400" : "text-white"
                                        )}
                                    >
                                        {pundit.name}
                                    </div>
                                    <div className="text-[10px] font-mono text-zinc-500 mt-0.5">
                                        {pundit.domain}
                                    </div>
                                </div>
                                <div className="shrink-0 text-right">
                                    <div
                                        className={cn(
                                            "text-sm font-mono font-semibold tabular-nums",
                                            accuracyPct >= 60
                                                ? "text-emerald-400"
                                                : accuracyPct >= 45
                                                ? "text-yellow-400"
                                                : "text-red-400"
                                        )}
                                    >
                                        {pundit.predictionCount > 0 ? `${accuracyPct}%` : "—"}
                                    </div>
                                    <div className="text-[10px] font-mono text-zinc-600">
                                        {pundit.predictionCount} picks
                                    </div>
                                </div>
                            </li>
                        );
                    })}
                    {showEmpty && (
                        <li
                            role="option"
                            aria-selected={false}
                            className="px-4 py-4 text-sm text-zinc-500 text-center"
                        >
                            No pundits found for &ldquo;{query}&rdquo;
                        </li>
                    )}
                </ul>
            )}
        </div>
    );
}
