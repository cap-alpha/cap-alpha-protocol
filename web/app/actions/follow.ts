'use server';

import { auth, clerkClient } from '@clerk/nextjs/server';
import { revalidatePath } from 'next/cache';

/**
 * Follow a pundit. Writes pundit_id into Clerk publicMetadata.followed_pundits[].
 * Idempotent — calling followPundit on an already-followed pundit is a no-op.
 *
 * Phase 1 storage: Clerk publicMetadata (8 KB cap ≈ 200+ pundit_ids).
 * Phase 2 migration path: user_follows Postgres table when fan-out queries are needed.
 */
export async function followPundit(punditId: string): Promise<{ success: boolean; error?: string }> {
    const { userId } = auth();
    if (!userId) {
        return { success: false, error: 'not_authenticated' };
    }

    try {
        const user = await clerkClient.users.getUser(userId);
        const current: string[] = (user.publicMetadata.followed_pundits as string[] | undefined) ?? [];
        if (current.includes(punditId)) {
            return { success: true }; // already following — idempotent
        }
        await clerkClient.users.updateUserMetadata(userId, {
            publicMetadata: {
                ...user.publicMetadata,
                followed_pundits: [...current, punditId],
            },
        });
        revalidatePath(`/ledger/${punditId}`);
        revalidatePath('/my/pundits');
        return { success: true };
    } catch (error) {
        console.error('followPundit failed:', error);
        return { success: false, error: 'server_error' };
    }
}

/**
 * Unfollow a pundit. Removes pundit_id from Clerk publicMetadata.followed_pundits[].
 * Idempotent — calling unfollowPundit on a non-followed pundit is a no-op.
 */
export async function unfollowPundit(punditId: string): Promise<{ success: boolean; error?: string }> {
    const { userId } = auth();
    if (!userId) {
        return { success: false, error: 'not_authenticated' };
    }

    try {
        const user = await clerkClient.users.getUser(userId);
        const current: string[] = (user.publicMetadata.followed_pundits as string[] | undefined) ?? [];
        const updated = current.filter((id) => id !== punditId);
        if (updated.length === current.length) {
            return { success: true }; // already not following — idempotent
        }
        await clerkClient.users.updateUserMetadata(userId, {
            publicMetadata: {
                ...user.publicMetadata,
                followed_pundits: updated,
            },
        });
        revalidatePath(`/ledger/${punditId}`);
        revalidatePath('/my/pundits');
        return { success: true };
    } catch (error) {
        console.error('unfollowPundit failed:', error);
        return { success: false, error: 'server_error' };
    }
}
