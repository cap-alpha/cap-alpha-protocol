import { MetadataRoute } from "next";

export const revalidate = 86400; // revalidate daily

const BASE_URL =
    process.env.NEXT_PUBLIC_APP_URL ?? "https://cap-alpha.co";

const API_URL =
    process.env.API_URL ||
    process.env.NEXT_PUBLIC_API_URL ||
    "https://pundit-ledger-api-wvhvx2muna-uc.a.run.app";

// ---------------------------------------------------------------------------
// Static routes
// ---------------------------------------------------------------------------

const staticRoutes: MetadataRoute.Sitemap = [
    {
        url: `${BASE_URL}/`,
        priority: 1.0,
        changeFrequency: "daily",
    },
    {
        url: `${BASE_URL}/ledger`,
        priority: 0.9,
        changeFrequency: "daily",
    },
    {
        url: `${BASE_URL}/methodology`,
        priority: 0.7,
        changeFrequency: "monthly",
    },
    {
        url: `${BASE_URL}/pricing`,
        priority: 0.7,
        changeFrequency: "monthly",
    },
    {
        url: `${BASE_URL}/docs`,
        priority: 0.7,
        changeFrequency: "monthly",
    },
    {
        url: `${BASE_URL}/quality`,
        priority: 0.6,
        changeFrequency: "weekly",
    },
    // Legal pages
    {
        url: `${BASE_URL}/legal/terms`,
        priority: 0.3,
        changeFrequency: "yearly",
    },
    {
        url: `${BASE_URL}/legal/privacy`,
        priority: 0.3,
        changeFrequency: "yearly",
    },
    {
        url: `${BASE_URL}/legal/disclosure`,
        priority: 0.3,
        changeFrequency: "yearly",
    },
    {
        url: `${BASE_URL}/legal/responsible-gambling`,
        priority: 0.3,
        changeFrequency: "yearly",
    },
    {
        url: `${BASE_URL}/legal/corrections`,
        priority: 0.3,
        changeFrequency: "yearly",
    },
    {
        url: `${BASE_URL}/legal/acceptable-use`,
        priority: 0.3,
        changeFrequency: "yearly",
    },
];

// ---------------------------------------------------------------------------
// Dynamic: /ledger/[pundit_id]
// ---------------------------------------------------------------------------

async function getPunditRoutes(): Promise<MetadataRoute.Sitemap> {
    try {
        const res = await fetch(`${API_URL}/v1/pundits/`, {
            headers: { Accept: "application/json" },
            // next.js fetch cache options
            next: { revalidate: 86400 },
        });

        if (!res.ok) {
            console.error(
                `[sitemap] Pundits API returned ${res.status} — skipping dynamic pundit routes`
            );
            return [];
        }

        const data: { pundits?: Array<{ pundit_id?: string; id?: string }> } =
            await res.json();
        const pundits = data.pundits ?? [];

        return pundits
            .map((p) => p.pundit_id ?? p.id)
            .filter((id): id is string => Boolean(id))
            .map((id) => ({
                url: `${BASE_URL}/ledger/${encodeURIComponent(id)}`,
                priority: 0.8,
                changeFrequency: "weekly" as const,
            }));
    } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        console.error(`[sitemap] Failed to fetch pundits — skipping: ${msg}`);
        return [];
    }
}

// ---------------------------------------------------------------------------
// Dynamic: /draft/[year]  (last 3 years)
// ---------------------------------------------------------------------------

function getDraftRoutes(): MetadataRoute.Sitemap {
    const currentYear = new Date().getFullYear();
    const years = [currentYear - 2, currentYear - 1, currentYear];
    return years.map((year) => ({
        url: `${BASE_URL}/draft/${year}`,
        priority: 0.6,
        changeFrequency: "weekly" as const,
    }));
}

// ---------------------------------------------------------------------------
// Sitemap entry point
// ---------------------------------------------------------------------------

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
    const [punditRoutes] = await Promise.all([getPunditRoutes()]);

    return [...staticRoutes, ...punditRoutes, ...getDraftRoutes()];
}
