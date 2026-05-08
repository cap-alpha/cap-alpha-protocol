import type { Metadata } from "next";
import Link from "next/link";

// ---------------------------------------------------------------------------
// Entity type list page — placeholder for /entity/[entity_type]
// Linked from the entity detail sidebar "Browse by Type" grid.
// TODO: Implement real entity list with search/filter once API supports it (#816)
// ---------------------------------------------------------------------------

const ENTITY_TYPE_LABELS: Record<string, string> = {
    player: "Player",
    team: "Team",
    game: "Game",
    award: "Award",
    coach: "Coach",
    event: "Event",
    pundit: "Pundit",
};

export async function generateMetadata({
    params,
}: {
    params: Promise<{ entity_type: string }>;
}): Promise<Metadata> {
    const { entity_type } = await params;
    const label = ENTITY_TYPE_LABELS[entity_type] ?? "Entity";
    return {
        title: `${label}s — Pundit Predictions · CapAlpha`,
        description: `Browse all ${label.toLowerCase()} entities tracked in the CapAlpha Pundit Prediction Ledger.`,
    };
}

export default async function EntityTypeListPage({
    params,
}: {
    params: Promise<{ entity_type: string }>;
}) {
    const { entity_type } = await params;
    const label = ENTITY_TYPE_LABELS[entity_type] ?? "Entity";

    return (
        <div className="min-h-screen bg-black text-white">
            <div className="border-b border-zinc-900 bg-zinc-950/50 px-6 py-2">
                <div className="max-w-6xl mx-auto flex items-center gap-2 text-xs text-zinc-500 font-mono">
                    <Link href="/ledger" className="hover:text-emerald-400 transition-colors">
                        Leaderboard
                    </Link>
                    <span className="text-zinc-700">›</span>
                    <span className="text-zinc-300 capitalize">{label}s</span>
                </div>
            </div>

            <div className="max-w-6xl mx-auto px-6 py-16 text-center">
                <div className="text-[10px] font-bold uppercase tracking-[2px] text-amber-400 mb-4">
                    {label} Directory
                </div>
                <h1 className="text-4xl font-black text-white mb-4 tracking-tight">
                    {label} Entities
                </h1>
                <p className="text-zinc-400 text-base max-w-xl mx-auto mb-8">
                    A full searchable directory of {label.toLowerCase()} entities is coming soon.
                    Each entity page shows per-pundit accuracy for claims about that specific{" "}
                    {label.toLowerCase()}.
                </p>
                <div className="flex items-center justify-center gap-4">
                    <Link
                        href="/ledger"
                        className="inline-flex items-center gap-2 bg-emerald-500 hover:bg-emerald-400 text-black font-bold px-5 py-2.5 text-sm transition-colors"
                    >
                        View Leaderboard
                    </Link>
                    <Link
                        href="/entity/player"
                        className="inline-flex items-center gap-2 border border-zinc-700 hover:border-zinc-500 text-zinc-300 font-bold px-5 py-2.5 text-sm transition-colors"
                    >
                        Browse Players
                    </Link>
                </div>
            </div>
        </div>
    );
}
