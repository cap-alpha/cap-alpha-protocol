import type { Metadata } from "next";

export async function generateMetadata({
    params,
}: {
    params: Promise<{ pundit_id: string }>;
}): Promise<Metadata> {
    const { pundit_id } = await params;
    // Convert slug to display name (best-effort; accurate name resolved in page body)
    const displayName = pundit_id
        .replace(/-/g, " ")
        .replace(/\b\w/g, (c) => c.toUpperCase());
    return {
        title: `${displayName} — Pundit Accuracy Profile`,
        description: `Prediction accuracy for ${displayName} independently audited by Cap Alpha. Full public record of claims, outcomes, and accountability — permanently on record.`,
        openGraph: {
            title: `${displayName} — Pundit Accuracy Profile`,
            description: `Prediction accuracy for ${displayName} independently audited by Cap Alpha. Every public claim scored and permanently on record.`,
        },
    };
}

export default function PunditDetailLayout({
    children,
}: {
    children: React.ReactNode;
}) {
    return <>{children}</>;
}
