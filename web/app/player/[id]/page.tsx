import { getRosterData, getPositionDistribution, getPlayerTimeline, getIntelligenceFeed, TimelineEvent, IntelligenceEvent } from '@/app/actions';
import PlayerDetailView from '@/components/player-detail-view';
import { GlobalSearch } from '@/components/global-search';
import { notFound } from 'next/navigation';
import { slugify } from '@/lib/utils';

// Generate static params for all players to enable static generation (optional but good for performance)
export async function generateStaticParams() {
    const players = await getRosterData();
    return players.map((player) => ({
        id: encodeURIComponent(slugify(player.player_name)),
    }));
}

export default async function PlayerPage({ params }: { params: { id: string } }) {
    const playerSlug = decodeURIComponent(params.id);
    const roster = await getRosterData();
    
    // Find the player where the slugified version of their name matches the slug URL
    const player = roster.find((p) => slugify(p.player_name) === playerSlug);

    if (!player) {
        notFound();
    }

    const [distribution, timeline, feed] = await Promise.all([
        getPositionDistribution(player.position),
        getPlayerTimeline(player.player_name),
        getIntelligenceFeed(player.player_name)
    ]);

    return (
        <main className="min-h-screen bg-zinc-950 text-white p-6">
            <div className="max-w-7xl mx-auto flex justify-between items-center mb-6">
                <div className="text-xl font-bold tracking-tighter bg-gradient-to-r from-emerald-400 to-teal-500 bg-clip-text text-transparent">
                    ALPHA PROTOCOL
                </div>
                <GlobalSearch />
            </div>
            <PlayerDetailView player={player} distributionData={distribution} timeline={timeline} feed={feed} />
        </main>
    );
}
