"use client";

export type AffiliateVariant = "A" | "B";

export function getAffVariant(): AffiliateVariant {
    if (typeof window === "undefined") return "A";
    const stored = localStorage.getItem("aff_variant");
    if (stored === "A" || stored === "B") return stored;
    const v: AffiliateVariant = Math.random() < 0.5 ? "A" : "B";
    localStorage.setItem("aff_variant", v);
    return v;
}

export type AffiliatePlatform = "draftkings" | "fanduel" | "prizepicks" | "underdog";

const PLATFORM_URLS: Record<AffiliatePlatform, string> = {
    draftkings: process.env.NEXT_PUBLIC_AFF_DRAFTKINGS ?? "https://draftkings.com",
    fanduel: process.env.NEXT_PUBLIC_AFF_FANDUEL ?? "https://fanduel.com",
    prizepicks: process.env.NEXT_PUBLIC_AFF_PRIZEPICKS ?? "https://prizepicks.com",
    underdog: process.env.NEXT_PUBLIC_AFF_UNDERDOG ?? "https://underdogfantasy.com",
};

export const PLATFORM_NAMES: Record<AffiliatePlatform, string> = {
    draftkings: "DraftKings",
    fanduel: "FanDuel",
    prizepicks: "PrizePicks",
    underdog: "Underdog Fantasy",
};

export function getAffUrl(platform: AffiliatePlatform): string {
    return PLATFORM_URLS[platform];
}

export function trackAffClick(
    platform: AffiliatePlatform,
    placement: string,
    variant: AffiliateVariant,
    extra?: Record<string, string>
): void {
    try {
        const w = window as typeof window & { umami?: { track: (event: string, props?: object) => void } };
        w.umami?.track("affiliate_click", {
            platform,
            placement,
            variant,
            ...extra,
        });
    } catch {
        // analytics unavailable — silent
    }
}
