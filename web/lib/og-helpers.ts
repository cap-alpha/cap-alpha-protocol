/**
 * Pure helper functions shared between the OG image route and tests.
 * Extracted here so they can be unit-tested without JSX/React dependencies.
 */

export type StampConfig = {
    text: string;
    color: string;
    borderColor: string;
    bgColor: string;
};

export function getStampConfig(status: string | null): StampConfig {
    switch (status) {
        case "CORRECT":
            return {
                text: "CORRECT ✓",
                color: "#22c55e",
                borderColor: "#22c55e",
                bgColor: "rgba(34,197,94,0.08)",
            };
        case "INCORRECT":
            return {
                text: "INCORRECT ✗",
                color: "#ef4444",
                borderColor: "#ef4444",
                bgColor: "rgba(239,68,68,0.08)",
            };
        default:
            return {
                text: "PENDING",
                color: "#fbbf24",
                borderColor: "#fbbf24",
                bgColor: "rgba(251,191,36,0.08)",
            };
    }
}

export function getCacheControl(status: string | null): string {
    const isResolved = status === "CORRECT" || status === "INCORRECT";
    return isResolved ? "public, max-age=3600, s-maxage=3600" : "no-store";
}

export function fmtDate(ts: string | null | undefined): string {
    if (!ts) return "—";
    try {
        return new Date(ts).toLocaleDateString("en-US", {
            month: "short",
            day: "numeric",
            year: "numeric",
        });
    } catch {
        return "—";
    }
}
