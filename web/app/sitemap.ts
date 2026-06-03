import { MetadataRoute } from "next";
import { getApiUrl, getAuthHeader } from "@/lib/ledger-server";

export const revalidate = 86400; // revalidate daily

const BASE_URL =
    process.env.NEXT_PUBLIC_APP_URL ?? "https://cap-alpha.co";

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
        const apiUrl = await getApiUrl();
        const res = await fetch(`${apiUrl}/v1/pundits/`, {
            headers: { Accept: "application/json", ...getAuthHeader() },
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
        const apiUrl = await getApiUrl();
        const res = await fetch(`${apiUrl}/v1/entities/leaderboard?entity_type=player&limit=100`, {
            headers: { Accept: "application/json", ...getAuthHeader() },
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
        ...getTeamRoutes(),
        ...playerRoutes,
    ];
}
