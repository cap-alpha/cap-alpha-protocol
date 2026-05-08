import Link from "next/link";

export type Verdict = "correct" | "incorrect" | "pending";

export interface ClaimResult {
    id: string;
    punditName: string;
    punditSlug: string;
    outlet: string;
    date: string;
    verdict: Verdict;
    quoteText: string;
    /** Substring of quoteText to highlight */
    highlight?: string;
    entities: Array<{ label: string; slug: string }>;
    hash: string;
}

function VerdictBadge({ verdict }: { verdict: Verdict }) {
    if (verdict === "correct") {
        return (
            <span
                className="inline-block text-[10px] font-bold tracking-[0.5px] px-2 py-0.5 uppercase"
                style={{
                    background: "rgba(26,122,74,.1)",
                    color: "var(--search-pos)",
                    border: "1px solid rgba(26,122,74,.2)",
                }}
            >
                ✓ Correct
            </span>
        );
    }
    if (verdict === "incorrect") {
        return (
            <span
                className="inline-block text-[10px] font-bold tracking-[0.5px] px-2 py-0.5 uppercase"
                style={{
                    background: "rgba(185,28,28,.08)",
                    color: "var(--search-neg)",
                    border: "1px solid rgba(185,28,28,.15)",
                }}
            >
                ✗ Incorrect
            </span>
        );
    }
    return (
        <span
            className="inline-block text-[10px] font-bold tracking-[0.5px] px-2 py-0.5 uppercase"
            style={{
                background: "rgba(146,64,14,.08)",
                color: "var(--search-warn)",
                border: "1px solid rgba(146,64,14,.15)",
            }}
        >
            ⟳ Pending
        </span>
    );
}

function highlightText(text: string, highlight?: string): React.ReactNode {
    if (!highlight) return text;
    const idx = text.toLowerCase().indexOf(highlight.toLowerCase());
    if (idx === -1) return text;
    return (
        <>
            {text.slice(0, idx)}
            <mark
                style={{
                    background: "rgba(184,134,11,.15)",
                    color: "inherit",
                    padding: "1px 2px",
                }}
            >
                {text.slice(idx, idx + highlight.length)}
            </mark>
            {text.slice(idx + highlight.length)}
        </>
    );
}

const VERDICT_ACCENT: Record<Verdict, string> = {
    correct: "var(--search-pos)",
    incorrect: "var(--search-neg)",
    pending: "var(--search-gold)",
};

export function ClaimCard({ claim }: { claim: ClaimResult }) {
    const accent = VERDICT_ACCENT[claim.verdict];

    return (
        <article
            className="relative mb-3"
            style={{
                background: "#fff",
                border: "1px solid var(--search-border)",
                paddingLeft: "23px",
            }}
        >
            {/* Left accent bar */}
            <div
                className="absolute left-0 top-0 bottom-0 w-[3px]"
                style={{ background: accent }}
                aria-hidden="true"
            />

            <div className="px-5 py-[18px]">
                {/* Top row */}
                <div className="flex justify-between items-start mb-1.5">
                    <p className="text-[12px]" style={{ color: "var(--search-lt)" }}>
                        <Link
                            href={`/ledger/${encodeURIComponent(claim.punditSlug)}`}
                            className="font-bold transition-colors"
                            style={{ color: "var(--search-navy)" }}
                            onMouseEnter={(e) =>
                                ((e.target as HTMLElement).style.color = "var(--search-gold)")
                            }
                            onMouseLeave={(e) =>
                                ((e.target as HTMLElement).style.color = "var(--search-navy)")
                            }
                        >
                            {claim.punditName}
                        </Link>
                        {" · "}
                        {claim.outlet}
                        {" · "}
                        {claim.date}
                    </p>
                    <VerdictBadge verdict={claim.verdict} />
                </div>

                {/* Quote */}
                <p
                    className="italic text-[15px] leading-[1.55] my-2"
                    style={{
                        fontFamily: "'Playfair Display', serif",
                        color: "var(--search-md)",
                    }}
                >
                    &ldquo;{highlightText(claim.quoteText, claim.highlight)}&rdquo;
                </p>

                {/* Bottom row */}
                <div className="flex items-center justify-between flex-wrap gap-2 mt-3">
                    <div className="flex gap-1.5 flex-wrap">
                        {claim.entities.map((ent) => (
                            <Link
                                key={ent.slug}
                                href={`/search?q=${encodeURIComponent(ent.label)}`}
                                className="text-[11px] font-semibold px-2.5 py-0.5 transition-colors"
                                style={{
                                    color: "var(--search-navy)",
                                    background: "rgba(26,39,68,.07)",
                                    border: "1px solid rgba(26,39,68,.12)",
                                }}
                                onMouseEnter={(e) => {
                                    (e.currentTarget as HTMLElement).style.background =
                                        "var(--search-navy)";
                                    (e.currentTarget as HTMLElement).style.color = "#fff";
                                }}
                                onMouseLeave={(e) => {
                                    (e.currentTarget as HTMLElement).style.background =
                                        "rgba(26,39,68,.07)";
                                    (e.currentTarget as HTMLElement).style.color =
                                        "var(--search-navy)";
                                }}
                            >
                                {ent.label}
                            </Link>
                        ))}
                    </div>
                    <span
                        className="text-[9px]"
                        style={{
                            fontFamily: "'JetBrains Mono', monospace",
                            color: "var(--search-lt)",
                        }}
                    >
                        {claim.hash}
                    </span>
                </div>
            </div>
        </article>
    );
}
