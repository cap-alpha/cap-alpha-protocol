"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { ExternalLink } from "lucide-react";
import {
    getAffVariant,
    getAffUrl,
    trackAffClick,
    PLATFORM_NAMES,
    type AffiliatePlatform,
    type AffiliateVariant,
} from "@/lib/affiliate";
import { AffiliateDisclosure } from "@/components/affiliate-disclosure";
import {
    AFFILIATE_LINKS,
    type AffiliatePlatformKey,
    type AffiliateContextKey,
} from "@/lib/affiliate-config";

interface AffiliateCTAProps {
    /** Variant A platform */
    platformA: AffiliatePlatform;
    /** Variant B platform */
    platformB: AffiliatePlatform;
    /** Call-to-action text. Use {platform} as a placeholder for the platform name. */
    cta: string;
    placement: string;
    /** Additional Umami properties (e.g. pundit_id) */
    extra?: Record<string, string>;
    className?: string;
}

export function AffiliateCTA({
    platformA,
    platformB,
    cta,
    placement,
    extra,
    className = "",
}: AffiliateCTAProps) {
    const [variant, setVariant] = useState<AffiliateVariant>("A");

    useEffect(() => {
        setVariant(getAffVariant());
    }, []);

    const platform: AffiliatePlatform = variant === "A" ? platformA : platformB;
    const url = getAffUrl(platform);
    const platformName = PLATFORM_NAMES[platform];
    const ctaText = cta.replace("{platform}", platformName);

    function handleClick() {
        trackAffClick(platform, placement, variant, extra);
    }

    return (
        <div className={`rounded-xl border border-emerald-900/40 bg-emerald-950/20 px-4 py-4 ${className}`}>
            <a
                href={url}
                target="_blank"
                rel="noopener noreferrer sponsored"
                onClick={handleClick}
                className="inline-flex items-center gap-2 text-sm font-semibold text-emerald-400 hover:text-emerald-300 transition-colors"
            >
                {ctaText}
                <ExternalLink className="w-3.5 h-3.5 shrink-0" />
            </a>
            <div className="mt-2">
                <AffiliateDisclosure />
            </div>
        </div>
    );
}

/** Compact inline affiliate link — for use inside text or footers. */
export function AffiliateInlineLink({
    platformA,
    platformB,
    label,
    placement,
    extra,
}: {
    platformA: AffiliatePlatform;
    platformB: AffiliatePlatform;
    label: string;
    placement: string;
    extra?: Record<string, string>;
}) {
    const [variant, setVariant] = useState<AffiliateVariant>("A");

    useEffect(() => {
        setVariant(getAffVariant());
    }, []);

    const platform: AffiliatePlatform = variant === "A" ? platformA : platformB;
    const url = getAffUrl(platform);
    const platformName = PLATFORM_NAMES[platform];
    const text = label.replace("{platform}", platformName);

    return (
        <>
            <a
                href={url}
                target="_blank"
                rel="noopener noreferrer sponsored"
                onClick={() => trackAffClick(platform, placement, variant, extra)}
                className="text-emerald-400 underline hover:text-emerald-300 transition-colors"
            >
                {text}
            </a>
            {" · "}
            <Link
                href="/legal/disclosure"
                className="text-zinc-600 hover:text-zinc-400 transition-colors text-[11px]"
            >
                Affiliate disclosure
            </Link>
        </>
    );
}

// ---------------------------------------------------------------------------
// AffiliateCta — simple placement component (platform × context)
//
// Uses AFFILIATE_LINKS config; renders NOTHING when href is '#affiliate-pending'
// so no broken links ship until Rakuten Advertising approval arrives.
// Swap one line in affiliate-config.ts per platform to go live.
// ---------------------------------------------------------------------------

interface AffiliateCtaProps {
    platform: AffiliatePlatformKey;
    context: AffiliateContextKey;
    className?: string;
}

/**
 * Fires an affiliate click event. Tries @vercel/analytics first (if installed),
 * falls back to Umami (which is already present in this codebase).
 */
function trackCtaClick(
    platform: AffiliatePlatformKey,
    context: AffiliateContextKey
): void {
    try {
        // Vercel Analytics — available when @vercel/analytics is installed
        const va = (window as typeof window & { va?: (event: string, props?: object) => void }).va;
        if (typeof va === "function") {
            va("event", { name: "affiliate_click", data: { platform, context } });
            return;
        }
        // Umami fallback — already in use elsewhere in this codebase
        const w = window as typeof window & {
            umami?: { track: (event: string, props?: object) => void };
        };
        w.umami?.track("affiliate_click", { platform, context });
    } catch {
        // analytics unavailable — silent
    }
}

export function AffiliateCta({ platform, context, className = "" }: AffiliateCtaProps) {
    const entry = AFFILIATE_LINKS[platform];

    // Render nothing while link is pending — zero user-visible impact until approval
    if (entry.href === "#affiliate-pending") return null;

    const ctaText = entry.cta[context];

    return (
        <div
            className={`rounded-xl border border-emerald-900/40 bg-emerald-950/20 px-4 py-4 ${className}`}
        >
            <a
                href={entry.href}
                target="_blank"
                rel="noopener noreferrer sponsored"
                onClick={() => trackCtaClick(platform, context)}
                className="inline-flex items-center gap-2 text-sm font-semibold text-emerald-400 hover:text-emerald-300 transition-colors"
            >
                {ctaText}
                <ExternalLink className="w-3.5 h-3.5 shrink-0" />
            </a>
            <p className="mt-1.5 text-[11px] text-zinc-500">
                Ad — Gambling affiliate link.{" "}
                <Link
                    href="/legal/disclosure"
                    className="underline hover:text-zinc-400 transition-colors"
                >
                    Disclosure
                </Link>
            </p>
        </div>
    );
}
