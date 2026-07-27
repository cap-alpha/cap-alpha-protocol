import type { Metadata } from "next";
import type { CSSProperties } from "react";
import { SearchBar } from "@/components/search/SearchBar";
import { SearchResults } from "@/components/search/SearchResults";

// ---------------------------------------------------------------------------
// V1 Data Editorial design tokens — scoped to this page so they don't bleed
// into the global dark theme. Exposed as CSS custom properties on the wrapper.
//
// The 8 values below that are BYTE-IDENTICAL to a canonical token in
// app/globals.css (navy/navy-lt/gold/gold-lt/pos/neg/warn/card) now alias
// that token via hsl(var(...)) instead of repeating the hex literal, so
// this page tracks any future palette change instead of silently
// re-diverging (see web/DESIGN_AUDIT.md §1.3). The remaining values
// (bg/raised/text/md/lt/border/blt) are close to, but not exact matches
// for, existing tokens — left as literal hex here rather than forced onto
// a near-token, since collapsing e.g. --search-md/--search-lt onto
// --ink-2/--ink-3 would visibly lighten this page's secondary text and
// wasn't verified against a screenshot. Tracked as a deferred follow-up.
// ---------------------------------------------------------------------------

// Extend CSSProperties so TypeScript accepts CSS custom properties (--foo: bar)
interface SearchPageStyle extends CSSProperties {
    "--search-bg": string;
    "--search-card": string;
    "--search-raised": string;
    "--search-navy": string;
    "--search-navy-lt": string;
    "--search-gold": string;
    "--search-gold-lt": string;
    "--search-text": string;
    "--search-md": string;
    "--search-lt": string;
    "--search-border": string;
    "--search-blt": string;
    "--search-pos": string;
    "--search-neg": string;
    "--search-warn": string;
}

const pageStyle: SearchPageStyle = {
    "--search-bg": "#F7F4EF",
    "--search-card": "hsl(var(--surface))", // exact match: #FFF == #FFFFFF
    "--search-raised": "#F0EDE8",
    "--search-navy": "hsl(var(--accent-editorial))", // exact match: #1A2744
    "--search-navy-lt": "hsl(var(--accent-editorial-light))", // exact match: #253660
    "--search-gold": "hsl(var(--gold))", // exact match: #B8860B
    "--search-gold-lt": "hsl(var(--gold-light))", // exact match: #D4A017
    "--search-text": "#1C1C1C",
    "--search-md": "#444",
    "--search-lt": "#6B6B6B",
    "--search-border": "#DDD8D0",
    "--search-blt": "#EAE6E0",
    "--search-pos": "hsl(var(--correct))", // exact match: #1A7A4A
    "--search-neg": "hsl(var(--incorrect))", // exact match: #B91C1C
    "--search-warn": "hsl(var(--pending))", // exact match: #92400E
    background: "var(--search-bg)",
    color: "var(--search-text)",
    fontFamily: "'Source Sans 3', system-ui, sans-serif",
    minHeight: "100vh",
};

// ---------------------------------------------------------------------------
// Metadata
// ---------------------------------------------------------------------------

export async function generateMetadata({
    searchParams,
}: {
    searchParams: Promise<{ q?: string }>;
}): Promise<Metadata> {
    const params = await searchParams;
    const q = (params.q ?? "").trim();
    return {
        title: q
            ? `"${q}" — Prediction Search`
            : "Search Predictions — Pundit Ledger",
        description: q
            ? `Every pundit claim matching "${q}", verified and scored.`
            : "Search every pundit prediction across all sports — verified, scored, and cryptographically sealed.",
    };
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default async function SearchPage({
    searchParams,
}: {
    searchParams: Promise<{ q?: string }>;
}) {
    const params = await searchParams;
    const query = (params.q ?? "").trim();

    return (
        /*
         * Root wrapper applies V1 Data Editorial light theme via scoped CSS vars.
         * Playfair Display + Source Sans 3 loaded via Google Fonts import below.
         */
        <div style={pageStyle}>
            {/* Font import: Playfair Display + Source Sans 3 for this page only */}
            <style>{`
                @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,700;0,900;1,600&family=Source+Sans+3:wght@300;400;600;700&display=swap');
            `}</style>

            {/* Search hero — navy background with gold border */}
            <div
                className="px-10 py-12"
                style={{
                    background: "var(--search-navy)",
                    borderBottom: "3px solid var(--search-gold)",
                }}
            >
                <SearchBar initialQuery={query} />
            </div>

            {/* Results (shows trending topics even without a query) */}
            <SearchResults query={query} />
        </div>
    );
}
