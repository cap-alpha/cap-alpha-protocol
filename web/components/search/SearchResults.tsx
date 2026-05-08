"use client";

import { useState } from "react";
import { ClaimCard, type ClaimResult } from "./ClaimCard";
import { SearchPunditCard, type PunditResult } from "./PunditCard";
import { FilterPanel } from "./FilterPanel";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface SearchFilters {
    verdicts: string[];
    pundits: string[];
    dateRanges: string[];
    confidence: string[];
    claimTypes: string[];
}

const DEFAULT_FILTERS: SearchFilters = {
    verdicts: ["correct", "incorrect", "pending"],
    pundits: ["Adam Schefter", "Shannon Sharpe", "Colin Cowherd", "Peter King"],
    dateRanges: ["2024–25 Season"],
    confidence: ["high", "medium"],
    claimTypes: ["Game Outcome", "Player Prop", "Award"],
};

type Tab = "claims" | "pundits" | "players" | "events";

// ---------------------------------------------------------------------------
// Mock data — realistic NFL content
// ---------------------------------------------------------------------------

const MOCK_CLAIMS: ClaimResult[] = [
    {
        id: "1",
        punditName: "Adam Schefter",
        punditSlug: "adam-schefter",
        outlet: "ESPN",
        date: "Jan 12, 2024",
        verdict: "correct",
        quoteText:
            "Patrick Mahomes will be named MVP of Super Bowl LVIII. His efficiency metrics this season have been the best of his career.",
        highlight: "MVP of Super Bowl",
        entities: [
            { label: "Patrick Mahomes", slug: "patrick-mahomes" },
            { label: "Super Bowl LVIII", slug: "super-bowl-lviii" },
            { label: "KC Chiefs", slug: "kc-chiefs" },
        ],
        hash: "a3f9…7d21",
    },
    {
        id: "2",
        punditName: "Skip Bayless",
        punditSlug: "skip-bayless",
        outlet: "FS1",
        date: "Jan 29, 2024",
        verdict: "incorrect",
        quoteText:
            "Brock Purdy will be named Super Bowl MVP — he outplays Mahomes tonight. 49ers are the better team and I'll say it all week.",
        highlight: "Super Bowl MVP",
        entities: [
            { label: "Brock Purdy", slug: "brock-purdy" },
            { label: "SF 49ers", slug: "sf-49ers" },
            { label: "Super Bowl LVIII", slug: "super-bowl-lviii" },
        ],
        hash: "b19d…3a52",
    },
    {
        id: "3",
        punditName: "Shannon Sharpe",
        punditSlug: "shannon-sharpe",
        outlet: "FS1",
        date: "Feb 1, 2024",
        verdict: "correct",
        quoteText:
            "Mahomes is winning Super Bowl MVP and it won't be close. He is the best player on the best team in the best city.",
        highlight: "Super Bowl MVP",
        entities: [
            { label: "Patrick Mahomes", slug: "patrick-mahomes" },
            { label: "KC Chiefs", slug: "kc-chiefs" },
        ],
        hash: "c72a…8f14",
    },
    {
        id: "4",
        punditName: "Peter King",
        punditSlug: "peter-king",
        outlet: "NBC Sports",
        date: "Sep 3, 2025",
        verdict: "pending",
        quoteText:
            "If Mahomes plays like he did last January, he's the Super Bowl MVP favorite before the season even starts. I'm putting that in writing.",
        highlight: "Super Bowl MVP",
        entities: [
            { label: "Patrick Mahomes", slug: "patrick-mahomes" },
            { label: "Super Bowl LX", slug: "super-bowl-lx" },
        ],
        hash: "d41c…9b37",
    },
];

const MOCK_PUNDITS: PunditResult[] = [
    {
        id: "1",
        slug: "adam-schefter",
        name: "Adam Schefter",
        outlet: "ESPN",
        accuracy: 0.73,
        totalClaims: 312,
        correctClaims: 228,
        incorrectClaims: 84,
    },
    {
        id: "2",
        slug: "peter-king",
        name: "Peter King",
        outlet: "NBC Sports",
        accuracy: 0.61,
        totalClaims: 189,
        correctClaims: 115,
        incorrectClaims: 74,
    },
    {
        id: "3",
        slug: "shannon-sharpe",
        name: "Shannon Sharpe",
        outlet: "FS1",
        accuracy: 0.58,
        totalClaims: 241,
        correctClaims: 140,
        incorrectClaims: 101,
    },
    {
        id: "4",
        slug: "colin-cowherd",
        name: "Colin Cowherd",
        outlet: "FS1",
        accuracy: 0.52,
        totalClaims: 408,
        correctClaims: 212,
        incorrectClaims: 196,
    },
    {
        id: "5",
        slug: "skip-bayless",
        name: "Skip Bayless",
        outlet: "FS1",
        accuracy: 0.31,
        totalClaims: 517,
        correctClaims: 160,
        incorrectClaims: 357,
    },
];

