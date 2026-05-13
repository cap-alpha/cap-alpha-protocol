/**
 * TrackedPredictionCard — static Server Component.
 *
 * Displays one tracked prediction across three labeled layers:
 *   Said → Meant → Happened
 *
 * Content is hard-coded for v1 (Schrager / 2026 NFL Mock Draft).
 * A future PR will source predictions from the DB; do NOT add data
 * plumbing here (one-concern-per-PR rule).
 *
 * Editorial voice: calm reporting. The hedge in the "Said" quote is
 * intentional — it shows we report accurately, including the source's
 * own uncertainty. Never strip hedges to make a pundit look worse.
 */

const PREDICTION = {
    said: {
        quote:
            "I take a lot of pride in being as accurate as possible, but I also sort of love that no one has the firmest grasp on what is going to happen Thursday.",
        attribution: "Peter Schrager, ESPN — 2026 NFL Mock Draft (final round 1 predictions)",
        sourceUrl:
            "https://www.espn.com/nfl/draft2026/story/_/id/48550650/2026-nfl-mock-draft-peter-schrager-insider-intel-final-first-round-picks-predictions",
        sourceLinkText: "ESPN · May 2026",
    },
    meant: "Carnell Tate to the Washington Commanders, pick #7 overall.",
    happened: "Carnell Tate selected #3 overall by the Tennessee Titans.",
    axesCaption: "Off by 4 picks · wrong team",
    fairnessFootnote:
        "Same mock had Fernando Mendoza going #1 to the Raiders. He did.",
} as const;

export function TrackedPredictionCard() {
    return (
        <div className="border border-zinc-800 rounded-lg overflow-hidden">
            {/* Said */}
            <div className="px-5 py-4 border-b border-zinc-800">
                <p className="text-[10px] font-mono uppercase tracking-widest text-emerald-400 mb-2">
                    Said
                </p>
                <blockquote className="text-sm text-zinc-200 leading-relaxed">
                    &ldquo;{PREDICTION.said.quote}&rdquo;
                </blockquote>
                <p className="mt-1.5 text-xs text-zinc-500">{PREDICTION.said.attribution}</p>
                <a
                    href={PREDICTION.said.sourceUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-block mt-1 text-xs text-zinc-500 hover:text-emerald-400 transition-colors underline underline-offset-2"
                >
                    {PREDICTION.said.sourceLinkText} ↗
                </a>
            </div>

            {/* Meant */}
            <div className="px-5 py-4 border-b border-zinc-800">
                <p className="text-[10px] font-mono uppercase tracking-widest text-emerald-400 mb-2">
                    Meant
                </p>
                <p className="text-sm text-zinc-200 leading-relaxed">{PREDICTION.meant}</p>
            </div>

            {/* Happened */}
            <div className="px-5 py-4">
                <p className="text-[10px] font-mono uppercase tracking-widest text-emerald-400 mb-2">
                    Happened
                </p>
                <p className="text-sm text-zinc-200 leading-relaxed">{PREDICTION.happened}</p>
                <p className="mt-2 text-xs text-emerald-400/80 font-mono">{PREDICTION.axesCaption}</p>
                <p className="mt-2 text-xs text-zinc-400 leading-snug italic">
                    {PREDICTION.fairnessFootnote}
                </p>
            </div>
        </div>
    );
}
