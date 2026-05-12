"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import {
    type PunditSummary,
    type CategoryBreakdown,
    type Prediction,
    type PredictionsResponse,
} from "./page";
import { FollowButton } from "./FollowButton";

// ---------------------------------------------------------------------------
// Design system constants — V1 Data Editorial
// ---------------------------------------------------------------------------

const DS = {
    navy: "#1A2744",
    navyLt: "#253660",
    gold: "#B8860B",
    goldLt: "#D4A017",
    bg: "#F7F4EF",
    card: "#FFFFFF",
    raised: "#F0EDE8",
    border: "#DDD8D0",
    borderLt: "#EAE6E0",
    text: "#1C1C1C",
    textMd: "#444444",
    textLt: "#6B6B6B",
    pos: "#1A7A4A",
    neg: "#B91C1C",
    warn: "#92400E",
} as const;

// ---------------------------------------------------------------------------
// Label maps
// ---------------------------------------------------------------------------

const CATEGORY_LABELS: Record<string, string> = {
    game_outcome: "Game Outcomes",
    player_performance: "Player Props",
    trade: "Trades / Moves",
    draft_pick: "Draft",
    injury: "Injury",
    contract: "Contract",
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Convert a player name to a URL slug for /player/[id] routes */
function slugifyPlayer(name: string): string {
    return encodeURIComponent(name.toLowerCase().replace(/\s+/g, "-"));
}

function getInitials(name: string): string {
    return name
        .split(" ")
        .filter(Boolean)
        .slice(0, 2)
        .map((w) => w[0])
        .join("")
        .toUpperCase();
}

function reliabilityLabel(accuracy: number | null): { label: string; color: string } {
    if (accuracy === null) return { label: "Unscored", color: DS.textLt };
    const pct = accuracy * 100;
    if (pct >= 65) return { label: "Reliable", color: DS.pos };
    if (pct >= 50) return { label: "Average", color: DS.warn };
    return { label: "Unreliable", color: DS.neg };
}

function accuracyColor(accuracy: number | null): string {
    if (accuracy === null) return DS.textLt;
    const pct = accuracy * 100;
    if (pct >= 65) return DS.pos;
    if (pct >= 50) return DS.goldLt;
    return DS.neg;
}

function fmtDate(ts: string | null | undefined): string {
    if (!ts) return "";
    try {
        return new Date(ts).toLocaleDateString("en-US", {
            month: "short",
            day: "numeric",
            year: "numeric",
        });
    } catch {
        return "";
    }
}

function hashShort(hash: string | null | undefined): string {
    if (!hash) return "—";
    const h = hash.replace(/^sha256:/, "");
    return h.slice(0, 4) + "…" + h.slice(-4);
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function Avatar({ name, accuracy }: { name: string; accuracy: number | null }) {
    const initials = getInitials(name);
    const { label, color } = reliabilityLabel(accuracy);

    // Avatar gradient based on reliability
    const gradients: Record<string, string> = {
        Reliable: "linear-gradient(135deg,#1A7A4A,#0a4a2a)",
        Average: "linear-gradient(135deg,#B8860B,#6b4f07)",
        Unreliable: "linear-gradient(135deg,#B91C1C,#6b0e0e)",
        Unscored: "linear-gradient(135deg,#6B6B6B,#333)",
    };

    return (
        <div style={{ position: "relative" }}>
            <div
                style={{
                    width: 100,
                    height: 100,
                    borderRadius: "50%",
                    background: gradients[label] ?? gradients.Unscored,
                    border: `3px solid ${DS.gold}`,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontFamily: "var(--font-serif), Georgia, serif",
                    fontSize: 36,
                    fontWeight: 900,
                    color: "#fff",
                }}
            >
                {initials}
            </div>
            <div
                style={{
                    position: "absolute",
                    bottom: -4,
                    right: -4,
                    background: color,
                    border: `2px solid ${DS.navy}`,
                    borderRadius: 12,
                    padding: "2px 7px",
                    fontSize: 10,
                    fontWeight: 700,
                    color: "#fff",
                    letterSpacing: "0.5px",
                    textTransform: "uppercase",
                    whiteSpace: "nowrap",
                }}
            >
                {label}
            </div>
        </div>
    );
}

function ScoreBox({
    num,
    label,
    sub,
    numColor,
    subUp,
}: {
    num: string;
    label: string;
    sub?: string;
    numColor?: string;
    subUp?: boolean | null;
}) {
    return (
        <div
            style={{
                textAlign: "center",
                padding: "20px 16px",
                borderRight: `1px solid rgba(255,255,255,0.1)`,
            }}
        >
            <div
                style={{
                    fontFamily: "var(--font-mono), 'JetBrains Mono', monospace",
                    fontSize: 28,
                    fontWeight: 600,
                    color: numColor ?? "#fff",
                    lineHeight: 1,
                }}
            >
                {num}
            </div>
            <div
                style={{
                    fontSize: 10,
                    color: "rgba(255,255,255,0.45)",
                    letterSpacing: "1.5px",
                    textTransform: "uppercase",
                    marginTop: 4,
                }}
            >
                {label}
            </div>
            {sub && (
                <div
                    style={{
                        fontSize: 11,
                        marginTop: 4,
                        color: subUp === true ? "#4ADE80" : subUp === false ? "#F87171" : "rgba(255,255,255,0.45)",
                    }}
                >
                    {sub}
                </div>
            )}
        </div>
    );
}

// Status badge
function ClaimBadge({ status }: { status: string }) {
    const cfg: Record<string, { bg: string; color: string; text: string }> = {
        CORRECT: { bg: `rgba(26,122,74,0.1)`, color: DS.pos, text: "✓ Correct" },
        INCORRECT: { bg: `rgba(185,28,28,0.08)`, color: DS.neg, text: "✗ Incorrect" },
        PENDING: { bg: `rgba(184,134,11,0.08)`, color: DS.warn, text: "⟳ Pending" },
    };
    const c = cfg[status] ?? cfg.PENDING;
    return (
        <span
            style={{
                display: "inline-block",
                fontSize: 10,
                fontWeight: 700,
                letterSpacing: "0.5px",
                padding: "3px 8px",
                textTransform: "uppercase",
                background: c.bg,
                color: c.color,
                border: `1px solid ${c.color}33`,
            }}
        >
            {c.text}
        </span>
    );
}

// Left border color for claim cards
function claimBorderColor(status: string): string {
    if (status === "CORRECT") return DS.pos;
    if (status === "INCORRECT") return DS.neg;
    return DS.gold;
}

// Confidence bar
function ConfBar({ confidence, status }: { confidence: number | null; status: string }) {
    if (confidence === null) return null;
    const pct = Math.round(confidence * 100);
    const barColor = status === "CORRECT" ? DS.pos : status === "INCORRECT" ? DS.neg : DS.gold;
    return (
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ fontSize: 11, color: DS.textLt }}>Conf:</span>
            <div
                style={{
                    width: 60,
                    height: 4,
                    background: DS.borderLt,
                    borderRadius: 2,
                    overflow: "hidden",
                }}
            >
                <div
                    style={{
                        height: "100%",
                        borderRadius: 2,
                        background: barColor,
                        width: `${pct}%`,
                    }}
                />
            </div>
            <span
                style={{
                    fontFamily: "var(--font-mono), monospace",
                    fontSize: 12,
                    color: barColor,
                }}
            >
                {confidence.toFixed(2)}
            </span>
        </div>
    );
}