interface TrendingTopic {
    label: string;
    topic: string;
    meta: string;
    href: string;
}

const TRENDING_TOPICS: TrendingTopic[] = [
    {
        label: "Hot this week",
        topic: "Caleb Williams rookie season",
        meta: "184 claims · 62% pending resolution",
        href: "/search?q=Caleb+Williams+rookie",
    },
    {
        label: "Most debated",
        topic: "Cowboys Super Bowl window",
        meta: "892 claims · 71% incorrect",
        href: "/search?q=Cowboys+Super+Bowl",
    },
    {
        label: "Most searched",
        topic: "2024 NFL Draft busts",
        meta: "341 claims · 58% still pending",
        href: "/search?q=2024+NFL+Draft+busts",
    },
    {
        label: "Upcoming resolution",
        topic: "2025 NFL MVP Award",
        meta: "287 claims · resolves Feb 2026",
        href: "/search?q=2025+NFL+MVP",
    },
    {
        label: "Most contested",
        topic: "LeBron final retirement",
        meta: "1,204 claims · pundits split 50/50",
        href: "/search?q=LeBron+retirement",
    },
    {
        label: "Recently resolved",
        topic: "Mahomes fourth Super Bowl",
        meta: "218 claims · 64% correct",
        href: "/search?q=Mahomes+four+Super+Bowls",
    },
];

// ---------------------------------------------------------------------------
// Tab bar
// ---------------------------------------------------------------------------

const TABS: { id: Tab; label: string; count: number }[] = [
    { id: "claims", label: "Claims", count: 218 },
    { id: "pundits", label: "Pundits", count: 47 },
    { id: "players", label: "Players", count: 23 },
    { id: "events", label: "Events", count: 12 },
];

// ---------------------------------------------------------------------------
// Trending section
// ---------------------------------------------------------------------------

