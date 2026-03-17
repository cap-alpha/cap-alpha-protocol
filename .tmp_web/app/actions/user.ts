'use server';

import { auth, clerkClient } from '@clerk/nextjs/server';
import { revalidatePath } from 'next/cache';

export async function updateUserTeam(team: string) {
    const { userId } = auth();

    if (!userId) {
        throw new Error("User not authenticated");
    }

    try {
        // Update the user's publicMetadata with the selected team
        await clerkClient.users.updateUserMetadata(userId, {
            publicMetadata: {
                favorite_team: team,
            },
        });

        // Revalidate the layout to reflect changes (if any UI depends on server-side metadata)
        revalidatePath('/');

        return { success: true };
    } catch (error) {
        console.error("Failed to update user team:", error);
        return { success: false, error: "Failed to update team" };
    }
}
