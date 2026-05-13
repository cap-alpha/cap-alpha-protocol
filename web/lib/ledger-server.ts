export const API_URL =
    process.env.API_URL ||
    process.env.NEXT_PUBLIC_API_URL ||
    "https://pundit-ledger-api-wvhvx2muna-uc.a.run.app";

export function normalizePundit(p: Record<string, unknown>): Record<string, unknown> {
    const resolvedCount = (p.resolved_count as number | undefined) ?? 0;
    const correctCount = (p.correct_count as number | undefined) ?? 0;
    return {
        ...p,
        resolved_predictions:
            p.resolved_predictions !== undefined
                ? p.resolved_predictions
                : resolvedCount,
        correct_predictions:
            p.correct_predictions !== undefined
                ? p.correct_predictions
                : correctCount,
        incorrect_predictions:
            p.incorrect_predictions !== undefined
                ? p.incorrect_predictions
                : resolvedCount - correctCount,
    };
}

export async function fetchPunditsSSR(
    sport?: string,
    limit = 20
): Promise<Record<string, unknown>[]> {
    try {
        const backendUrl = new URL(`${API_URL}/v1/pundits/`);
        backendUrl.searchParams.set("limit", String(limit));
        backendUrl.searchParams.set("sort", "accuracy");
        if (sport && sport !== "ALL") {
            backendUrl.searchParams.set("sport", sport.toLowerCase());
        }
        const res = await fetch(backendUrl.toString(), {
            headers: { Accept: "application/json" },
            next: { revalidate: 300 },
        });
        if (!res.ok) {
            console.error(`[fetchPunditsSSR] Backend returned ${res.status}`);
            return [];
        }
        const data = await res.json();
        return (data.pundits || []).map(normalizePundit);
    } catch (err) {
        console.error("[fetchPunditsSSR] Error:", err);
        return [];
    }
}
