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
                className="text-zinc-400 hover:text-zinc-400 transition-colors text-[11px]"
            >
                Affiliate disclosure
            </Link>
        </>
    );
}
