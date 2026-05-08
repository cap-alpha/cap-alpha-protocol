import { MetadataRoute } from 'next'

const BASE_URL = 'https://cap-alpha.co'
const API_URL =
  process.env.NEXT_PUBLIC_API_URL ||
  'https://pundit-ledger-api-wvhvx2muna-uc.a.run.app'

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const staticRoutes: MetadataRoute.Sitemap = [
    {
      url: `${BASE_URL}/`,
      lastModified: new Date(),
      changeFrequency: 'daily',
      priority: 1.0,
    },
    {
      url: `${BASE_URL}/ledger`,
      lastModified: new Date(),
      changeFrequency: 'daily',
      priority: 0.9,
    },
    {
      url: `${BASE_URL}/methodology`,
      lastModified: new Date(),
      changeFrequency: 'monthly',
      priority: 0.7,
    },
    {
      url: `${BASE_URL}/pricing`,
      lastModified: new Date(),
      changeFrequency: 'monthly',
      priority: 0.7,
    },
    {
      url: `${BASE_URL}/docs`,
      lastModified: new Date(),
      changeFrequency: 'monthly',
      priority: 0.7,
    },
    {
      url: `${BASE_URL}/quality`,
      lastModified: new Date(),
      changeFrequency: 'daily',
      priority: 0.6,
    },
    {
      url: `${BASE_URL}/legal/terms`,
      lastModified: new Date(),
      changeFrequency: 'yearly',
      priority: 0.3,
    },
    {
      url: `${BASE_URL}/legal/privacy`,
      lastModified: new Date(),
      changeFrequency: 'yearly',
      priority: 0.3,
    },
    {
      url: `${BASE_URL}/legal/disclosure`,
      lastModified: new Date(),
      changeFrequency: 'yearly',
      priority: 0.3,
    },
    {
      url: `${BASE_URL}/legal/responsible-gambling`,
      lastModified: new Date(),
      changeFrequency: 'yearly',
      priority: 0.3,
    },
    {
      url: `${BASE_URL}/legal/corrections`,
      lastModified: new Date(),
      changeFrequency: 'yearly',
      priority: 0.3,
    },
    {
      url: `${BASE_URL}/legal/acceptable-use`,
      lastModified: new Date(),
      changeFrequency: 'yearly',
      priority: 0.3,
    },
  ]

  // Dynamic: pundit profile pages
  let punditRoutes: MetadataRoute.Sitemap = []
  try {
    const res = await fetch(`${API_URL}/v1/pundits/`, {
      next: { revalidate: 3600 },
    })
    if (res.ok) {
      const data = await res.json()
      const pundits: Array<{ pundit_id?: string; id?: string }> =
        data.pundits || data || []
      punditRoutes = pundits.map((p) => ({
        url: `${BASE_URL}/ledger/${p.pundit_id || p.id}`,
        lastModified: new Date(),
        changeFrequency: 'weekly',
        priority: 0.8,
      }))
    }
  } catch {
    // API unavailable at build time — degrade gracefully to static-only sitemap
  }

  // Dynamic: draft year pages (current year and 2 prior)
  const currentYear = new Date().getFullYear()
  const draftRoutes: MetadataRoute.Sitemap = [0, 1, 2].map((offset) => ({
    url: `${BASE_URL}/draft/${currentYear - offset}`,
    lastModified: new Date(),
    changeFrequency: 'monthly',
    priority: 0.6,
  }))

  return [...staticRoutes, ...punditRoutes, ...draftRoutes]
}
