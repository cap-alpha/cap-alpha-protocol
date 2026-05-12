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
        const internalApiKey = process.env.CAP_ALPHA_INTERNAL_API_KEY;
        const headers: Record<string, string> = { Accept: "application/json" };
        if (internalApiKey) {
            headers["x-api-key"] = internalApiKey;
        } else {
            console.warn(
                "[sitemap] CAP_ALPHA_INTERNAL_API_KEY is not set — pundits fetch may return 401"
            );
        }
        const res = await fetch(`${API_URL}/v1/pundits/`, {
            headers,
            // next.js fetch cache options
            next: { revalidate: 86400 },
        });

        if (!res.ok) {
            console.error(
                `[sitemap] Pundits API returned ${res.status} — skipping dynamic pundit routes`
            );
            return [];
        }

        const data: {
            pundits?: Array<{
                pundit_id?: string;
                id?: string;
                total_predictions?: number;
            }>;
        } = await res.json();
        const pundits = data.pundits ?? [];

        // Only include pundits with >= 5 predictions — thin pages harm SEO (#769)
        return pundits
            .filter((p) => (p.total_predictions ?? 0) >= 5)
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
// Dynamic: /team/[abbr]  (all 32 NFL teams — static list)
// ---------------------------------------------------------------------------

const NFL_TEAM_ABBRS = [
    "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE",
    "DAL", "DEN", "DET", "GB",  "HOU", "IND", "JAX", "KC",
    "LAC", "LAR", "LV",  "MIA", "MIN", "NE",  "NO",  "NYG",
    "NYJ", "PHI", "PIT", "SEA", "SF",  "TB",  "TEN", "WAS",
];

function getTeamRoutes(): MetadataRoute.Sitemap {
    return NFL_TEAM_ABBRS.map((abbr) => ({
        url: `${BASE_URL}/team/${abbr}`,
        priority: 0.8,
        changeFrequency: "weekly" as const,
    }));
}

// ---------------------------------------------------------------------------
// Dynamic: /player/[slug]  (top players by claims from entity API)
// ---------------------------------------------------------------------------

async function getPlayerRoutes(): Promise<MetadataRoute.Sitemap> {
    try {
        const internalApiKey = process.env.CAP_ALPHA_INTERNAL_API_KEY;
        const headers: Record<string, string> = { Accept: "application/json" };
        if (internalApiKey) {
            headers["x-api-key"] = internalApiKey;
        }
        // Fetch top players by claim count from the entity leaderboard
        const res = await fetch(`${API_URL}/v1/entities/leaderboard?entity_type=player&limit=100`, {
            headers,
            next: { revalidate: 86400 },
        });

        if (!res.ok) {
            console.warn(
                `[sitemap] Entity leaderboard returned ${res.status} — skipping player routes`
            );
            return [];
        }

        const data: { entities?: Array<{ entity_name?: string; slug?: string; total_claims?: number }> } =
            await res.json();
        const entities = data.entities ?? [];

        return entities
            .filter((e) => (e.total_claims ?? 0) >= 3 && (e.entity_name || e.slug))
            .map((e) => {
                const slug = e.slug ??
                    encodeURIComponent(
                        (e.entity_name ?? "").toLowerCase().replace(/\s+/g, "-")
                    );
                return {
                    url: `${BASE_URL}/player/${slug}`,
                    priority: 0.7,
                    changeFrequency: "weekly" as const,
                };
            });
    } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        console.warn(`[sitemap] Failed to fetch player entities — skipping: ${msg}`);
        return [];
    }
}

// ---------------------------------------------------------------------------
// Sitemap entry point
// ---------------------------------------------------------------------------

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
    const [punditRoutes, playerRoutes] = await Promise.all([
        getPunditRoutes(),
        getPlayerRoutes(),
    ]);

    return [
        ...staticRoutes,
        ...punditRoutes,
        ...getDraftRoutes(),
        ...getTeamRoutes(),
        ...playerRoutes,
    ];
}