// Accuracy bar for sidebar
function AccuracyBarRow({
    label,
    rate,
}: {
    label: string;
    rate: number | null;
}) {
    const pct = rate !== null ? Math.round(rate * 100) : null;
    let fillColor: string = DS.gold;
    let scoreColor: string = DS.warn;
    if (pct !== null) {
        if (pct >= 60) {
            fillColor = DS.pos;
            scoreColor = DS.pos;
        } else if (pct < 50) {
            fillColor = DS.neg;
            scoreColor = DS.neg;
        }
    }

    return (
        <div
            style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                padding: "8px 0",
                borderBottom: `1px solid ${DS.borderLt}`,
            }}
        >
            <div style={{ fontSize: 13, color: DS.textMd, minWidth: 100 }}>{label}</div>
            <div style={{ flex: 1, margin: "0 12px" }}>
                <div
                    style={{
                        height: 4,
                        background: DS.borderLt,
                        borderRadius: 2,
                        overflow: "hidden",
                    }}
                >
                    <div
                        style={{
                            height: "100%",
                            borderRadius: 2,
                            background: fillColor,
                            width: pct !== null ? `${pct}%` : "0%",
                        }}
                    />
                </div>
            </div>
            <div
                style={{
                    fontFamily: "var(--font-mono), monospace",
                    fontSize: 13,
                    fontWeight: 600,
                    color: pct !== null ? scoreColor : DS.textLt,
                }}
            >
                {pct !== null ? `${pct}%` : "—"}
            </div>
        </div>
    );
}

// ---------------------------------------------------------------------------
// ClaimCard
// ---------------------------------------------------------------------------

