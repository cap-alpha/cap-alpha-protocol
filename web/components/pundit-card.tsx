"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, CheckCircle2, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface PunditCardProps {
    punditId: string;
    name: string;
    accuracy: number; // 0-1
    correctCount: number;
    resolvedCount: number;
    totalCount: number;
    featuredPrediction?: {
        text: string;
        outcome: "correct" | "incorrect";
        resolvedAt: string;
    };
    variant: "hof" | "hos";
}

// ---------------------------------------------------------------------------
// Animated accuracy counter
// ---------------------------------------------------------------------------

function AnimatedCounter({ target }: { target: number }) {
    const [display, setDisplay] = useState(0);

    useEffect(() => {
        let start = 0;
        const end = Math.round(target * 100);
        if (start === end) {
            setDisplay(end);
            return;
        }
        const duration = 700; // ms
        const step = Math.ceil((end - start) / (duration / 16));
        const timer = setInterval(() => {
            start += step;
            if (start >= end) {
                setDisplay(end);
                clearInterval(timer);
            } else {
                setDisplay(start);
            }
        }, 16);
        return () => clearInterval(timer);
    }, [target]);

    return <>{display}</>;
}

// ---------------------------------------------------------------------------
// Initials circle avatar
// ---------------------------------------------------------------------------

function InitialsAvatar({
    name,
    variant,
}: {
    name: string;
    variant: "hof" | "hos";
}) {
    const initials = name
        .split(" ")
        .slice(0, 2)
        .map((w) => w[0]?.toUpperCase() ?? "")
        .join("");

    return (
        <div
            className={cn(
                "w-12 h-12 rounded-full flex items-center justify-center text-sm font-bold shrink-0",
                variant === "hof"
                    ? "bg-navy/10 text-navy ring-2 ring-navy/25"
                    : "bg-[rgba(185,28,28,0.08)] text-incorrect ring-2 ring-incorrect/25"
            )}
            aria-hidden="true"
        >
            {initials}
        </div>
    );
}

// ---------------------------------------------------------------------------
// Outcome stamp — literal prediction outcome, keeps the correct/incorrect
// semantic colors (not navy — this is a real CORRECT/INCORRECT result, not
// a "top decile" ranking badge).
// ---------------------------------------------------------------------------

function OutcomeStamp({
    outcome,
}: {
    outcome: "correct" | "incorrect";
}) {
    if (outcome === "correct") {
        return (
            <span className="inline-flex items-center gap-1 rounded-full bg-[rgba(26,122,74,0.1)] px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-correct ring-1 ring-correct/30">
                <CheckCircle2 className="w-2.5 h-2.5" />
                Correct
            </span>
        );
    }
    return (
        <span className="inline-flex items-center gap-1 rounded-full bg-[rgba(185,28,28,0.08)] px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-incorrect ring-1 ring-incorrect/30">
            <XCircle className="w-2.5 h-2.5" />
            Incorrect
        </span>
    );
}

// ---------------------------------------------------------------------------
// Main card component
// ---------------------------------------------------------------------------

export function PunditCard({
    punditId,
    name,
    accuracy,
    correctCount,
    resolvedCount,
    totalCount,
    featuredPrediction,
    variant,
}: PunditCardProps) {
    const lowSample = resolvedCount < 10;
    const accentBorder =
        variant === "hof" ? "border-navy/20" : "border-incorrect/20";
    const accentText =
        variant === "hof" ? "text-navy" : "text-incorrect";
    const accentBg =
        variant === "hof" ? "bg-navy/5" : "bg-[rgba(185,28,28,0.04)]";

    return (
        <div
            className={cn(
                "rounded-xl border bg-editorial-card p-4 flex flex-col gap-3 transition-colors hover:bg-editorial-border/60",
                accentBorder,
                accentBg
            )}
            data-testid="pundit-card"
            data-variant={variant}
        >
            {/* Top row: avatar + name + accuracy */}
            <div className="flex items-start gap-3">
                <InitialsAvatar name={name} variant={variant} />
                <div className="flex-1 min-w-0">
                    <div className="text-base font-bold text-ink truncate leading-tight">
                        {name}
                    </div>
                    <div className={cn("text-3xl font-bold tabular-nums leading-none mt-1", accentText)}>
                        <AnimatedCounter target={accuracy} />
                        <span className="text-xl">%</span>
                    </div>
                </div>
            </div>

            {/* Correct / resolved count + sample size label */}
            <div className="flex items-center justify-between gap-2">
                <div className="text-xs font-mono text-ink-2">
                    <span className="text-navy font-semibold">{correctCount}</span>
                    <span className="text-ink-3"> correct / </span>
                    <span className="font-semibold text-ink">{resolvedCount}</span>
                    <span className="text-ink-3"> resolved</span>
                </div>
                {lowSample && (
                    <span className="text-[10px] font-mono text-pending bg-[rgba(146,64,14,0.08)] border border-pending/20 rounded px-1.5 py-0.5 shrink-0">
                        small sample
                    </span>
                )}
            </div>
            {totalCount > resolvedCount && (
                <div className="text-[10px] font-mono text-ink-3">
                    {totalCount - resolvedCount} more picks awaiting resolution
                </div>
            )}

            {/* Featured prediction */}
            {featuredPrediction && (
                <div className="rounded-lg border border-editorial-border bg-editorial-card px-3 py-2 space-y-1.5">
                    <p className="text-xs italic text-ink leading-snug line-clamp-2">
                        &ldquo;{featuredPrediction.text}&rdquo;
                    </p>
                    <div className="flex items-center justify-between gap-2">
                        <OutcomeStamp outcome={featuredPrediction.outcome} />
                        <span className="text-[10px] font-mono text-ink-3">
                            {featuredPrediction.resolvedAt}
                        </span>
                    </div>
                </div>
            )}

            {/* View full record link */}
            <Link
                href={`/ledger/${encodeURIComponent(punditId)}`}
                className="inline-flex items-center gap-1 text-xs font-mono text-ink-2 hover:text-navy transition-colors mt-auto pt-1"
            >
                View full record <ArrowRight className="w-3 h-3" />
            </Link>
        </div>
    );
}