function TrendingSection() {
    return (
        <section className="mt-8">
            <div
                className="flex justify-between items-baseline mb-3.5 pb-2"
                style={{ borderTop: "2px solid var(--search-navy)" }}
            >
                <span
                    className="text-xl font-bold pt-2"
                    style={{
                        fontFamily: "'Playfair Display', serif",
                        color: "var(--search-navy)",
                    }}
                >
                    Trending Topics
                </span>
                <a
                    href="#"
                    className="text-[11px] font-bold tracking-[0.5px] uppercase"
                    style={{ color: "var(--search-gold)", textDecoration: "none" }}
                >
                    All topics →
                </a>
            </div>
            <div className="grid grid-cols-2 gap-3">
                {TRENDING_TOPICS.map((t) => (
                    <a
                        key={t.topic}
                        href={t.href}
                        className="block px-4 py-3.5 transition-colors"
                        style={{
                            background: "#fff",
                            border: "1px solid var(--search-border)",
                            textDecoration: "none",
                            color: "inherit",
                        }}
                        onMouseEnter={(e) =>
                            ((e.currentTarget as HTMLElement).style.borderColor =
                                "var(--search-gold)")
                        }
                        onMouseLeave={(e) =>
                            ((e.currentTarget as HTMLElement).style.borderColor =
                                "var(--search-border)")
                        }
                    >
                        <p
                            className="text-[10px] font-bold tracking-[1.5px] uppercase mb-1.5"
                            style={{ color: "var(--search-gold)" }}
                        >
                            {t.label}
                        </p>
                        <p
                            className="text-[15px] font-bold mb-1.5"
                            style={{
                                fontFamily: "'Playfair Display', serif",
                                color: "var(--search-navy)",
                            }}
                        >
                            {t.topic}
                        </p>
                        <p className="text-[11px]" style={{ color: "var(--search-lt)" }}>
                            {t.meta}
                        </p>
                    </a>
                ))}
            </div>
        </section>
    );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

interface SearchResultsProps {
    query: string;
}

export function SearchResults({ query }: SearchResultsProps) {
    const [activeTab, setActiveTab] = useState<Tab>("claims");
    const [sortBy, setSortBy] = useState("Relevance");
    const [filters, setFilters] = useState<SearchFilters>(DEFAULT_FILTERS);

    const totalResults = TABS.reduce((acc, t) => acc + t.count, 0);

    return (
        <div
            className="max-w-[1100px] mx-auto px-10 py-8 grid gap-8"
            style={{ gridTemplateColumns: "220px 1fr" }}
        >
            {/* Filter sidebar */}
            <FilterPanel filters={filters} onChange={setFilters} />

            {/* Results area */}
            <div>
                {/* Header */}
                <div className="flex justify-between items-baseline mb-5">
                    <p className="text-[14px]" style={{ color: "var(--search-md)" }}>
                        <strong style={{ color: "var(--search-navy)" }}>
                            {totalResults} results
                        </strong>
                        {query ? ` for "${query}"` : ""}
                    </p>
                    <div
                        className="flex items-center gap-2 text-[13px]"
                        style={{ color: "var(--search-lt)" }}
                    >
                        Sort:{" "}
                        <select
                            value={sortBy}
                            onChange={(e) => setSortBy(e.target.value)}
                            className="px-2.5 py-1.5 text-[13px]"
                            style={{
                                border: "1px solid var(--search-border)",
                                background: "#fff",
                                color: "var(--search-md)",
                                cursor: "pointer",
                            }}
                        >
                            {[
                                "Relevance",
                                "Newest",
                                "Pundit Accuracy",
                                "Confidence",
                            ].map((opt) => (
                                <option key={opt}>{opt}</option>
                            ))}
                        </select>
                    </div>
                </div>

                {/* Tabs */}
                <div
                    className="flex mb-5"
                    style={{ borderBottom: "1px solid var(--search-border)" }}
                >
                    {TABS.map((tab) => (
                        <button
                            key={tab.id}
                            type="button"
                            onClick={() => setActiveTab(tab.id)}
                            className="text-[13px] font-semibold tracking-[0.4px] uppercase px-4 h-10 flex items-center transition-colors"
                            style={{
                                borderBottom:
                                    activeTab === tab.id
                                        ? "3px solid var(--search-gold-lt)"
                                        : "3px solid transparent",
                                color:
                                    activeTab === tab.id
                                        ? "var(--search-navy)"
                                        : "var(--search-lt)",
                                marginBottom: "-1px",
                                background: "transparent",
                                cursor: "pointer",
                            }}
                        >
                            {tab.label}
                            <span
                                className="ml-1.5 text-[11px] px-1.5 py-0.5 rounded-full"
                                style={{
                                    fontFamily: "'JetBrains Mono', monospace",
                                    background: "var(--search-navy)",
                                    color: "#fff",
                                }}
                            >
                                {tab.count}
                            </span>
                        </button>
                    ))}
                </div>

                {/* Tab content */}
                {activeTab === "claims" && (
                    <>
                        <p
                            className="text-[10px] font-bold tracking-[2px] uppercase mb-2.5"
                            style={{ color: "var(--search-lt)" }}
                        >
                            Most relevant claims
                        </p>
                        {MOCK_CLAIMS.map((claim) => (
                            <ClaimCard key={claim.id} claim={claim} />
                        ))}
                        <div className="text-center pt-7 pb-3">
                            <span
                                className="text-[13px]"
                                style={{ color: "var(--search-lt)" }}
                            >
                                Showing {MOCK_CLAIMS.length} of 218 claims ·{" "}
                                <a
                                    href="#"
                                    className="font-semibold"
                                    style={{
                                        color: "var(--search-gold)",
                                        textDecoration: "none",
                                    }}
                                >
                                    Load next 20 →
                                </a>
                            </span>
                        </div>
                    </>
                )}

                {activeTab === "pundits" && (
                    <>
                        <p
                            className="text-[10px] font-bold tracking-[2px] uppercase mb-2.5"
                            style={{ color: "var(--search-lt)" }}
                        >
                            Matching pundits
                        </p>
                        {MOCK_PUNDITS.map((pundit) => (
                            <SearchPunditCard key={pundit.id} pundit={pundit} />
                        ))}
                    </>
                )}

                {activeTab === "players" && (
                    <div
                        className="py-12 text-center"
                        style={{ color: "var(--search-lt)" }}
                    >
                        <p className="text-[15px]">
                            23 players matched for &ldquo;{query || "your search"}&rdquo;
                        </p>
                        <p className="text-[13px] mt-2">
                            Player entity pages coming soon.
                        </p>
                    </div>
                )}

                {activeTab === "events" && (
                    <div
                        className="py-12 text-center"
                        style={{ color: "var(--search-lt)" }}
                    >
                        <p className="text-[15px]">
                            12 events matched for &ldquo;{query || "your search"}&rdquo;
                        </p>
                        <p className="text-[13px] mt-2">
                            Event timeline pages coming soon.
                        </p>
                    </div>
                )}

                {/* Trending topics — shown on all tabs */}
                <TrendingSection />
            </div>
        </div>
    );
}