function ClaimCard({ p }: { p: Prediction }) {
    const borderColor = claimBorderColor(p.resolution_status);
    const claimText = p.extracted_claim || p.raw_assertion_text || "(no claim text)";
    const dateStr = fmtDate(p.ingestion_timestamp);
    // Build source label: try to extract domain from source_url
    let sourceLabel = "";
    if (p.source_url) {
        try {
            const domain = new URL(p.source_url).hostname.replace(/^www\./, "");
            sourceLabel = domain;
        } catch {
            sourceLabel = "source";
        }
    }

    // Entity chips — derive from target_player_name/target_team for linking
    const playerName = p.target_player_name ?? p.target_player_id ?? null;
    const teamAbbr = p.target_team ?? null;

    return (
        <div
            style={{
                background: DS.card,
                border: `1px solid ${DS.border}`,
                marginBottom: 12,
                padding: "18px 20px 18px 23px",
                position: "relative",
                borderLeft: `3px solid ${borderColor}`,
            }}
        >
            {/* Top row: date + badge */}
            <div
                style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "flex-start",
                    marginBottom: 8,
                }}
            >
                <div
                    style={{
                        fontFamily: "var(--font-mono), monospace",
                        fontSize: 11,
                        color: DS.textLt,
                    }}
                >
                    {dateStr}
                    {sourceLabel && ` · ${sourceLabel}`}
                </div>
                <ClaimBadge status={p.resolution_status} />
            </div>

            {/* Claim quote */}
            <div
                style={{
                    fontFamily: "var(--font-serif), Georgia, serif",
                    fontStyle: "italic",
                    fontSize: 15,
                    lineHeight: 1.55,
                    color: DS.textMd,
                    margin: "6px 0 12px",
                }}
            >
                &ldquo;{claimText}&rdquo;
            </div>

            {/* Bottom row: entities + confidence + hash */}
            <div
                style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    flexWrap: "wrap",
                    gap: 8,
                }}
            >
                {/* Entity chips — linked to player/team pages */}
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    {playerName && (
                        <Link
                            href={`/player/${slugifyPlayer(playerName)}`}
                            style={{
                                fontSize: 11,
                                fontWeight: 600,
                                color: DS.navy,
                                background: `rgba(26,39,68,0.07)`,
                                padding: "3px 10px",
                                border: `1px solid rgba(26,39,68,0.12)`,
                                textDecoration: "none",
                            }}
                        >
                            {playerName}
                        </Link>
                    )}
                    {teamAbbr && (
                        <Link
                            href={`/team/${encodeURIComponent(teamAbbr)}`}
                            style={{
                                fontSize: 11,
                                fontWeight: 600,
                                color: DS.navy,
                                background: `rgba(26,39,68,0.07)`,
                                padding: "3px 10px",
                                border: `1px solid rgba(26,39,68,0.12)`,
                                textDecoration: "none",
                            }}
                        >
                            {teamAbbr}
                        </Link>
                    )}
                    {p.season_year && (
                        <span
                            style={{
                                fontSize: 11,
                                color: DS.textLt,
                                fontFamily: "var(--font-mono), monospace",
                            }}
                        >
                            {p.season_year}
                        </span>
                    )}
                </div>

                {/* Right side: confidence + hash */}
                <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
                    <ConfBar confidence={p.confidence} status={p.resolution_status} />
                    <div
                        style={{
                            fontFamily: "var(--font-mono), monospace",
                            fontSize: 9,
                            color: DS.textLt,
                        }}
                    >
                        {hashShort(p.prediction_hash)}
                    </div>
                </div>
            </div>

            {/* Outcome notes for wrong predictions */}
            {p.outcome_notes && p.resolution_status === "INCORRECT" && (
                <div
                    style={{
                        marginTop: 8,
                        fontSize: 12,
                        color: DS.neg,
                        fontStyle: "italic",
                        lineHeight: 1.4,
                    }}
                >
                    {p.outcome_notes}
                </div>
            )}

            {/* Provenance toggle */}
            <ClaimProvenance p={p} />
        </div>
    );
}

// ---------------------------------------------------------------------------
// ClaimProvenance — collapsible source & provenance section for ClaimCard
// ---------------------------------------------------------------------------

function formatModelLabel(provider: string | null, model: string | null): string | null {
    if (!provider && !model) return null;
    if (!model) return provider;
    const pLow = (provider ?? "").toLowerCase();
    const mLow = (model ?? "").toLowerCase();
    if (pLow === "ollama") {
        const m = model.match(/(\d+)b/i);
        if (mLow.includes("qwen2.5")) return `Qwen 2.5${m ? " " + m[1] + "B" : ""} (Ollama)`;
        if (mLow.includes("llama")) return "Llama (Ollama)";
        return `${model} (Ollama)`;
    }
    if (pLow === "google" || pLow === "gemini") {
        if (mLow.includes("gemini-1.5")) return "Gemini 1.5";
        if (mLow.includes("gemini-2")) return "Gemini 2";
        return model ?? "Gemini";
    }
    if (pLow === "anthropic") return `Claude (${model})`;
    return model;
}

function formatOutcomeSrc(source: string | null): string | null {
    if (!source) return null;
    const map: Record<string, string> = {
        sportsdataio: "SportsData.io",
        pfr: "Pro Football Reference",
        spotrac: "Spotrac",
        manual: "Manual review",
        "official-team": "Official team report",
    };
    return map[source.toLowerCase()] ?? source;
}

function qualityBadge(score: number): { label: string; color: string } {
    if (score >= 0.7) return { label: "HIGH", color: DS.pos };
    if (score >= 0.4) return { label: "MED", color: DS.warn };
    return { label: "LOW", color: DS.neg };
}

