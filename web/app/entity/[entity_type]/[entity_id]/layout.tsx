import type { Metadata } from "next";

// ---------------------------------------------------------------------------
// Server-side metadata generation for entity detail pages
// Implements generateMetadata for per-entity OG tags (issue #816)
// Phase 1 (#772): adds canonical URL so the entity page is indexable.
// ---------------------------------------------------------------------------

const BASE_URL =
    process.env.NEXT_PUBLIC_APP_URL ?? "https://cap-alpha.co";

const ENTITY_TYPE_LABELS: Record<string, string> = {
    player: "Player",
    team: "Team",
    game: "Game",
    award: "Award",
    coach: "Coach",
    event: "Event",
    pundit: "Pundit",
};

function humanizeName(entityId: string): string {
    return entityId
        .split("-")
        .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
        .join(" ");
}

export async function generateMetadata({
    params,
}: {
    params: Promise<{ entity_type: string; entity_id: string }>;
}): Promise<Metadata> {
    const { entity_type, entity_id } = await params;

    // Attempt to fetch real entity name from API
    // TODO: Replace with real /v1/entities/{entity_type}/{entity_id} once backend lands (#816)
    const entityName = humanizeName(entity_id);
    const typeLabel = ENTITY_TYPE_LABELS[entity_type] ?? "Entity";

    const canonicalUrl = `${BASE_URL}/entity/${encodeURIComponent(entity_type)}/${encodeURIComponent(entity_id)}`;

    const title = `${entityName} — Pundit Predictions · Cap Alpha`;
    const description = `See every pundit prediction about ${entityName} (${typeLabel}). Accuracy scores, Brier ratings, and cryptographically verified claim history.`;

    return {
        title,
        description,
        alternates: {
            canonical: canonicalUrl,
        },
        openGraph: {
            title,
            description,
            type: "website",
            url: canonicalUrl,
        },
        twitter: {
            card: "summary",
            title,
            description,
        },
    };
}

export default function EntityDetailLayout({
    children,
}: {
    children: React.ReactNode;
}) {
    return <>{children}</>;
}
