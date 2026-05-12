"use client";

import { useState, useTransition } from "react";
import Link from "next/link";
import { unfollowPundit } from "@/app/actions/follow";

interface PunditSummary {
    pundit_id: string;
    pundit_name: string;
    sport: string;
    total_predictions: number;
    resolved_count: number;
    correct_count: number;
    accuracy_rate: number | null;
    avg_brier_score: number | null;
    brier_score: number | null;
    avg_weighted_score: number | null;
    overconfidence_score: number | null;
}

interface Props {
    pundits: PunditSummary[];
    followedIds: string[];
}

// Design system — matches the ledger page DS
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

function accuracyColor(rate: number | null): string {
    if (rate === null) return DS.textLt;
    if (rate >= 0.65) return DS.pos;
    if (rate >= 0.5) return DS.goldLt;
    return DS.neg;
}

function reliabilityLabel(rate: number | null): string {
    if (rate === null) return "Unscored";
    const pct = rate * 100;
    if (pct >= 65) return "Reliable";
    if (pct >= 50) return "Average";
    return "Unreliable";
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

function PunditCard({
    pundit,
    onUnfollow,
    isUnfollowing,
}: {
    pundit: PunditSummary;
    onUnfollow: (id: string) => void;
    isUnfollowing: boolean;
}) {
    const accuracyPct =
        pundit.accuracy_rate !== null
            ? `${Math.round(pundit.accuracy_rate * 100)}%`
            : "—";
    const accColor = accuracyColor(pundit.accuracy_rate);
    const label = reliabilityLabel(pundit.accuracy_rate);
    const pendingCount = pundit.total_predictions - pundit.resolved_count;
    const brierDisplay =
        (pundit.brier_score ?? pundit.avg_brier_score) !== null
            ? (pundit.brier_score ?? pundit.avg_brier_score)!.toFixed(3)
            : "—";

    const gradients: Record<string, string> = {
        Reliable: "linear-gradient(135deg,#1A7A4A,#0a4a2a)",
        Average: "linear-gradient(135deg,#B8860B,#6b4f07)",
        Unreliable: "linear-gradient(135deg,#B91C1C,#6b0e0e)",
        Unscored: "linear-gradient(135deg,#6B6B6B,#333)",
    };

    return (
        <div
            style={{
                background: DS.card,
                border: `1px solid ${DS.border}`,
                borderLeft: `3px solid ${DS.gold}`,
                padding: "20px 24px",
                display: "flex",
                alignItems: "center",
                gap: 20,
                marginBottom: 12,
            }}
        >
            {/* Avatar */}
            <div
                style={{
                    width: 56,
                    height: 56,
                    borderRadius: "50%",
                    background: gradients[label] ?? gradients.Unscored,
                    border: `2px solid ${DS.gold}`,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontFamily: "var(--font-serif), Georgia, serif",
                    fontSize: 20,
                    fontWeight: 900,
                    color: "#fff",
                    flexShrink: 0,
                }}
            >
                {getInitials(pundit.pundit_name)}
            </div>

            {/* Info */}
            <div style={{ flex: 1, minWidth: 0 }}>
                <Link
                    href={`/ledger/${pundit.pundit_id}`}
                    style={{
                        fontFamily: "var(--font-serif), Georgia, serif",
                        fontSize: 18,
                        fontWeight: 700,
                        color: DS.navy,
                        textDecoration: "none",
                    }}
                >
                    {pundit.pundit_name}
                </Link>
                <div
                    style={{
                        fontSize: 12,
                        color: DS.textLt,
                        marginTop: 2,
                        marginBottom: 10,
                    }}
                >
                    {pundit.sport} · {label}
                </div>

                {/* Stats row */}
                <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
                    <div>
                        <div
                            style={{
                                fontFamily: "var(--font-mono), monospace",
                                fontSize: 18,
                                fontWeight: 600,
                                color: accColor,
                                lineHeight: 1,
                            }}
                        >
                            {accuracyPct}
                        </div>
                        <div
                            style={{
                                fontSize: 10,
                                color: DS.textLt,
                                textTransform: "uppercase",
                                letterSpacing: "1px",
                                marginTop: 2,
                            }}
                        >
                            Accuracy
                        </div>
                    </div>
                    <div>
                        <div
                            style={{
                                fontFamily: "var(--font-mono), monospace",
                                fontSize: 18,
                                fontWeight: 600,
                                color: DS.text,
                                lineHeight: 1,
                            }}
                        >
                            {brierDisplay}
                        </div>
                        <div
                            style={{
                                fontSize: 10,
                                color: DS.textLt,
                                textTransform: "uppercase",
                                letterSpacing: "1px",
                                marginTop: 2,
                            }}
                        >
                            Brier Score
                        </div>
                    </div>
                    <div>
                        <div
                            style={{
                                fontFamily: "var(--font-mono), monospace",
                                fontSize: 18,
                                fontWeight: 600,
                                color: DS.text,
                                lineHeight: 1,
                            }}
                        >
                            {pundit.total_predictions.toLocaleString()}
                        </div>
                        <div
                            style={{
                                fontSize: 10,
                                color: DS.textLt,
                                textTransform: "uppercase",
                                letterSpacing: "1px",
                                marginTop: 2,
                            }}
                        >
                            Predictions
                        </div>
                    </div>
                    <div>
                        <div
                            style={{
                                fontFamily: "var(--font-mono), monospace",
                                fontSize: 18,
                                fontWeight: 600,
                                color: pendingCount > 0 ? DS.warn : DS.textLt,
                                lineHeight: 1,
                            }}
                        >
                            {pendingCount}
                        </div>
                        <div
                            style={{
                                fontSize: 10,
                                color: DS.textLt,
                                textTransform: "uppercase",
                                letterSpacing: "1px",
                                marginTop: 2,
                            }}
                        >
                            Pending
                        </div>
                    </div>
                </div>
            </div>

            {/* Actions */}
            <div style={{ display: "flex", flexDirection: "column", gap: 8, alignItems: "flex-end" }}>
                <Link
                    href={`/ledger/${pundit.pundit_id}`}
                    style={{
                        display: "inline-block",
                        fontSize: 12,
                        fontWeight: 700,
                        letterSpacing: "0.5px",
                        textTransform: "uppercase",
                        padding: "6px 14px",
                        border: `1px solid ${DS.navy}`,
                        color: DS.navy,
                        textDecoration: "none",
                    }}
                >
                    View Ledger →
                </Link>
                <button
                    onClick={() => onUnfollow(pundit.pundit_id)}
                    disabled={isUnfollowing}
                    style={{
                        fontSize: 11,
                        fontWeight: 600,
                        letterSpacing: "0.5px",
                        textTransform: "uppercase",
                        padding: "5px 12px",
                        border: `1px solid ${DS.border}`,
                        background: "none",
                        color: DS.textLt,
                        cursor: isUnfollowing ? "wait" : "pointer",
                        opacity: isUnfollowing ? 0.5 : 1,
                    }}
                >
                    Unfollow
                </button>
            </div>
        </div>
    );
}

export function MyPunditsClient({ pundits: initialPundits, followedIds }: Props) {
    const [pundits, setPundits] = useState(initialPundits);
    const [unfollowingId, setUnfollowingId] = useState<string | null>(null);
    const [, startTransition] = useTransition();

    function handleUnfollow(punditId: string) {
        setUnfollowingId(punditId);
        // Optimistic removal
        setPundits((prev) => prev.filter((p) => p.pundit_id !== punditId));

        startTransition(async () => {
            const result = await unfollowPundit(punditId);
            if (!result.success) {
                // Revert on error — restore the pundit
                const restored = initialPundits.find((p) => p.pundit_id === punditId);
                if (restored) {
                    setPundits((prev) => {
                        // Re-insert in original position
                        const idx = initialPundits.findIndex((p) => p.pundit_id === punditId);
                        const next = [...prev];
                        next.splice(idx, 0, restored);
                        return next;
                    });
                }
            }
            setUnfollowingId(null);
        });
    }

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
                <span>My Pundits</span>
            </div>

            {/* Header */}
            <div style={{ background: DS.navy, color: "#fff", padding: "32px 40px" }}>
                <div style={{ maxWidth: 900, margin: "0 auto" }}>
                    <h1
                        style={{
                            fontFamily: "var(--font-serif), Georgia, serif",
                            fontSize: 30,
                            fontWeight: 900,
                            margin: "0 0 6px",
                        }}
                    >
                        My Pundits
                    </h1>
                    <p style={{ margin: 0, fontSize: 14, color: "rgba(255,255,255,0.55)" }}>
                        {pundits.length > 0
                            ? `Following ${pundits.length} pundit${pundits.length === 1 ? "" : "s"} — you'll receive email alerts when their predictions resolve.`
                            : "Start following pundits to get resolution alerts and weekly digests."}
                    </p>
                </div>
            </div>

            {/* Content */}
            <div style={{ maxWidth: 900, margin: "0 auto", padding: "32px 40px" }}>
                {pundits.length === 0 ? (
                    /* Empty state */
                    <div
                        style={{
                            background: DS.card,
                            border: `1px solid ${DS.border}`,
                            padding: "56px 40px",
                            textAlign: "center",
                        }}
                    >
                        <div
                            style={{
                                fontSize: 40,
                                marginBottom: 16,
                                color: DS.gold,
                            }}
                        >
                            ☆
                        </div>
                        <p
                            style={{
                                fontSize: 16,
                                color: DS.textMd,
                                margin: "0 0 24px",
                            }}
                        >
                            You{"'"}re not following any pundits yet.
                        </p>
                        <Link
                            href="/ledger"
                            style={{
                                display: "inline-block",
                                padding: "10px 24px",
                                background: DS.navy,
                                color: "#fff",
                                textDecoration: "none",
                                fontSize: 14,
                                fontWeight: 700,
                                letterSpacing: "0.5px",
                            }}
                        >
                            Browse the Pundit Ledger →
                        </Link>
                    </div>
                ) : (
                    <>
                        {/* Notification preferences note */}
                        <div
                            style={{
                                background: `rgba(26,39,68,0.05)`,
                                border: `1px solid rgba(26,39,68,0.12)`,
                                borderLeft: `3px solid ${DS.gold}`,
                                padding: "12px 16px",
                                fontSize: 13,
                                color: DS.textMd,
                                marginBottom: 24,
                                lineHeight: 1.5,
                            }}
                        >
                            <strong style={{ color: DS.navy }}>Email alerts are on.</strong>{" "}
                            You{"'"}ll receive a bundled email each morning when a followed pundit{"'"}s prediction resolves,
                            plus a weekly digest every Tuesday. To unsubscribe from digests, use the link in the email footer.
                        </div>

                        {/* Pundit list */}
                        {pundits.map((pundit) => (
                            <PunditCard
                                key={pundit.pundit_id}
                                pundit={pundit}
                                onUnfollow={handleUnfollow}
                                isUnfollowing={unfollowingId === pundit.pundit_id}
                            />
                        ))}

                        {/* Footer link */}
                        <div
                            style={{
                                textAlign: "center",
                                marginTop: 32,
                                paddingTop: 24,
                                borderTop: `1px solid ${DS.border}`,
                            }}
                        >
                            <Link
                                href="/ledger"
                                style={{
                                    fontSize: 13,
                                    color: DS.gold,
                                    textDecoration: "none",
                                    fontWeight: 600,
                                }}
                            >
                                Discover more pundits in the Ledger →
                            </Link>
                        </div>
                    </>
                )}
            </div>
        </div>
    );
}
