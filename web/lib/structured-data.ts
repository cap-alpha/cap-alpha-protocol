/**
 * Structured-data helpers for JSON-LD rich results.
 *
 * Issue: #769 — bettor discovery journey Phase 1 (PR A)
 * Spec: https://github.com/cap-alpha/cap-alpha-protocol/issues/769
 */

const BASE_URL = process.env.NEXT_PUBLIC_APP_URL ?? "https://cap-alpha.co";

export interface PunditJsonLdInput {
    pundit_id: string;
    pundit_name: string;
    total_predictions: number;
    resolved_count: number;
    correct_count: number;
    accuracy_rate: number | null;
}

/**
 * Build a `Person` + `Dataset` JSON-LD object for a pundit detail page.
 * Eligible for Google rich results on "person + dataset" queries.
 *
 * Usage: JSON.stringify(punditJsonLd(pundit)) inside a
 * <script type="application/ld+json"> tag.
 */
export function punditJsonLd(pundit: PunditJsonLdInput): Record<string, unknown> {
    const totalStr = pundit.total_predictions.toLocaleString();
    const correctStr = `${pundit.correct_count}/${pundit.resolved_count}`;

    return {
        "@context": "https://schema.org",
        "@type": "Person",
        name: pundit.pundit_name,
        url: `${BASE_URL}/ledger/${encodeURIComponent(pundit.pundit_id)}`,
        jobTitle: "Sports analyst / pundit",
        subjectOf: {
            "@type": "Dataset",
            name: `${pundit.pundit_name} prediction record`,
            description: `${totalStr} predictions tracked, ${correctStr} resolved correct`,
            creator: {
                "@type": "Organization",
                name: "Cap Alpha",
                url: BASE_URL,
            },
            license: `${BASE_URL}/legal/terms`,
            measurementTechnique: `${BASE_URL}/methodology`,
            variableMeasured: [
                "accuracy_rate",
                "brier_score",
                "total_predictions",
            ],
        },
    };
}
