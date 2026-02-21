'use server';

import { auth } from '@clerk/nextjs/server';
import { db } from '@/db';
import { scenarios } from '@/db/schema';
import { revalidatePath } from 'next/cache';

export async function saveScenario(
    playerId: string,
    playerName: string,
    cutType: string,
    savings: number,
    deadCap: number
) {
    const { userId } = auth();

    if (!userId) {
        return { success: false, error: "Unauthorized" };
    }

    try {
        await db.insert(scenarios).values({
            userId: userId,
            name: `Cut ${playerName} (${cutType})`,
            description: `Generated from Cut Calculator. Savings: $${savings?.toLocaleString()}M. Dead Cap: $${deadCap?.toLocaleString()}M.`,
            rosterState: {
                action: 'cut',
                playerId,
                playerName,
                cutType,
                financials: { savings, deadCap }
            },
        });

        revalidatePath('/scenarios');

        return { success: true };
    } catch (e) {
        console.error("Error saving scenario:", e);
        return { success: false, error: "Failed to save scenario" };
    }
}
