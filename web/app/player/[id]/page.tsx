import { getRosterData, getPlayerTimeline, getIntelligenceFeed, getPlayerAuditLedger, TimelineEvent, IntelligenceEvent, AuditEntry } from '@/app/actions';
import PlayerDetailView from '@/components/player-detail-view';
import { notFound } from 'next/navigation';
import { slugify } from '@/lib/utils';

// Generate static params for all players to enable static generation (optional but good for performance)
export async function generateStaticParams() {
    const players = await getRosterData();
    return players.map((player) => ({
        id: encodeURIComponent(slugify(player.player_name)),
    }));
}

export const revalidate = 3600; // Cache for 1 hour (ISR)

export default async function PlayerPage({ params }: { params: { id: string } }) {
    const playerSlug = decodeURIComponent(params.id);
    const roster = await getRosterData();
    
    // Find the player where the slugified version of their name matches the slug URL
    const player = roster.find((p) => slugify(p.player_name) === playerSlug);

    if (!player) {
        notFound();
    }

    const [timeline, feed, ledger] = await Promise.all([
        getPlayerTimeline(player.player_name),
        getIntelligenceFeed(player.player_name),
        getPlayerAuditLedger(player.player_name)
    ]);

    return (
        <main className="min-h-screen bg-zinc-950 text-white p-6">
            <PlayerDetailView player={player} timeline={timeline} feed={feed} ledger={ledger} />
        </main>
    );
}
