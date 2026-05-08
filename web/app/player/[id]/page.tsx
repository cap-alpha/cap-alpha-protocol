import { getRosterData, getPlayerTimeline, getIntelligenceFeed, getPlayerAuditLedger, calculateExactDeadMoney, getPlayerFMVHistory, getPositionalComps } from '@/app/actions';
import PlayerDetailView from '@/components/player-detail-view';
import { notFound } from 'next/navigation';
import { slugify } from '@/lib/utils';
import path from 'path';
import fs from 'fs';
import type { Metadata } from 'next';


export const revalidate = 3600; // Cache for 1 hour (ISR)

export async function generateMetadata({ params }: { params: { id: string } }): Promise<Metadata> {
    const playerSlug = decodeURIComponent(params.id);
    // Convert slug back to a display name (best-effort; accurate name resolved in page body)
    const displayName = playerSlug.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
    return {
        title: `${displayName} — Contract Analysis | Cap Alpha`,
        description: `FMV history, positional comps, and contract efficiency for ${displayName}.`,
        openGraph: {
            title: `${displayName} — Contract Analysis`,
            description: `FMV history, positional comps, and contract efficiency for ${displayName}.`,
        },
    };
}

export default async function PlayerPage({ params }: { params: { id: string } }) {
    const playerSlug = decodeURIComponent(params.id);
    const roster = await getRosterData();

    // Find the player where the slugified version of their name matches the slug URL
    const player = roster.find((p) => slugify(p.player_name) === playerSlug);

    if (!player) {
        notFound();
    }

    const [timeline, feed, ledger, deadMoneyMath, fmvHistory, positionalComps] = await Promise.all([
        getPlayerTimeline(player.player_name),
        getIntelligenceFeed(player.player_name),
        getPlayerAuditLedger(player.player_name),
        calculateExactDeadMoney(player.player_name, 2026), // Defaulting to 2026 per the timeline
        getPlayerFMVHistory(player.player_name),
        getPositionalComps(player.player_name, player.position),
    ]);

    // Check if player image exists to prevent 404 console errors
    const imagePath = path.join(process.cwd(), 'public', 'players', `${playerSlug}.jpg`);
    const hasHeadshot = fs.existsSync(imagePath);

    return (
        <main className="min-h-screen bg-zinc-950 text-white p-6">
            <PlayerDetailView player={player} timeline={timeline} feedResult={feed} ledger={ledger} deadMoneyMath={deadMoneyMath || undefined} hasHeadshot={hasHeadshot} fmvHistory={fmvHistory} positionalComps={positionalComps} />
        </main>
    );
}
