import { NextResponse } from "next/server";
import { Redis } from "@upstash/redis";
import { Ratelimit } from "@upstash/ratelimit";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type PunditSearchResult = {
    id: string;
    slug: string;
    name: string;
    accuracy: number;         // 0-1
    predictionCount: number;
    correctCount: number;
    domain: string;           // 'sports.nfl', etc.
    avatarUrl?: string;
};

// ---------------------------------------------------------------------------
// Upstash setup — gracefully optional
// ---------------------------------------------------------------------------

function getRedis(): Redis | null {
    const url = process.env.UPSTASH_REDIS_REST_URL;
    const token = process.env.UPSTASH_REDIS_REST_TOKEN;
    if (!url || !token) return null;
    return new Redis({ url, token });
}

let _ipLimiter: Ratelimit | null = null;

function getIpLimiter(): Ratelimit | null {
    const redis = getRedis();
    if (!redis) return null;
    if (_ipLimiter) return _ipLimiter;
    _ipLimiter = new Ratelimit({
        redis,
        limiter: Ratelimit.slidingWindow(30, "60 s"),
        prefix: "rl:search_pundits",
        analytics: true,
    });
    return _ipLimiter;
}

const CACHE_TTL_SECONDS = 300; // 5 minutes

async function getCached(redis: Redis, key: string): Promise<PunditSearchResult[] | null> {
    try {
        const raw = await redis.get<PunditSearchResult[]>(key);
        return raw ?? null;
    } catch (err) {
        console.warn("[search/pundits] Redis GET error:", err);
        return null;
    }
}

async function setCached(redis: Redis, key: string, value: PunditSearchResult[]): Promise<void> {
    try {
        await redis.set(key, JSON.stringify(value), { ex: CACHE_TTL_SECONDS });
    } catch (err) {
        console.warn("[search/pundits] Redis SET error:", err);
    }
}

// ---------------------------------------------------------------------------
// Backend
// ---------------------------------------------------------------------------

const API_URL =
    process.env.API_URL ||
    process.env.NEXT_PUBLIC_API_URL ||
    "https://pundit-ledger-api-wvhvx2muna-uc.a.run.app";

async function searchFromBackend(q: string): Promise<PunditSearchResult[]> {
    const url = new URL(`${API_URL}/v1/pundits/`);
    url.searchParams.set("search", q);
    url.searchParams.set("limit", "8");

    const res = await fetch(url.toString(), {
        headers: { Accept: "application/json" },
    });

    if (!res.ok) {
        console.error(`[search/pundits] Backend returned ${res.status}`);
        return [];
    }

    const data = await res.json();
    const pundits: Record<string, unknown>[] = data.pundits || [];

    return pundits
        .filter((p) => {
            const name = String(p.pundit_name ?? p.name ?? "").toLowerCase();
            return name.includes(q.toLowerCase());
        })
        .slice(0, 8)
        .map((p): PunditSearchResult => {
            const resolvedCount = (p.resolved_count as number | undefined) ??
                (p.resolved_predictions as number | undefined) ?? 0;
            const correctCount = (p.correct_count as number | undefined) ??
                (p.correct_predictions as number | undefined) ?? 0;
            const totalCount = (p.total_predictions as number | undefined) ?? 0;

            const accuracyRate = (p.accuracy_rate as number | null | undefined);
            const accuracy = accuracyRate != null
                ? accuracyRate
                : resolvedCount > 0
                ? correctCount / resolvedCount
                : 0;

            const punditId = String(p.pundit_id ?? p.id ?? "");
            const punditName = String(p.pundit_name ?? p.name ?? "");
            const sport = String(p.sport ?? "sports.nfl");

            return {
                id: punditId,
                slug: punditId,
                name: punditName,
                accuracy: Math.min(1, Math.max(0, accuracy)),
                predictionCount: totalCount,
                correctCount,
                domain: sport.includes(".") ? sport : `sports.${sport.toLowerCase()}`,
                avatarUrl: undefined,
            };
        });
}

// ---------------------------------------------------------------------------
// Route handler
// ---------------------------------------------------------------------------

export async function GET(req: Request): Promise<NextResponse> {
    const { searchParams } = new URL(req.url);
    const q = (searchParams.get("q") ?? "").trim();

    // Validate minimum query length
    if (q.length < 2) {
        return NextResponse.json({ results: [] });
    }

    // Rate limit by IP
    const ip =
        req.headers.get("x-forwarded-for")?.split(",")[0].trim() ||
        req.headers.get("x-real-ip") ||
        "unknown";

    const limiter = getIpLimiter();
    if (limiter) {
        try {
            const rl = await limiter.limit(ip);
            if (!rl.success) {
                return NextResponse.json(
                    { error: "Rate limit exceeded" },
                    {
                        status: 429,
                        headers: {
                            "Retry-After": String(Math.ceil((rl.reset - Date.now()) / 1000)),
                        },
                    }
                );
            }
        } catch (err) {
            console.warn("[search/pundits] Rate limit check error:", err);
            // Fail-open
        }
    }

    // Cache check
    const redis = getRedis();
    const cacheKey = `search:pundits:${q.toLowerCase()}`;

    if (redis) {
        const cached = await getCached(redis, cacheKey);
        if (cached !== null) {
            return NextResponse.json({ results: cached });
        }
    }

    // Fetch from backend
    try {
        const results = await searchFromBackend(q);

        if (redis) {
            await setCached(redis, cacheKey, results);
        }

        return NextResponse.json({ results });
    } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        console.error("[search/pundits] Error:", msg);
        return NextResponse.json({ results: [] }, { status: 500 });
    }
}
