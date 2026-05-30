import { auth, clerkClient } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";
import Link from "next/link";
import { Metadata } from "next";
import { MyPunditsClient } from "./MyPunditsClient";
import { getAuthHeader, API_URL as BACKEND_URL } from "@/lib/ledger-server";

export const metadata: Metadata = {
    title: "My Pundits | Cap Alpha",
    description: "Pundits you're following on Cap Alpha — accuracy summaries, recent resolutions, and pending predictions.",
};

interface PunditSummary {
    pundit_id: string;
    pundit_name: string;
    sport: string;
    total_predictions: number;
    resolved_count: number;
    correct_count: number;
    accuracy_rate: number | null;
    avg_brier_score: number | null;
    brier_score: number | null;
    avg_weighted_score: number | null;
    overconfidence_score: number | null;
}

async function fetchPunditSummary(punditId: string): Promise<PunditSummary | null> {
    try {
        const res = await fetch(
            `${BACKEND_URL}/v1/pundits/${encodeURIComponent(punditId)}`,
            { next: { revalidate: 300 }, headers: { Accept: "application/json", ...getAuthHeader() } }
        );
        if (!res.ok) return null;
        const data = await res.json();
        return data.pundit ?? null;
    } catch {
        return null;
    }
}

export default async function MyPunditsPage() {
    const { userId } = auth();
    if (!userId) {
        redirect("/sign-in?redirect_url=/my/pundits");
    }

    // Fetch followed pundit IDs from Clerk metadata
    let followedIds: string[] = [];
    try {
        const user = await clerkClient.users.getUser(userId);
        followedIds = (user.publicMetadata.followed_pundits as string[] | undefined) ?? [];
    } catch {
        // non-fatal — show empty state
    }

    // Fetch summary data for each followed pundit in parallel
    const pundits = followedIds.length > 0
        ? (await Promise.all(followedIds.map(fetchPunditSummary))).filter(
            (p): p is PunditSummary => p !== null
          )
        : [];

    return (
        <MyPunditsClient
            pundits={pundits}
            followedIds={followedIds}
        />
    );
}
