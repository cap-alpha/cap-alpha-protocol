"use client";

import { Calendar, Flag, Clock } from "lucide-react";
import { type ResolutionWindow } from "@/lib/resolution-window";
import { cn } from "@/lib/utils";

interface ResolutionChipProps {
    window: ResolutionWindow;
    className?: string;
}

/**
 * Renders a single-line resolution window chip for pending predictions.
 *
 * - exact_date → calendar icon + date label
 * - event → flag icon + event name · est. date
 * - season → year badge "Season YYYY"
 * - fuzzy → clock icon + hint (de-emphasized)
 *
 * Issue: #770
 */
export function ResolutionChip({ window, className }: ResolutionChipProps) {
    switch (window.kind) {
        case "exact_date":
            return (
                <span
                    className={cn(
                        "inline-flex items-center gap-1.5 text-[11px] font-mono text-amber-400",
                        className
                    )}
                >
                    <Calendar className="w-3 h-3 shrink-0" />
                    {window.label}
                </span>
            );

        case "event": {
            const dateStr = window.estDate
                ? formatShortDate(window.estDate)
                : null;
            return (
                <span
                    className={cn(
                        "inline-flex items-center gap-1.5 text-[11px] font-mono text-amber-400",
                        className
                    )}
                >
                    <Flag className="w-3 h-3 shrink-0" />
                    By {window.eventName}
                    {dateStr && (
                        <span className="text-zinc-500"> · {dateStr}</span>
                    )}
                </span>
            );
        }

        case "season":
            return (
                <span
                    className={cn(
                        "inline-flex items-center gap-1.5 text-[11px] font-mono text-zinc-400",
                        className
                    )}
                >
                    <span className="bg-zinc-800 border border-zinc-700 rounded px-1.5 py-0.5 text-[10px] uppercase tracking-wide">
                        Season {window.year}
                    </span>
                </span>
            );

        case "fuzzy":
            return (
                <span
                    className={cn(
                        "inline-flex items-center gap-1.5 text-[11px] font-mono text-zinc-600",
                        className
                    )}
                >
                    <Clock className="w-3 h-3 shrink-0" />
                    {window.hint || "Resolution TBD"}
                </span>
            );
    }
}

/** Format ISO date string as "Nov 4, 2025" */
function formatShortDate(iso: string): string | null {
    try {
        const d = new Date(iso);
        if (isNaN(d.getTime())) return null;
        // Force UTC to avoid timezone shift on the date
        const utc = new Date(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate());
        return utc.toLocaleDateString("en-US", {
            month: "short",
            day: "numeric",
            year: "numeric",
        });
    } catch {
        return null;
    }
}
