import { UserResource } from "@clerk/types";

export const CREDITS_PER_REPORT = 1;
export const INITIAL_CREDITS = 100;

export function getCreditBalance(user: UserResource | null | undefined): number {
    if (!user) return 0;
    // Clerk metadata is untyped by default, cast it
    const metadata = user.publicMetadata as { credits?: number };
    return metadata.credits ?? 0;
}

export async function deductCredits(userId: string, amount: number) {
    // This would need to be a server action or API call to securely update Clerk
    // For MVP client-side check, we rely on the API route to do the actual deduction
    console.log(`Deducting ${amount} credits for ${userId}`);
    return true;
}
