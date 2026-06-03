import { Metadata } from "next";
import { notFound } from "next/navigation";
import Link from "next/link";
import { Suspense } from "react";
import { auth, clerkClient } from "@clerk/nextjs/server";
import { PunditProfileClient } from "./PunditProfileClient";
import { punditJsonLd } from "@/lib/structured-data";
import { getApiUrl, getAuthHeader } from "@/lib/ledger-server";
import snapshot from "@/lib/data/leaderboard-snapshot.json";

// ---------------------------------------------------------------------------
// Types — shared between server and client
// ---------------------------------------------------------------------------

export interface PunditSummary {
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

export interface CategoryBreakdown {
    claim_category: string;
    total: number;
    resolved: number;
    correct: number;
    accuracy_rate: number | null;
    avg_weighted_score: number | null;
}

export interface Prediction {
    prediction_hash: string;
    ingestion_timestamp: string;
    source_url: string | null;
    raw_assertion_text: string | null;
    extracted_claim: string | null;
    claim_category: string;
    season_year: number | null;
    target_player_id: string | null;
    target_player_name: string | null;
    target_team: string | null;
    llm_provider: string | null;
    llm_model: string | null;
    prompt_version: string | null;
    resolution_status: string;
    resolved_at: string | null;
    binary_correct: boolean | null;
    brier_score: number | null;
    weighted_score: number | null;
    confidence: number | null;
    outcome_source: string | null;
    outcome_notes: string | null;
    quality_score: number | null;
}

export interface PredictionsResponse {
    pundit_id: string;
    predictions: Prediction[];
    page: number;
    page_size: number;
    total: number;
    pages: number;
}

// ---------------------------------------------------------------------------
// Server-side data fetch
// ---------------------------------------------------------------------------

async function fetchPunditDetail(punditId: string): Promise<{
    pundit: PunditSummary;
    accuracy_by_category: CategoryBreakdown[];
} | null> {
    try {
        const apiUrl = await getApiUrl();
        const res = await fetch(
            `${apiUrl}/v1/pundits/${encodeURIComponent(punditId)}`,
            { next: { revalidate: 300 }, headers: { Accept: "application/json", ...getAuthHeader() } }
        );
        if (res.status === 404) return null;
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
    } catch {
        return null;
    }
}

async function fetchInitialPredictions(punditId: string): Promise<PredictionsResponse | null> {
    try {
        const apiUrl = await getApiUrl();
        const res = await fetch(
            `${apiUrl}/v1/pundits/${encodeURIComponent(punditId)}/predictions?page=1&page_size=20`,
            { next: { revalidate: 60 }, headers: { Accept: "application/json", ...getAuthHeader() } }
        );
        if (!res.ok) return null;
        return res.json();
    } catch {
        return null;
    }
}

// ---------------------------------------------------------------------------
// Snapshot fallback — when backend is unavailable, serve stats from the
// static leaderboard-snapshot.json so leaderboard links never 404.
// Follow-up to provision CAP_ALPHA_INTERNAL_API_KEY tracked in issue #1018.
// ---------------------------------------------------------------------------

function getPunditFromSnapshot(punditId: string): {
    pundit: PunditSummary;
    accuracy_by_category: [];
} | null {
    const record = (snapshot.pundits as Array<{
        pundit_id: string;
        pundit_name: string;
        total_predictions: number;
        resolved_predictions: number;
        correct_predictions: number;
        incorrect_predictions: number;
        accuracy_rate: number | null;
        avg_brier_score: number | null;
        sport: string;
    }>).find((p) => p.pundit_id === punditId);

    if (!record) return null;

    return {
        pundit: {
            pundit_id: record.pundit_id,
            pundit_name: record.pundit_name,
            sport: record.sport,
            total_predictions: record.total_predictions,
            resolved_count: record.resolved_predictions,
            correct_count: record.correct_predictions,
            accuracy_rate: record.accuracy_rate,
            avg_brier_score: record.avg_brier_score,
            brier_score: record.avg_brier_score,
            avg_weighted_score: null,
            overconfidence_score: null,
        },
        accuracy_by_category: [],
    };
}

// ---------------------------------------------------------------------------
// generateMetadata — issue #777
// ---------------------------------------------------------------------------

export async function generateMetadata({
    params,
}: {
    params: { pundit_id: string };
}): Promise<Metadata> {
    const data = await fetchPunditDetail(params.pundit_id)
        ?? getPunditFromSnapshot(params.pundit_id);
    if (!data) {
        return { title: "Pundit Not Found | Pundit Ledger" };
    }

    const { pundit } = data;
    const accuracyPct =
        pundit.accuracy_rate !== null
            ? `${Math.round(pundit.accuracy_rate * 100)}% accuracy`
            : "unscored";
    const description = `${pundit.pundit_name} — ${accuracyPct} · ${pundit.total_predictions} tracked predictions. Cryptographically sealed on CapAlpha.`;

    return {
        title: `${pundit.pundit_name} | Pundit Ledger`,
        description,
        alternates: {
            canonical: `https://cap-alpha.co/ledger/${params.pundit_id}`,
        },
        openGraph: {
            title: `${pundit.pundit_name} Prediction Record | CapAlpha`,
            description,
            url: `https://cap-alpha.co/ledger/${params.pundit_id}`,
        },
        twitter: {
            card: "summary",
            title: `${pundit.pundit_name} — CapAlpha Pundit Ledger`,
            description,
        },
    };
}

// ---------------------------------------------------------------------------
// Server component shell
// ---------------------------------------------------------------------------

export default async function PunditProfilePage({
    params,
}: {
    params: { pundit_id: string };
}) {
    const [liveDetail, initialPreds] = await Promise.all([
        fetchPunditDetail(params.pundit_id),
        fetchInitialPredictions(params.pundit_id),
    ]);

    // Fall back to the static snapshot when the backend is unavailable (e.g.
    // missing CAP_ALPHA_INTERNAL_API_KEY → 422 → proxy 502). Predictions will
    // be empty in fallback mode but still render the profile from snapshot data.
    const detail = liveDetail ?? getPunditFromSnapshot(params.pundit_id);
    // Watermark: snapshot generated_at is always available; live data has no
    // per-pundit updated_at on the summary endpoint today.
    const dataUpdatedAt: string = (snapshot.snapshot_metadata as { generated_at: string }).generated_at;

    if (!detail) {
        notFound();
    }

    // Resolve follow state server-side — zero client flicker
    // Wrapped in try/catch: Clerk v5 throws when clerkMiddleware() is absent on
    // this route. See Option B follow-up issue for the proper middleware fix.
    let userId: string | null = null;
    try {
        const authResult = auth();
        userId = authResult.userId ?? null;
    } catch {
        // Clerk middleware not configured on this route — isFollowing defaults to false
    }
    let isFollowing = false;
    if (userId) {
        try {
            const user = await clerkClient.users.getUser(userId);
            const followed: string[] = (user.publicMetadata.followed_pundits as string[] | undefined) ?? [];
            isFollowing = followed.includes(params.pundit_id);
        } catch {
            // non-fatal — fall back to not following
        }
    }

    const jsonLd = punditJsonLd({
        pundit_id: params.pundit_id,
        pundit_name: detail.pundit.pundit_name,
        total_predictions: detail.pundit.total_predictions,
        resolved_count: detail.pundit.resolved_count,
        correct_count: detail.pundit.correct_count,
        accuracy_rate: detail.pundit.accuracy_rate,
    });

    return (
        <>
            {/* JSON-LD structured data for Google rich results (#769) */}
            <script
                type="application/ld+json"
                dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
            />
            {/* Suspense required because PunditProfileClient uses useSearchParams (#769) */}
            <Suspense fallback={null}>
                <PunditProfileClient
                    pundit={detail.pundit}
                    accuracyByCategory={detail.accuracy_by_category}
                    initialPredictions={initialPreds}
                    punditId={params.pundit_id}
                    isFollowing={isFollowing}
                    isAuthenticated={!!userId}
                    dataUpdatedAt={dataUpdatedAt}
                />
            </Suspense>
        </>
    );
}