function ClaimProvenance({ p }: { p: Prediction }) {
    const [open, setOpen] = useState(false);

    const model = formatModelLabel(p.llm_provider, p.llm_model);
    const src = formatOutcomeSrc(p.outcome_source);
    const rawDiffers =
        p.raw_assertion_text &&
        p.extracted_claim &&
        p.raw_assertion_text.trim() !== p.extracted_claim.trim();

    const hasData = model || (p.quality_score !== null && p.quality_score !== undefined) || src;
    if (!hasData) return null;

    return (
        <div style={{ marginTop: 10 }}>
            <button
                onClick={() => setOpen((v) => !v)}
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
                ⓘ Source &amp; Provenance {open ? "▲" : "▼"}
            </button>

            {open && (
                <div
                    style={{
                        marginTop: 8,
                        padding: "12px 14px",
                        background: DS.raised,
                        border: `1px solid ${DS.borderLt}`,
                        fontSize: 12,
                        lineHeight: 1.5,
                    }}
                >
                    {/* Raw quote — only shown if different from extracted_claim */}
                    {rawDiffers && p.raw_assertion_text && (
                        <div style={{ marginBottom: 10 }}>
                            <div
                                style={{
                                    fontSize: 9,
                                    fontWeight: 700,
                                    letterSpacing: 1.5,
                                    textTransform: "uppercase",
                                    color: DS.gold,
                                    marginBottom: 4,
                                }}
                            >
                                Raw Quote
                            </div>
                            <div
                                style={{
                                    fontStyle: "italic",
                                    color: DS.textMd,
                                    borderLeft: `2px solid ${DS.borderLt}`,
                                    paddingLeft: 8,
                                }}
                            >
                                &ldquo;{p.raw_assertion_text}&rdquo;
                            </div>
                        </div>
                    )}

                    {/* Extraction model + quality */}
                    {(model || (p.quality_score !== null && p.quality_score !== undefined)) && (
                        <div style={{ marginBottom: src ? 10 : 0 }}>
                            <div
                                style={{
                                    fontSize: 9,
                                    fontWeight: 700,
                                    letterSpacing: 1.5,
                                    textTransform: "uppercase",
                                    color: DS.gold,
                                    marginBottom: 4,
                                }}
                            >
                                Extraction
                            </div>
                            <div style={{ color: DS.textMd, display: "flex", flexWrap: "wrap", gap: 8 }}>
                                {model && <span>{model}</span>}
                                {p.prompt_version && (
                                    <span style={{ color: DS.textLt }}>· Prompt {p.prompt_version}</span>
                                )}
                                {p.quality_score !== null && p.quality_score !== undefined && (() => {
                                    const q = qualityBadge(p.quality_score);
                                    return (
                                        <span>
                                            · Quality:{" "}
                                            <span style={{ color: q.color, fontWeight: 700 }}>
                                                {p.quality_score.toFixed(2)} ({q.label})
                                            </span>
                                        </span>
                                    );
                                })()}
                            </div>
                        </div>
                    )}

                    {/* Resolution source */}
                    {src && (
                        <div>
                            <div
                                style={{
                                    fontSize: 9,
                                    fontWeight: 700,
                                    letterSpacing: 1.5,
                                    textTransform: "uppercase",
                                    color: DS.gold,
                                    marginBottom: 4,
                                }}
                            >
                                Resolution Source
                            </div>
                            <div style={{ color: DS.textMd }}>
                                Resolved via {src}
                                {p.outcome_notes && p.resolution_status !== "INCORRECT" && (
                                    <span style={{ color: DS.textLt, fontStyle: "italic" }}>
                                        {" "}— {p.outcome_notes}
                                    </span>
                                )}
                            </div>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}

// ---------------------------------------------------------------------------
// Main client component
// ---------------------------------------------------------------------------

type ActiveTab = "all" | "correct" | "incorrect" | "pending";
type FilterCategory = "all" | "game_outcome" | "player_performance" | "trade" | "draft_pick" | "injury" | "contract";
type SortMode = "newest" | "highest_conf" | "most_wrong";

interface Props {
    pundit: PunditSummary;
    accuracyByCategory: CategoryBreakdown[];
    initialPredictions: PredictionsResponse | null;
    punditId: string;
    isFollowing: boolean;
    isAuthenticated: boolean;
}

export function PunditProfileClient({
    pundit,
    accuracyByCategory,
    initialPredictions,
    punditId,
    isFollowing,
    isAuthenticated,
}: Props) {
    const [activeTab, setActiveTab] = useState<ActiveTab>("all");
    const [filterCat, setFilterCat] = useState<FilterCategory>("all");
    const [sortMode, setSortMode] = useState<SortMode>("newest");

    const [predictions, setPredictions] = useState<Prediction[]>(
        initialPredictions?.predictions ?? []
    );
    const [page, setPage] = useState(initialPredictions?.page ?? 1);
    const [totalPages, setTotalPages] = useState(initialPredictions?.pages ?? 1);
    const [total, setTotal] = useState(initialPredictions?.total ?? 0);
    const [loading, setLoading] = useState(false);

    const incorrectCount = (pundit.resolved_count ?? 0) - (pundit.correct_count ?? 0);
    const pendingCount = (pundit.total_predictions ?? 0) - (pundit.resolved_count ?? 0);

    // Tab filter map
    const tabStatusMap: Record<ActiveTab, string | null> = {
        all: null,
        correct: "CORRECT",
        incorrect: "INCORRECT",
        pending: "PENDING",
    };

    const loadPredictions = useCallback(
        async (nextPage: number, tab: ActiveTab) => {
            setLoading(true);
            const statusParam = tabStatusMap[tab] ? `&status=${tabStatusMap[tab]}` : "";
            try {
                const res = await fetch(
                    `/api/ledger/pundits/${encodeURIComponent(punditId)}/predictions?page=${nextPage}&page_size=20${statusParam}`
                );
                if (!res.ok) return;
                const data: PredictionsResponse = await res.json();
                if (nextPage === 1) {
                    setPredictions(data.predictions);
                } else {
                    setPredictions((prev) => [...prev, ...data.predictions]);
                }
                setPage(data.page);
                setTotalPages(data.pages);
                setTotal(data.total);
            } catch {
                // silently ignore
            } finally {
                setLoading(false);
            }
        },
        [punditId] // eslint-disable-line react-hooks/exhaustive-deps
    );

    // When tab changes, reload
    useEffect(() => {
        loadPredictions(1, activeTab);
    }, [activeTab]); // eslint-disable-line react-hooks/exhaustive-deps

    // Client-side filter + sort
    const filtered = predictions.filter((p) => {
        if (filterCat !== "all" && p.claim_category !== filterCat) return false;
        return true;
    });

    const sorted = [...filtered].sort((a, b) => {
        if (sortMode === "newest") {
            return (
                new Date(b.ingestion_timestamp).getTime() -
                new Date(a.ingestion_timestamp).getTime()
            );
        }
        if (sortMode === "highest_conf") {
            return (b.confidence ?? 0) - (a.confidence ?? 0);
        }
        if (sortMode === "most_wrong") {
            // wrong first, then by date
            if (a.resolution_status === "INCORRECT" && b.resolution_status !== "INCORRECT") return -1;
            if (b.resolution_status === "INCORRECT" && a.resolution_status !== "INCORRECT") return 1;
            return 0;
        }
        return 0;
    });

    const showMore = page < totalPages;

    const { label: reliLabel, color: reliColor } = reliabilityLabel(pundit.accuracy_rate);
    const accColor = accuracyColor(pundit.accuracy_rate);

    // Rank: TODO — wire when leaderboard API exposes rank (#807)
    // For now, show "—" with a TODO comment
    const rankDisplay = "—"; // TODO: wire from /v1/leaderboard when rank field is exposed (#807)

    // Build ticker items from category breakdown for the header
    const brierDisplay =
        (pundit.brier_score ?? pundit.avg_brier_score) !== null
            ? (pundit.brier_score ?? pundit.avg_brier_score)!.toFixed(3)
            : "—";
    const brierColor =
        (pundit.brier_score ?? pundit.avg_brier_score) !== null
            ? (pundit.brier_score ?? pundit.avg_brier_score)! > 0.25
                ? DS.neg
                : DS.goldLt
            : DS.textLt;

    const accuracyDisplay =
        pundit.accuracy_rate !== null
            ? `${(pundit.accuracy_rate * 100).toFixed(1)}`
            : "—";

    return (
        <div style={{ background: DS.bg, minHeight: "100vh", color: DS.text }}>
            {/* Breadcrumb */}
            <div
                style={{
                    background: DS.card,
                    borderBottom: `1px solid ${DS.border}`,
                    padding: "10px 40px",
                    fontSize: 12,
                    color: DS.textLt,
                }}
            >
                <Link href="/" style={{ color: DS.gold, textDecoration: "none" }}>
                    CapAlpha
                </Link>
                <span style={{ margin: "0 4px" }}>›</span>
                <Link href="/ledger" style={{ color: DS.gold, textDecoration: "none" }}>
                    Pundits
                </Link>
                <span style={{ margin: "0 4px" }}>›</span>
                <span>{pundit.pundit_name}</span>
            </div>

            {/* ===== PUNDIT HEADER ===== */}
            <div style={{ background: DS.navy, color: "#fff", padding: "40px" }}>
                <div
                    style={{
                        maxWidth: 1100,
                        margin: "0 auto",
                        display: "grid",
                        gridTemplateColumns: "auto 1fr auto",
                        gap: 32,
                        alignItems: "start",
                    }}
                >
                    {/* Avatar */}
                    <Avatar name={pundit.pundit_name} accuracy={pundit.accuracy_rate} />

                    {/* Name + outlet + tags + follow */}
                    <div>
                        <div
                            style={{
                                fontFamily: "var(--font-serif), Georgia, serif",
                                fontSize: 36,
                                fontWeight: 900,
                                lineHeight: 1,
                                marginBottom: 6,
                            }}
                        >
                            {pundit.pundit_name}
                        </div>
                        <div style={{ fontSize: 14, color: "rgba(255,255,255,0.55)", marginBottom: 16 }}>
                            {pundit.sport}
                        </div>
                        {/* Topic tags + follow button */}
                        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
                            <span
                                style={{
                                    background: "rgba(255,255,255,0.1)",
                                    border: "1px solid rgba(255,255,255,0.15)",
                                    color: "rgba(255,255,255,0.7)",
                                    fontSize: 11,
                                    fontWeight: 600,
                                    padding: "3px 10px",
                                    letterSpacing: "0.5px",
                                    textTransform: "uppercase",
                                }}
                            >
                                {pundit.sport}
                            </span>
                            <span
                                style={{
                                    background: "rgba(255,255,255,0.1)",
                                    border: "1px solid rgba(255,255,255,0.15)",
                                    color: "rgba(255,255,255,0.7)",
                                    fontSize: 11,
                                    fontWeight: 600,
                                    padding: "3px 10px",
                                    letterSpacing: "0.5px",
                                    textTransform: "uppercase",
                                }}
                            >
                                {reliLabel}
                            </span>
                            <FollowButton
                                punditId={punditId}
                                punditName={pundit.pundit_name}
                                isFollowing={isFollowing}
                                isAuthenticated={isAuthenticated}
                            />
                        </div>
                    </div>

                    {/* Score grid — 4 boxes */}
                    <div
                        style={{
                            display: "grid",
                            gridTemplateColumns: "repeat(4, 1fr)",
                            border: "1px solid rgba(255,255,255,0.1)",
                        }}
                    >
                        <ScoreBox
                            num={accuracyDisplay === "—" ? "—" : `${accuracyDisplay}%`}
                            label="Accuracy"
                            numColor={accColor}
                            sub={
                                pundit.accuracy_rate !== null
                                    ? pundit.accuracy_rate >= 0.65
                                        ? "↑ above avg"
                                        : pundit.accuracy_rate < 0.5
                                        ? "↓ below avg"
                                        : "≈ near avg"
                                    : undefined
                            }
                            subUp={
                                pundit.accuracy_rate !== null
                                    ? pundit.accuracy_rate >= 0.65
                                        ? true
                                        : false
                                    : null
                            }
                        />
                        <ScoreBox
                            num={brierDisplay}
                            label="Brier Score"
                            numColor={brierColor}
                            sub="↓ lower is better"
                        />
                        <ScoreBox
                            num={pundit.total_predictions.toLocaleString()}
                            label="Claims Total"
                            numColor={DS.goldLt}
                        />
                        <div
                            style={{
                                textAlign: "center",
                                padding: "20px 16px",
                            }}
                        >
                            <div
                                style={{
                                    fontFamily: "var(--font-mono), monospace",
                                    fontSize: 28,
                                    fontWeight: 600,
                                    color: DS.textLt,
                                    lineHeight: 1,
                                }}
                            >
                                {rankDisplay}
                            </div>
                            <div
                                style={{
                                    fontSize: 10,
                                    color: "rgba(255,255,255,0.45)",
                                    letterSpacing: "1.5px",
                                    textTransform: "uppercase",
                                    marginTop: 4,
                                }}
                            >
                                Rank
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            {/* ===== TABS ===== */}
            <div
                style={{
                    background: DS.card,
                    borderBottom: `1px solid ${DS.border}`,
                    padding: "0 40px",
                }}
            >
                <div style={{ maxWidth: 1100, margin: "0 auto", display: "flex" }}>
                    {(
                        [
                            { id: "all", label: `All Claims (${pundit.total_predictions.toLocaleString()})` },
                            { id: "correct", label: `Correct (${pundit.correct_count})` },
                            { id: "incorrect", label: `Incorrect (${incorrectCount})` },
                            { id: "pending", label: `Pending (${pendingCount})` },
                        ] as { id: ActiveTab; label: string }[]
                    ).map(({ id, label }) => (
                        <button
                            key={id}
                            onClick={() => setActiveTab(id)}
                            style={{
                                fontSize: 13,
                                fontWeight: 600,
                                letterSpacing: "0.4px",
                                textTransform: "uppercase",
                                padding: "0 20px",
                                height: 44,
                                display: "flex",
                                alignItems: "center",
                                cursor: "pointer",
                                background: "none",
                                border: "none",
                                borderBottom: activeTab === id ? `3px solid ${DS.gold}` : "3px solid transparent",
                                marginBottom: -1,
                                color: activeTab === id ? DS.navy : DS.textLt,
                            }}
                        >
                            {label}
                        </button>
                    ))}
                </div>
            </div>

            {/* ===== MAIN CONTENT ===== */}
            <div style={{ maxWidth: 1100, margin: "0 auto", padding: "32px 40px" }}>
                <div
                    style={{
                        display: "grid",
                        gridTemplateColumns: "1fr 300px",
                        gap: 32,
                    }}
                >
                    {/* LEFT: Claims feed */}
                    <div>
                        {/* Filter row */}
                        <div
                            style={{
                                display: "flex",
                                gap: 10,
                                alignItems: "center",
                                marginBottom: 20,
                                flexWrap: "wrap",
                            }}
                        >
                            <span
                                style={{
                                    fontSize: 12,
                                    fontWeight: 600,
                                    color: DS.textLt,
                                    textTransform: "uppercase",
                                    letterSpacing: "0.5px",
                                    marginRight: 4,
                                }}
                            >
                                Filter:
                            </span>
                            {(
                                [
                                    { id: "all", label: "All" },
                                    { id: "game_outcome", label: "Game Outcomes" },
                                    { id: "player_performance", label: "Player Props" },
                                    { id: "trade", label: "Trades" },
                                    { id: "draft_pick", label: "Draft" },
                                    { id: "injury", label: "Injury" },
                                ] as { id: FilterCategory; label: string }[]
                            ).map(({ id, label }) => (
                                <button
                                    key={id}
                                    onClick={() => setFilterCat(id)}
                                    style={{
                                        background: filterCat === id ? DS.navy : "none",
                                        border: `1px solid ${filterCat === id ? DS.navy : DS.border}`,
                                        color: filterCat === id ? "#fff" : DS.textMd,
                                        fontSize: 12,
                                        fontWeight: 600,
                                        padding: "5px 12px",
                                        cursor: "pointer",
                                        letterSpacing: "0.3px",
                                    }}
                                >
                                    {label}
                                </button>
                            ))}

                            <span
                                style={{
                                    fontSize: 12,
                                    fontWeight: 600,
                                    color: DS.textLt,
                                    textTransform: "uppercase",
                                    letterSpacing: "0.5px",
                                    margin: "0 4px 0 12px",
                                }}
                            >
                                Sort:
                            </span>
                            {(
                                [
                                    { id: "newest", label: "Newest" },
                                    { id: "highest_conf", label: "Highest Conf." },
                                    { id: "most_wrong", label: "Most Wrong" },
                                ] as { id: SortMode; label: string }[]
                            ).map(({ id, label }) => (
                                <button
                                    key={id}
                                    onClick={() => setSortMode(id)}
                                    style={{
                                        background: sortMode === id ? DS.navy : "none",
                                        border: `1px solid ${sortMode === id ? DS.navy : DS.border}`,
                                        color: sortMode === id ? "#fff" : DS.textMd,
                                        fontSize: 12,
                                        fontWeight: 600,
                                        padding: "5px 12px",
                                        cursor: "pointer",
                                        letterSpacing: "0.3px",
                                    }}
                                >
                                    {label}
                                </button>
                            ))}
                        </div>

                        {/* Claims list */}
                        {loading && sorted.length === 0 ? (
                            <div
                                style={{
                                    textAlign: "center",
                                    padding: "48px 0",
                                    color: DS.textLt,
                                    fontSize: 14,
                                    fontFamily: "var(--font-mono), monospace",
                                }}
                            >
                                Loading claims…
                            </div>
                        ) : sorted.length === 0 ? (
                            <div
                                style={{
                                    textAlign: "center",
                                    padding: "48px 0",
                                    color: DS.textLt,
                                    fontSize: 14,
                                }}
                            >
                                No claims found for this filter.
                            </div>
                        ) : (
                            sorted.map((p) => <ClaimCard key={p.prediction_hash} p={p} />)
                        )}

                        {/* Load more */}
                        {showMore && !loading && (
                            <div style={{ textAlign: "center", padding: "24px 0" }}>
                                <button
                                    onClick={() => loadPredictions(page + 1, activeTab)}
                                    style={{
                                        background: "none",
                                        border: `1px solid ${DS.navy}`,
                                        color: DS.navy,
                                        padding: "8px 24px",
                                        fontSize: 13,
                                        fontWeight: 600,
                                        cursor: "pointer",
                                        letterSpacing: "0.5px",
                                    }}
                                >
                                    Load more ({total - sorted.length} remaining)
                                </button>
                            </div>
                        )}
                        {loading && sorted.length > 0 && (
                            <div
                                style={{
                                    textAlign: "center",
                                    padding: "16px 0",
                                    color: DS.textLt,
                                    fontSize: 12,
                                    fontFamily: "var(--font-mono), monospace",
                                }}
                            >
                                Loading…
                            </div>
                        )}

                        {/* Total count */}
                        {sorted.length > 0 && (
                            <div
                                style={{
                                    textAlign: "center",
                                    padding: "8px 0",
                                    fontSize: 13,
                                    color: DS.textLt,
                                }}
                            >
                                Showing {sorted.length} of {total} claims
                            </div>
                        )}
                    </div>

                    {/* RIGHT: Sidebar */}
                    <div>
                        {/* Accuracy by category */}
                        <div
                            style={{
                                background: DS.card,
                                border: `1px solid ${DS.border}`,
                                padding: 20,
                                marginBottom: 20,
                            }}
                        >
                            <div
                                style={{
                                    fontSize: 11,
                                    fontWeight: 700,
                                    letterSpacing: 2,
                                    textTransform: "uppercase",
                                    color: DS.gold,
                                    borderBottom: `1px solid ${DS.border}`,
                                    paddingBottom: 10,
                                    marginBottom: 14,
                                }}
                            >
                                Accuracy by Category
                            </div>
                            {accuracyByCategory.length > 0 ? (
                                accuracyByCategory.map((cat) => (
                                    <AccuracyBarRow
                                        key={cat.claim_category}
                                        label={CATEGORY_LABELS[cat.claim_category] ?? cat.claim_category}
                                        rate={cat.accuracy_rate}
                                    />
                                ))
                            ) : (
                                /* TODO: wire to /v1/pundits/{id} accuracy_by_category when #807 populates data */
                                <div style={{ color: DS.textLt, fontSize: 13 }}>
                                    No category data yet.
                                </div>
                            )}
                        </div>

                        {/* Similar pundits — TODO: wire to leaderboard API (#807) */}
                        <div
                            style={{
                                background: DS.card,
                                border: `1px solid ${DS.border}`,
                                padding: 20,
                                marginBottom: 20,
                            }}
                        >
                            <div
                                style={{
                                    fontSize: 11,
                                    fontWeight: 700,
                                    letterSpacing: 2,
                                    textTransform: "uppercase",
                                    color: DS.gold,
                                    borderBottom: `1px solid ${DS.border}`,
                                    paddingBottom: 10,
                                    marginBottom: 14,
                                }}
                            >
                                Similar Pundits
                            </div>
                            {/* TODO: fetch pundits with close accuracy from /v1/leaderboard and display here (#807) */}
                            <div
                                style={{
                                    color: DS.textLt,
                                    fontSize: 13,
                                    fontStyle: "italic",
                                }}
                            >
                                Similar pundit comparison coming soon.
                            </div>
                        </div>

                        {/* Ledger integrity */}
                        <div
                            style={{
                                background: DS.card,
                                border: `1px solid ${DS.border}`,
                                padding: 20,
                            }}
                        >
                            <div
                                style={{
                                    fontSize: 11,
                                    fontWeight: 700,
                                    letterSpacing: 2,
                                    textTransform: "uppercase",
                                    color: DS.gold,
                                    borderBottom: `1px solid ${DS.border}`,
                                    paddingBottom: 10,
                                    marginBottom: 14,
                                }}
                            >
                                Ledger Integrity
                            </div>
                            <LedgerIntegrityBlock
                                punditId={punditId}
                                totalClaims={pundit.total_predictions}
                                predictions={predictions}
                            />
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}

// ---------------------------------------------------------------------------
// Ledger integrity sidebar block — fetches chain head from predictions
// ---------------------------------------------------------------------------

function LedgerIntegrityBlock({
    punditId,
    totalClaims,
    predictions,
}: {
    punditId: string;
    totalClaims: number;
    predictions: Prediction[];
}) {
    // Use the most recent prediction hash as the "chain head" proxy
    // TODO: wire to /v1/integrity/verify?pundit_id={id} when endpoint supports per-pundit filtering (#807)
    const headHash = predictions.length > 0 ? predictions[0].prediction_hash : null;
    const shortHash = headHash
        ? headHash.replace(/^sha256:/, "").match(/.{1,8}/g)?.slice(0, 4).join("\n")
        : null;

    return (
        <div style={{ textAlign: "center", padding: 16 }}>
            <div style={{ fontSize: 11, color: DS.textLt, marginBottom: 6 }}>Chain head hash</div>
            {shortHash ? (
                <div
                    style={{
                        fontFamily: "var(--font-mono), monospace",
                        fontSize: 11,
                        color: DS.textLt,
                        wordBreak: "break-all",
                        lineHeight: 1.8,
                        marginBottom: 8,
                    }}
                >
                    {shortHash}
                </div>
            ) : (
                <div style={{ fontSize: 12, color: DS.textLt, marginBottom: 8 }}>—</div>
            )}
            <div style={{ fontSize: 11, color: DS.textLt, marginBottom: 10 }}>
                {totalClaims.toLocaleString()} entries · Cryptographically sealed
            </div>
            <Link
                href="/ledger"
                style={{
                    display: "block",
                    background: "none",
                    border: `1px solid ${DS.navy}`,
                    color: DS.navy,
                    fontSize: 11,
                    fontWeight: 700,
                    padding: "6px 14px",
                    cursor: "pointer",
                    letterSpacing: "0.5px",
                    textTransform: "uppercase",
                    width: "100%",
                    textAlign: "center",
                    textDecoration: "none",
                    boxSizing: "border-box",
                }}
            >
                View Ledger →
            </Link>
        </div>
    );
}

