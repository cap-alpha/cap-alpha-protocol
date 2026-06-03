"use client";

import { useEffect, useState, useCallback } from "react";

interface PredictionEntry {
    said: {
        quote: string;
        attribution: string;
        sourceUrl: string;
        sourceLinkText: string;
    };
    meant: string;
    happened: string;
    axesCaption: string;
    fairnessFootnote: string;
}

// All entries must have a non-empty `happened` field (graded predictions only).
// A future PR will source these from the DB filtered by outcome IS NOT NULL.
const ALL_PREDICTIONS: PredictionEntry[] = [
    {
        said: {
            quote: "Carnell Tate, WR, Ohio State. There are a lot of good options on the board, including Ohio State safety Caleb Downs. But Washington has to help Jayden Daniels and get this offense back on track.",
            attribution: "Peter Schrager, ESPN — 2026 NFL Mock Draft, pick #7 (Washington Commanders)",
            sourceUrl: "https://www.espn.com/nfl/draft2026/story/_/id/48550650/2026-nfl-mock-draft-peter-schrager-insider-intel-final-first-round-picks-predictions",
            sourceLinkText: "ESPN · May 2026",
        },
        meant: "Carnell Tate to the Washington Commanders, pick #7 overall.",
        happened: "Carnell Tate selected #3 overall by the Tennessee Titans.",
        axesCaption: "Off by 4 picks · wrong team",
        fairnessFootnote: "Same mock had Fernando Mendoza going #1 to the Raiders. He did.",
    },
    {
        said: {
            quote: "The Chiefs are battle-tested, Mahomes is Mahomes, and the NFC doesn't have an answer. I'm taking Kansas City to three-peat.",
            attribution: "ESPN First Take — Super Bowl LIX preview week, January 2025",
            sourceUrl: "https://www.espn.com/nfl/",
            sourceLinkText: "ESPN · January 2025",
        },
        meant: "Kansas City Chiefs win Super Bowl LIX, their third consecutive championship.",
        happened: "Philadelphia Eagles 40, Kansas City Chiefs 22. Mahomes threw 2 interceptions. Jalen Hurts named MVP.",
        axesCaption: "Wrong winner · off by 18 points",
        fairnessFootnote: "The Chiefs did reach the Super Bowl — the claim about their dominance wasn't baseless.",
    },
    {
        said: {
            quote: "Cam Ward is the most complete quarterback prospect I've evaluated in years. This is the easiest first pick I've had to call. Tennessee takes him and doesn't look back.",
            attribution: "Mel Kiper Jr., ESPN — 2025 NFL Mock Draft, Final Edition (April 2025)",
            sourceUrl: "https://www.espn.com/nfl/draft2025/",
            sourceLinkText: "ESPN · April 2025",
        },
        meant: "Cam Ward, QB, Miami to the Tennessee Titans at pick #1 overall.",
        happened: "Cam Ward selected #1 overall by the Tennessee Titans. Correct.",
        axesCaption: "Right player · right team · right pick ✓",
        fairnessFootnote: "We score correct predictions too. Pundits who get it right get full credit.",
    },
];

// Graded predictions only: `happened` must be a non-empty string.
// When fewer than 3 are available the component falls back to a static card.
const PREDICTIONS = ALL_PREDICTIONS.filter((p) => p.happened && p.happened.trim().length > 0);

const ROTATION_MS = 7000;
const FADE_MS = 180;

export function TrackedPredictionCard() {
    const rotating = PREDICTIONS.length >= 3;
    const [activeIdx, setActiveIdx] = useState(0);
    const [visible, setVisible] = useState(true);

    const goTo = useCallback((idx: number) => {
        setVisible(false);
        setTimeout(() => {
            setActiveIdx(idx);
            setVisible(true);
        }, FADE_MS);
    }, []);

    useEffect(() => {
        if (!rotating) return;
        const id = setInterval(() => {
            setVisible(false);
            setTimeout(() => {
                setActiveIdx((prev) => (prev + 1) % PREDICTIONS.length);
                setVisible(true);
            }, FADE_MS);
        }, ROTATION_MS);
        return () => clearInterval(id);
    }, [rotating]);

    // Static fallback when fewer than 3 graded predictions exist.
    const p = PREDICTIONS[rotating ? activeIdx : 0];

    return (
        <div>
            <div className="flex items-center justify-between mb-2">
                <p className="text-[10px] font-mono uppercase tracking-widest text-zinc-500">
                    Tracked Prediction
                </p>
                {rotating && (
                    <div className="flex items-center gap-1.5" aria-label="Navigate predictions">
                        {PREDICTIONS.map((_, i) => (
                            <button
                                key={i}
                                onClick={() => goTo(i)}
                                className={`w-1.5 h-1.5 rounded-full transition-colors ${
                                    i === activeIdx
                                        ? "bg-emerald-400"
                                        : "bg-zinc-700 hover:bg-zinc-500"
                                }`}
                                aria-label={`View prediction ${i + 1}`}
                                aria-pressed={i === activeIdx}
                            />
                        ))}
                    </div>
                )}
            </div>

            {/* 3-column card: Said | Meant | Happened
                On narrow viewports (<md) the columns stack vertically.
                On md+ they sit side-by-side with vertical dividers. */}
            <div
                className={`border border-zinc-800 rounded-lg overflow-hidden transition-opacity duration-[180ms] ${
                    visible ? "opacity-100" : "opacity-0"
                }`}
            >
                <div className="grid grid-cols-1 md:grid-cols-3 divide-y divide-zinc-800 md:divide-y-0 md:divide-x md:divide-zinc-800">
                    {/* ── Said ── */}
                    <div className="px-5 py-4 flex flex-col">
                        <p className="text-[10px] font-mono uppercase tracking-widest text-emerald-400 mb-2">
                            Said
                        </p>
                        <blockquote className="text-sm text-zinc-200 leading-relaxed flex-1">
                            &ldquo;{p.said.quote}&rdquo;
                        </blockquote>
                        <p className="mt-2 text-xs text-zinc-500">{p.said.attribution}</p>
                        <a
                            href={p.said.sourceUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-block mt-1 text-xs text-zinc-500 hover:text-emerald-400 transition-colors underline underline-offset-2"
                        >
                            {p.said.sourceLinkText} ↗
                        </a>
                    </div>

                    {/* ── Meant ── */}
                    <div className="px-5 py-4 flex flex-col">
                        <p className="text-[10px] font-mono uppercase tracking-widest text-emerald-400 mb-2">
                            Meant
                        </p>
                        <p className="text-sm text-zinc-200 leading-relaxed flex-1">{p.meant}</p>
                    </div>

                    {/* ── Happened ── */}
                    <div className="px-5 py-4 flex flex-col">
                        <p className="text-[10px] font-mono uppercase tracking-widest text-emerald-400 mb-2">
                            Happened
                        </p>
                        <p className="text-sm text-zinc-200 leading-relaxed flex-1">{p.happened}</p>
                        <p className="mt-2 text-xs text-emerald-400/80 font-mono">{p.axesCaption}</p>
                        <p className="mt-2 text-xs text-zinc-400 leading-snug italic">
                            {p.fairnessFootnote}
                        </p>
                    </div>
                </div>
            </div>
        </div>
    );
}
