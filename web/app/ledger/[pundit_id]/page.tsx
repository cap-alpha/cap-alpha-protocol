import { Metadata } from "next";
import { notFound } from "next/navigation";
import Link from "next/link";
import { PunditProfileClient } from "./PunditProfileClient";

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

const API_URL =
    process.env.API_URL ||
    process.env.NEXT_PUBLIC_API_URL ||
    "https://pundit-ledger-api-wvhvx2muna-uc.a.run.app";

async function fetchPunditDetail(punditId: string): Promise<{
    pundit: PunditSummary;
    accuracy_by_category: CategoryBreakdown[];
} | null> {
    try {
        const res = await fetch(
            `${API_URL}/v1/pundits/${encodeURIComponent(punditId)}`,
            { next: { revalidate: 300 } }
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
        const res = await fetch(
            `${API_URL}/v1/pundits/${encodeURIComponent(punditId)}/predictions?page=1&page_size=20`,
            { next: { revalidate: 60 } }
        );
        if (!res.ok) return null;
        return res.json();
    } catch {
        return null;
    }
}

// ---------------------------------------------------------------------------
// generateMetadata — issue #777
// ---------------------------------------------------------------------------

export async function generateMetadata({
    params,
}: {
    params: { pundit_id: string };
}): Promise<Metadata> {
    const data = await fetchPunditDetail(params.pundit_id);
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
    const [detail, initialPreds] = await Promise.all([
        fetchPunditDetail(params.pundit_id),
        fetchInitialPredictions(params.pundit_id),
    ]);

    if (!detail) {
        notFound();
    }

    return (
        <PunditProfileClient
            pundit={detail.pundit}
            accuracyByCategory={detail.accuracy_by_category}
            initialPredictions={initialPreds}
            punditId={params.pundit_id}
        />
    );
}
