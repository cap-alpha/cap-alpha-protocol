import React from "react";
import Link from "next/link";

/**
 * Inline FTC disclosure — place above or adjacent to any sportsbook affiliate link.
 * Required by FTC Endorsement Guides (16 CFR Part 255).
 */
export function AffiliateDisclosure() {
    return (
        <p className="text-xs text-zinc-400 leading-relaxed">
            <span className="font-semibold text-zinc-400">Affiliate link:</span>{" "}
            Cap Alpha may earn a commission if you sign up through this link, at no additional cost to you.{" "}
            <Link href="/legal/disclosure" className="underline hover:text-emerald-500 transition-colors">
                Learn more
            </Link>
        </p>
    );
}
