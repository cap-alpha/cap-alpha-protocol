'use server';

import { auth, currentUser } from '@clerk/nextjs/server';
import { db } from '@/db';
import { scenarios, users } from '@/db/schema';
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
        // Lazy provision the user to bypass local webhook forwarding issues
        const user = await currentUser();
        if (user) {
            const email = user.emailAddresses[0]?.emailAddress || "unknown@clerk.dev";
            await db.insert(users).values({
                clerkId: userId,
                email: email,
            }).onConflictDoNothing();
        }

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
