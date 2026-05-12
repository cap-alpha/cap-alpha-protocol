"use client";

/**
 * SimilarPredictionsExpander — expandable "N pundits made similar predictions" row.
 *
 * Lazy-loads /api/ledger/similar?utterance_id=<hash_short>&limit=3 on first expand.
 * Renders a compact list: pundit name + accuracy + claim + outcome chip.
 *
 * Issue: #769 — bettor discovery journey Phase 1 (PR B)
 */

import { useState, useCallback } from "react";
import Link from "next/link";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface SimilarPrediction {
    pundit_id: string;
    pundit_name: string;
    accuracy_rate?: number | null;
    extracted_claim?: string | null;
    raw_assertion_text?: string | null;
    resolution_status?: string | null;
    prediction_hash_short?: string | null;
    similarity_score?: number | null;
}

interface SimilarResponse {
    similar?: SimilarPrediction[];
    // honeypot fields injected by anti-scraping middleware — intentionally ignored
    [key: string]: unknown;
}

// ---------------------------------------------------------------------------
// Local design constants (match PunditProfileClient DS)
// ---------------------------------------------------------------------------

const DS = {
    navy: "#1A2744",
    gold: "#B8860B",
    card: "#FFFFFF",
    raised: "#F0EDE8",
    border: "#DDD8D0",
    borderLt: "#EAE6E0",
    textMd: "#444444",
    textLt: "#6B6B6B",
    pos: "#1A7A4A",
    neg: "#B91C1C",
    warn: "#92400E",
} as const;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function outcomeChip(status: string | null | undefined): {
    text: string;
    color: string;
    bg: string;
} {
    if (status === "CORRECT") return { text: "Correct", color: DS.pos, bg: "rgba(26,122,74,0.08)" };
    if (status === "INCORRECT") return { text: "Incorrect", color: DS.neg, bg: "rgba(185,28,28,0.06)" };
    return { text: "Pending", color: DS.warn, bg: "rgba(184,134,11,0.06)" };
}

function accuracyPct(rate: number | null | undefined): string {
    if (rate === null || rate === undefined) return "—";
    return `${Math.round(rate * 100)}%`;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface Props {
    /** Hash short (first 12 chars without prefix) used as utterance_id */
    utteranceId: string | null | undefined;
    limit?: number;
}

export function SimilarPredictionsExpander({ utteranceId, limit = 3 }: Props) {
    const [open, setOpen] = useState(false);
    const [loading, setLoading] = useState(false);
    const [items, setItems] = useState<SimilarPrediction[] | null>(null);
    const [error, setError] = useState(false);

    const handleToggle = useCallback(async () => {
        if (!utteranceId) return;

        if (open) {
            setOpen(false);
            return;
        }

        setOpen(true);

        // Only fetch once
        if (items !== null) return;

        setLoading(true);
        setError(false);
        try {
            const url = `/api/ledger/similar?utterance_id=${encodeURIComponent(utteranceId)}&limit=${limit}`;
            const res = await fetch(url, { cache: "no-store" });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data: SimilarResponse = await res.json();
            setItems(data.similar ?? []);
        } catch {
            setError(true);
            setItems([]);
        } finally {
            setLoading(false);
        }
    }, [utteranceId, open, items, limit]);

    if (!utteranceId) return null;

    return (
        <div style={{ marginTop: 8 }}>
            {/* Toggle button */}
            <button
                onClick={handleToggle}
                style={{
                    background: "none",
                    border: `1px solid ${DS.borderLt}`,
                    color: DS.textLt,
                    fontSize: 10,
                    fontWeight: 600,
                    padding: "3px 10px",
                    cursor: "pointer",
                    letterSpacing: "0.5px",
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 4,
                }}
                aria-expanded={open}
            >
                Similar from other pundits {open ? "▲" : "▼"}
            </button>

            {open && (
                <div
                    style={{
                        marginTop: 8,
                        padding: "10px 12px",
                        background: DS.raised,
                        border: `1px solid ${DS.borderLt}`,
                        fontSize: 12,
                    }}
                >
                    {loading && (
                        <div style={{ color: DS.textLt, fontFamily: "var(--font-mono), monospace" }}>
                            Loading similar predictions…
                        </div>
                    )}

                    {!loading && error && (
                        <div style={{ color: DS.neg, fontSize: 11 }}>
                            Could not load similar predictions.
                        </div>
                    )}

                    {!loading && !error && items !== null && items.length === 0 && (
                        <div style={{ color: DS.textLt, fontSize: 11, fontStyle: "italic" }}>
                            No similar predictions found.
                        </div>
                    )}

                    {!loading && !error && items !== null && items.length > 0 && (
                        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                            {items.map((item, idx) => {
                                const chip = outcomeChip(item.resolution_status);
                                const claimText =
                                    item.extracted_claim ||
                                    item.raw_assertion_text ||
                                    "(no claim text)";

                                return (
                                    <div
                                        key={item.prediction_hash_short ?? idx}
                                        style={{
                                            borderBottom:
                                                idx < items.length - 1
                                                    ? `1px solid ${DS.borderLt}`
                                                    : "none",
                                            paddingBottom:
                                                idx < items.length - 1 ? 10 : 0,
                                        }}
                                    >
                                        {/* Pundit name + accuracy */}
                                        <div
                                            style={{
                                                display: "flex",
                                                justifyContent: "space-between",
                                                alignItems: "center",
                                                marginBottom: 4,
                                            }}
                                        >
                                            <Link
                                                href={`/ledger/${encodeURIComponent(item.pundit_id)}`}
                                                style={{
                                                    fontSize: 12,
                                                    fontWeight: 700,
                                                    color: DS.navy,
                                                    textDecoration: "none",
                                                }}
                                            >
                                                {item.pundit_name}
                                            </Link>
                                            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                                                <span
                                                    style={{
                                                        fontFamily:
                                                            "var(--font-mono), monospace",
                                                        fontSize: 11,
                                                        color: DS.textLt,
                                                    }}
                                                >
                                                    {accuracyPct(item.accuracy_rate)} acc
                                                </span>
                                                <span
                                                    style={{
                                                        fontSize: 10,
                                                        fontWeight: 700,
                                                        color: chip.color,
                                                        background: chip.bg,
                                                        padding: "2px 6px",
                                                        border: `1px solid ${chip.color}33`,
                                                    }}
                                                >
                                                    {chip.text}
                                                </span>
                                            </div>
                                        </div>

                                        {/* Claim text */}
                                        <div
                                            style={{
                                                fontSize: 12,
                                                color: DS.textMd,
                                                fontStyle: "italic",
                                                lineHeight: 1.4,
                                            }}
                                        >
                                            &ldquo;{claimText}&rdquo;
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}
