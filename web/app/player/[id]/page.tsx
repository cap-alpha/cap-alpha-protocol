import { getRosterData, getPlayerTimeline, getIntelligenceFeed, getPlayerAuditLedger, calculateExactDeadMoney, TimelineEvent, IntelligenceEvent, AuditEntry } from '@/app/actions';
import PlayerDetailView from '@/components/player-detail-view';
import { notFound } from 'next/navigation';
import { slugify } from '@/lib/utils';
import path from 'path';
import fs from 'fs';


export const revalidate = 3600; // Cache for 1 hour (ISR)

export default async function PlayerPage({ params }: { params: { id: string } }) {
    const playerSlug = decodeURIComponent(params.id);
    const roster = await getRosterData();

    // Find the player where the slugified version of their name matches the slug URL
    const player = roster.find((p) => slugify(p.player_name) === playerSlug);

    if (!player) {
        notFound();
    }

    const [timeline, feed, ledger, deadMoneyMath] = await Promise.all([
        getPlayerTimeline(player.player_name),
        getIntelligenceFeed(player.player_name),
        getPlayerAuditLedger(player.player_name),
        calculateExactDeadMoney(player.player_name, 2026) // Defaulting to 2026 per the timeline
    ]);

    // Check if player image exists to prevent 404 console errors
    const imagePath = path.join(process.cwd(), 'public', 'players', `${playerSlug}.jpg`);
    const hasHeadshot = fs.existsSync(imagePath);

    return (
        <main className="min-h-screen bg-zinc-950 text-white p-6">
            <PlayerDetailView player={player} timeline={timeline} feed={feed} ledger={ledger} deadMoneyMath={deadMoneyMath || undefined} hasHeadshot={hasHeadshot} />
        </main>
    );
}
