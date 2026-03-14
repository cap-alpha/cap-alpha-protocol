import { getRosterData, getPositionDistribution, getPlayerTimeline, TimelineEvent } from '@/app/actions';
import PlayerDetailView from '@/components/player-detail-view';
import { notFound } from 'next/navigation';

// Generate static params for all players to enable static generation (optional but good for performance)
export async function generateStaticParams() {
    const players = await getRosterData();
    return players.map((player) => ({
        id: encodeURIComponent(player.player_name),
    }));
}

export default async function PlayerPage({ params }: { params: { id: string } }) {
    const playerName = decodeURIComponent(params.id);
    const roster = await getRosterData();
    const player = roster.find((p) => p.player_name === playerName);

    if (!player) {
        notFound();
    }

    const [distribution, timeline] = await Promise.all([
        getPositionDistribution(player.position),
        getPlayerTimeline(player.player_name)
    ]);

    return (
        <main className="min-h-screen bg-zinc-950 text-white p-6">
            <PlayerDetailView player={player} distributionData={distribution} timeline={timeline} />
        </main>
    );
}
