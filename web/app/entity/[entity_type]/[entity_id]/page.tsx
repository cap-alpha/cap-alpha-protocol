"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
    CheckCircle2,
    XCircle,
    Clock,
    ArrowLeft,
    Activity,
    ExternalLink,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { SectionHeading } from "@/components/ui/heading";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface EntityData {
    entity_id: string;
    entity_type: string;
    entity_name: string;
    entity_subtype?: string | null;
    context?: string | null;        // e.g. "Kansas City Chiefs · AFC West · NFL"
    tags?: string[];
    total_claims: number;
    correct_claims: number;
    incorrect_claims: number;
    pending_claims: number;
}

interface PunditAccuracyRow {
    pundit_id: string;
    pundit_name: string;
    outlet?: string | null;
    claims: number;
    correct: number;
    accuracy_pct: number | null;
    brier_score: number | null;
    verdict: "Expert" | "Reliable" | "Average" | "Avoid" | null;
}

interface ClaimItem {
    claim_id: string;
    pundit_id: string;
    pundit_name: string;
    outlet?: string | null;
    claim_text: string;
    claim_date?: string | null;
    claim_context?: string | null;     // e.g. "Pre-Super Bowl LVIII"
    resolution_status: "CORRECT" | "INCORRECT" | "PENDING" | null;
    confidence?: number | null;
    hash_short?: string | null;
}

interface RelatedEntity {
    entity_id: string;
    entity_type: string;
    entity_name: string;
    entity_subtype?: string | null;
    co_mention_count: number;
    initials?: string;
}

interface TimelineEvent {
    date_str: string;
    pundit_name: string;
    summary: string;
    status: "correct" | "incorrect" | "pending";
}

// ---------------------------------------------------------------------------
// Entity type config
// ---------------------------------------------------------------------------

const ENTITY_TYPE_LABELS: Record<string, string> = {
    player: "Player",
    team: "Team",
    game: "Game",
    award: "Award",
    coach: "Coach",
    event: "Event",
    pundit: "Pundit",
};

// ---------------------------------------------------------------------------
// Mock data builders — used until API supports per-entity breakdown
// TODO: Replace with real API calls once /v1/entities endpoint is implemented (#816)
// ---------------------------------------------------------------------------

function buildMockEntity(entityType: string, entityId: string): EntityData {
    const typeLabel = ENTITY_TYPE_LABELS[entityType] ?? entityType;
    const name = entityId
        .split("-")
        .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
        .join(" ");
    return {
        entity_id: entityId,
        entity_type: entityType,
        entity_name: name,
        entity_subtype: typeLabel === "Player" ? "Quarterback" : undefined,
        context: `${typeLabel} entity`,
        tags: ["NFL"],
        total_claims: 0,
        correct_claims: 0,
        incorrect_claims: 0,
        pending_claims: 0,
    };
}

const MOCK_PUNDIT_ROWS: PunditAccuracyRow[] = [
    // TODO: Replace with real API data from /v1/entities/{entity_id}/pundit-accuracy
    {
        pundit_id: "adam-schefter",
        pundit_name: "Adam Schefter",
        outlet: "ESPN",
        claims: 41,
        correct: 34,
        accuracy_pct: 82.9,
        brier_score: 0.161,
        verdict: "Expert",
    },
    {
        pundit_id: "shannon-sharpe",
        pundit_name: "Shannon Sharpe",
        outlet: "FS1",
        claims: 29,
        correct: 22,
        accuracy_pct: 75.9,
        brier_score: 0.209,
        verdict: "Reliable",
    },
    {
        pundit_id: "colin-cowherd",
        pundit_name: "Colin Cowherd",
        outlet: "FS1",
        claims: 67,
        correct: 40,
        accuracy_pct: 59.7,
        brier_score: 0.321,
        verdict: "Average",
    },
    {
        pundit_id: "skip-bayless",
        pundit_name: "Skip Bayless",
        outlet: "FS1",
        claims: 89,
        correct: 39,
        accuracy_pct: 43.8,
        brier_score: 0.451,
        verdict: "Avoid",
    },
    {
        pundit_id: "peter-king",
        pundit_name: "Peter King",
        outlet: "NBC Sports",
        claims: 22,
        correct: 16,
        accuracy_pct: 72.7,
        brier_score: 0.231,
        verdict: "Reliable",
    },
];

const MOCK_CLAIMS: ClaimItem[] = [
    // TODO: Replace with real API data from /v1/entities/{entity_id}/claims
    {
        claim_id: "mock-1",
        pundit_id: "adam-schefter",
        pundit_name: "Adam Schefter",
        outlet: "ESPN",
        claim_text:
            "This entity will perform at the highest level this season. The metrics support a dominant year ahead.",
        claim_date: "Jan 12, 2024",
        claim_context: "Pre-Season",
        resolution_status: "CORRECT",
        confidence: 0.84,
        hash_short: "a3f9…7d21",
    },
    {
        claim_id: "mock-2",
        pundit_id: "shannon-sharpe",
        pundit_name: "Shannon Sharpe",
        outlet: "FS1",
        claim_text:
            "I'm going on record: this is going to be a defining moment. Mark my words.",
        claim_date: "Oct 3, 2023",
        claim_context: "Week 5",
        resolution_status: "CORRECT",
        confidence: 0.78,
        hash_short: "c8d2…a119",
    },
    {
        claim_id: "mock-3",
        pundit_id: "skip-bayless",
        pundit_name: "Skip Bayless",
        outlet: "FS1",
        claim_text:
            "The numbers don't lie — this is going to end badly. There's no way this works out.",
        claim_date: "Jan 29, 2024",
        claim_context: "Playoff Season",
        resolution_status: "INCORRECT",
        confidence: 0.85,
        hash_short: "e7f1…b432",
    },
    {
        claim_id: "mock-4",
        pundit_id: "colin-cowherd",
        pundit_name: "Colin Cowherd",
        outlet: "FS1",
        claim_text:
            "This is a dynasty situation. We're going to be talking about this for years to come. I'll bet my career on it.",
        claim_date: "Mar 20, 2025",
        claim_context: null,
        resolution_status: "PENDING",
        confidence: 0.72,
        hash_short: "d4a8…f209",
    },
];

const MOCK_RELATED: RelatedEntity[] = [
    // TODO: Replace with real co-mention data from /v1/entities/{entity_id}/related
    {
        entity_id: "kansas-city-chiefs",
        entity_type: "team",
        entity_name: "Kansas City Chiefs",
        entity_subtype: "AFC West",
        co_mention_count: 1247,
        initials: "KC",
    },
    {
        entity_id: "super-bowl-lviii",
        entity_type: "event",
        entity_name: "Super Bowl LVIII",
        entity_subtype: "Feb 2024",
        co_mention_count: 892,
        initials: "SB",
    },
    {
        entity_id: "travis-kelce",
        entity_type: "player",
        entity_name: "Travis Kelce",
        entity_subtype: "TE",
        co_mention_count: 218,
        initials: "TK",
    },
    {
        entity_id: "andy-reid",
        entity_type: "coach",
        entity_name: "Andy Reid",
        entity_subtype: "Head Coach",
        co_mention_count: 143,
        initials: "AR",
    },
    {
        entity_id: "nfl-mvp",
        entity_type: "award",
        entity_name: "NFL MVP Award",
        entity_subtype: "Annual",
        co_mention_count: 187,
        initials: "MVP",
    },
];

const MOCK_TIMELINE: TimelineEvent[] = [
    // TODO: Replace with real timeline from /v1/entities/{entity_id}/activity
    {
        date_str: "May 2\n2025",
        pundit_name: "Peter King",
        summary: "predicted a major development in 2025 — pending",
        status: "pending",
    },
    {
        date_str: "Mar 20\n2025",
        pundit_name: "Colin Cowherd",
        summary: "made a long-range dynasty prediction — pending",
        status: "pending",
    },
    {
        date_str: "Feb 12\n2024",
        pundit_name: "Adam Schefter",
        summary: "championship prediction — correct",
        status: "correct",
    },
    {
        date_str: "Jan 29\n2024",
        pundit_name: "Skip Bayless",
        summary: "predicted a major upset — incorrect",
        status: "incorrect",
    },
];

// ---------------------------------------------------------------------------
// Helper: verdicts, colors
// ---------------------------------------------------------------------------

type VerdictKind = "Expert" | "Reliable" | "Average" | "Avoid";

const VERDICT_STYLE: Record<VerdictKind, string> = {
    Expert:
        "bg-correct/10 text-correct border border-correct/30",
    Reliable:
        "bg-correct/5 text-correct border border-correct/20",
    Average:
        "bg-pending/10 text-pending border border-pending/30",
    Avoid:
        "bg-incorrect/10 text-incorrect border border-incorrect/30",
};

function verdictStyle(verdict: string | null): string {
    if (!verdict) return "bg-editorial-border text-ink-2 border border-editorial-border";
    return VERDICT_STYLE[verdict as VerdictKind] ?? "bg-editorial-border text-ink-2 border border-editorial-border";
}

function getAccuracyClass(pct: number | null): string {
    if (pct === null) return "text-ink-3";
    if (pct >= 70) return "text-correct";
    if (pct >= 55) return "text-pending";
    return "text-incorrect";
}

function getBrierClass(score: number | null): string {
    if (score === null) return "text-ink-3";
    if (score <= 0.2) return "text-correct";
    if (score <= 0.35) return "text-pending";
    return "text-incorrect";
}

function fmtDate(ts: string | null | undefined): string | null {
    if (!ts) return null;
    try {
        return new Date(ts).toLocaleDateString("en-US", {
            month: "short",
            day: "numeric",
            year: "numeric",
        });
    } catch {
        return null;
    }
}

function getInitials(name: string): string {
    return name
        .split(/\s+/)
        .map((w) => w.charAt(0).toUpperCase())
        .join("")
        .slice(0, 3);
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function ClaimStatusBadge({ status }: { status: "CORRECT" | "INCORRECT" | "PENDING" | null }) {
    if (status === "CORRECT")
        return (
            <span className="inline-flex items-center gap-1 rounded-full bg-correct/10 px-2.5 py-1 text-[11px] font-semibold text-correct ring-1 ring-correct/30 shrink-0">
                <CheckCircle2 className="w-3 h-3" /> Correct
            </span>
        );
    if (status === "INCORRECT")
        return (
            <span className="inline-flex items-center gap-1 rounded-full bg-incorrect/10 px-2.5 py-1 text-[11px] font-semibold text-incorrect ring-1 ring-incorrect/30 shrink-0">
                <XCircle className="w-3 h-3" /> Incorrect
            </span>
        );
    return (
        <span className="inline-flex items-center gap-1 rounded-full bg-pending/10 px-2.5 py-1 text-[11px] font-semibold text-pending ring-1 ring-pending/30 shrink-0">
            <Clock className="w-3 h-3" /> Pending
        </span>
    );
}

function ConfBar({ confidence, status }: { confidence: number | null; status: "CORRECT" | "INCORRECT" | "PENDING" | null }) {
    if (confidence === null) return null;
    const pct = Math.round(confidence * 100);
    const fillClass =
        status === "CORRECT"
            ? "bg-correct"
            : status === "INCORRECT"
            ? "bg-incorrect"
            : "bg-pending";
    return (
        <div className="flex items-center gap-2 text-[11px] text-ink-3 font-mono">
            <span>Conf:</span>
            <div className="w-12 h-1 bg-editorial-border rounded-full overflow-hidden">
                <div
                    className={cn("h-full rounded-full", fillClass)}
                    style={{ width: `${pct}%` }}
                />
            </div>
            <span>{confidence.toFixed(2)}</span>
        </div>
    );
}

function EntityTypeBrowser() {
    const types = [
        { type: "player", label: "Players", icon: "P" },
        { type: "team", label: "Teams", icon: "T" },
        { type: "game", label: "Games", icon: "G" },
        { type: "award", label: "Awards", icon: "A" },
        { type: "coach", label: "Coaches", icon: "C" },
        { type: "event", label: "Events", icon: "E" },
    ];
    return (
        <div className="grid grid-cols-2 gap-2">
            {types.map(({ type, label, icon }) => (
                <Link
                    key={type}
                    href={`/entity/${type}`}
                    className="flex items-center gap-2 bg-editorial-card border border-editorial-border hover:border-ink-3 px-3 py-2.5 text-sm font-semibold text-ink-2 hover:text-ink transition-colors rounded"
                >
                    <span className="text-[10px] font-mono font-bold text-ink-3 w-4 text-center">
                        {icon}
                    </span>
                    {label}
                </Link>
            ))}
        </div>
    );
}

// ---------------------------------------------------------------------------
// Tab state
// ---------------------------------------------------------------------------

type TabId = "all" | "by-pundit" | "claim-timeline";

const TABS: { id: TabId; label: string }[] = [
    { id: "all", label: "All Claims" },
    { id: "by-pundit", label: "By Pundit" },
    { id: "claim-timeline", label: "Claim Timeline" },
];

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function EntityDetailPage() {
    const params = useParams<{ entity_type: string; entity_id: string }>();
    const entityType = params.entity_type ?? "player";
    const entityId = params.entity_id ?? "unknown";

    const [entity, setEntity] = useState<EntityData | null>(null);
    const [punditsRows, setPunditsRows] = useState<PunditAccuracyRow[]>([]);
    const [claims, setClaims] = useState<ClaimItem[]>([]);
    const [relatedEntities, setRelatedEntities] = useState<RelatedEntity[]>([]);
    const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
    const [loading, setLoading] = useState(true);
    const [activeTab, setActiveTab] = useState<TabId>("all");
    const [claimsShown, setClaimsShown] = useState(4);

    useEffect(() => {
        setLoading(true);

        const enc = encodeURIComponent(entityId);

        Promise.all([
            fetch(`/api/entities/${enc}`)
                .then((r) => (r.ok ? r.json() : null))
                .catch(() => null),
            fetch(`/api/entities/${enc}/claims?page_size=100`)
                .then((r) => (r.ok ? r.json() : null))
                .catch(() => null),
            fetch(`/api/entities/${enc}/pundit-accuracy`)
                .then((r) => (r.ok ? r.json() : null))
                .catch(() => null),
            fetch(`/api/entities/${enc}/related`)
                .then((r) => (r.ok ? r.json() : null))
                .catch(() => null),
        ])
            .then(([entityData, claimsData, punditAccData, relatedData]) => {
                // Entity — fall back to a minimal stub built from URL params if API not yet deployed
                if (entityData && entityData.entity_id) {
                    setEntity(entityData as EntityData);
                } else {
                    setEntity(buildMockEntity(entityType, entityId));
                }

                // Claims
                const rawClaims: ClaimItem[] = (claimsData?.claims ?? []) as ClaimItem[];
                setClaims(rawClaims.length > 0 ? rawClaims : MOCK_CLAIMS);

                // Pundit accuracy rows
                const rawRows: PunditAccuracyRow[] = (punditAccData?.rows ?? []) as PunditAccuracyRow[];
                setPunditsRows(rawRows.length > 0 ? rawRows : MOCK_PUNDIT_ROWS);

                // Related entities
                const rawRelated: RelatedEntity[] = (relatedData?.entities ?? []) as RelatedEntity[];
                setRelatedEntities(rawRelated.length > 0 ? rawRelated : MOCK_RELATED);

                // Timeline is derived from claims for now (no dedicated /activity endpoint yet)
                setTimeline(MOCK_TIMELINE);
            })
            .catch(() => {
                setEntity(buildMockEntity(entityType, entityId));
                setClaims(MOCK_CLAIMS);
                setPunditsRows(MOCK_PUNDIT_ROWS);
                setRelatedEntities(MOCK_RELATED);
                setTimeline(MOCK_TIMELINE);
            })
            .finally(() => setLoading(false));
    }, [entityType, entityId]); // eslint-disable-line react-hooks/exhaustive-deps

    const entityTypeLabel = ENTITY_TYPE_LABELS[entityType] ?? entityType;

    if (loading || !entity) {
        return (
            <div className="min-h-screen bg-editorial-bg text-ink flex items-center justify-center">
                <Activity className="w-4 h-4 animate-pulse mr-2 text-accent-editorial" />
                <span className="font-mono text-sm text-ink-2">Loading entity…</span>
            </div>
        );
    }

    const visibleClaims = claims.slice(0, claimsShown);
    const entityInitials = getInitials(entity.entity_name);

    return (
        <div className="min-h-screen bg-editorial-bg text-ink">
            {/* Breadcrumb */}
            <div className="border-b border-editorial-border bg-editorial-card px-6 py-2">
                <div className="max-w-6xl mx-auto flex items-center gap-2 text-xs text-ink-3 font-mono">
                    <Link href="/ledger" className="hover:text-accent-editorial transition-colors inline-flex items-center gap-1">
                        <ArrowLeft className="w-3 h-3" /> Leaderboard
                    </Link>
                    <span className="text-ink-3">›</span>
                    <Link href={`/entity/${entityType}`} className="hover:text-accent-editorial transition-colors capitalize">
                        {entityTypeLabel}s
                    </Link>
                    <span className="text-ink-3">›</span>
                    <span className="text-ink-2">{entity.entity_name}</span>
                </div>
            </div>

            {/* Entity Header */}
            <div className="border-b border-editorial-border bg-editorial-card">
                <div className="max-w-6xl mx-auto px-6 py-8">
                    <div className="flex flex-col sm:flex-row items-start gap-6">
                        {/* Avatar */}
                        <div className="w-20 h-20 rounded-lg bg-editorial-bg border border-editorial-border flex items-center justify-center shrink-0">
                            <span className="font-black text-2xl text-accent-editorial font-mono">
                                {entityInitials}
                            </span>
                        </div>

                        {/* Name + meta */}
                        <div className="flex-1 min-w-0">
                            {/* Type badge */}
                            <div className="text-[10px] font-bold tracking-[2px] uppercase text-gold mb-1">
                                {entityTypeLabel}
                                {entity.entity_subtype ? ` · ${entity.entity_subtype}` : ""}
                            </div>
                            <SectionHeading size="xl" className="text-ink mb-2">
                                {entity.entity_name}
                            </SectionHeading>
                            {entity.context && (
                                <div className="text-sm text-ink-2 mb-3">{entity.context}</div>
                            )}
                            {/* Tags */}
                            {entity.tags && entity.tags.length > 0 && (
                                <div className="flex flex-wrap gap-2">
                                    {entity.tags.map((tag) => (
                                        <span
                                            key={tag}
                                            className="bg-editorial-bg border border-editorial-border text-ink-2 text-[11px] font-semibold px-2.5 py-1 uppercase tracking-wide"
                                        >
                                            {tag}
                                        </span>
                                    ))}
                                </div>
                            )}
                        </div>

                        {/* Claim summary boxes */}
                        <div className="flex divide-x divide-editorial-border border border-editorial-border bg-editorial-bg shrink-0">
                            <div className="text-center px-6 py-4">
                                <div className="text-3xl font-black font-mono text-ink tabular-nums">
                                    {entity.total_claims}
                                </div>
                                <div className="text-[10px] uppercase tracking-widest text-ink-3 mt-1">
                                    Total Claims
                                </div>
                            </div>
                            <div className="text-center px-6 py-4">
                                <div className="text-3xl font-black font-mono text-correct tabular-nums">
                                    {entity.correct_claims}
                                </div>
                                <div className="text-[10px] uppercase tracking-widest text-ink-3 mt-1">
                                    Correct
                                </div>
                            </div>
                            <div className="text-center px-6 py-4">
                                <div className="text-3xl font-black font-mono text-incorrect tabular-nums">
                                    {entity.incorrect_claims}
                                </div>
                                <div className="text-[10px] uppercase tracking-widest text-ink-3 mt-1">
                                    Wrong
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            {/* Tabs */}
            <div className="border-b border-editorial-border bg-editorial-card">
                <div className="max-w-6xl mx-auto px-6">
                    <div className="flex gap-0">
                        {TABS.map(({ id, label }) => (
                            <button
                                key={id}
                                onClick={() => setActiveTab(id)}
                                className={cn(
                                    "px-5 py-3 text-sm font-semibold uppercase tracking-wide transition-colors border-b-2",
                                    activeTab === id
                                        ? "border-accent-editorial text-accent-editorial"
                                        : "border-transparent text-ink-3 hover:text-ink"
                                )}
                            >
                                {label}
                                {id === "all" && entity.total_claims > 0
                                    ? ` (${entity.total_claims})`
                                    : ""}
                            </button>
                        ))}
                    </div>
                </div>
            </div>

            {/* Two-column content */}
            <div className="max-w-6xl mx-auto px-6 py-8 grid grid-cols-1 lg:grid-cols-[1fr_300px] gap-8">
                {/* Main column */}
                <div>
                    {/* Pundit accuracy table — always shown regardless of tab */}
                    <div className="mb-8">
                        <div className="border-t-2 border-ink pt-3 flex items-baseline justify-between mb-4">
                            <h2 className="text-xl font-black text-ink">
                                Pundit Accuracy on {entity.entity_name}
                            </h2>
                            <Link
                                href="/ledger"
                                className="text-[11px] font-bold uppercase tracking-wide text-accent-editorial hover:text-accent-editorial-light transition-colors"
                            >
                                All pundits →
                            </Link>
                        </div>
                        <div className="overflow-x-auto">
                            <table className="w-full border-collapse">
                                <thead>
                                    <tr className="border-b border-editorial-border">
                                        {["Pundit", "Claims", "Correct", "Accuracy", "Brier", "Verdict"].map(
                                            (col, i) => (
                                                <th
                                                    key={col}
                                                    className={cn(
                                                        "text-[10px] font-bold uppercase tracking-widest text-ink-3 py-2 px-3",
                                                        i === 0 ? "text-left" : "text-right"
                                                    )}
                                                >
                                                    {col}
                                                </th>
                                            )
                                        )}
                                    </tr>
                                </thead>
                                <tbody>
                                    {punditsRows.map((row) => (
                                        <tr
                                            key={row.pundit_id}
                                            className="border-b border-editorial-border hover:bg-editorial-card transition-colors"
                                        >
                                            <td className="py-3 px-3">
                                                <Link
                                                    href={`/ledger/${encodeURIComponent(row.pundit_id)}`}
                                                    className="font-black text-ink hover:text-accent-editorial transition-colors text-sm"
                                                >
                                                    {row.pundit_name}
                                                </Link>
                                                {row.outlet && (
                                                    <div className="text-[11px] text-ink-3 mt-0.5">
                                                        {row.outlet}
                                                    </div>
                                                )}
                                            </td>
                                            <td className="py-3 px-3 text-right font-mono text-sm text-ink-2 tabular-nums">
                                                {row.claims}
                                            </td>
                                            <td className={cn("py-3 px-3 text-right font-mono text-sm font-bold tabular-nums", getAccuracyClass(row.accuracy_pct))}>
                                                {row.correct}
                                            </td>
                                            <td className={cn("py-3 px-3 text-right font-mono text-sm font-bold tabular-nums", getAccuracyClass(row.accuracy_pct))}>
                                                {row.accuracy_pct !== null ? `${row.accuracy_pct}%` : "—"}
                                            </td>
                                            <td className={cn("py-3 px-3 text-right font-mono text-sm font-bold tabular-nums", getBrierClass(row.brier_score))}>
                                                {row.brier_score !== null ? row.brier_score.toFixed(3) : "—"}
                                            </td>
                                            <td className="py-3 px-3 text-right">
                                                {row.verdict && (
                                                    <span
                                                        className={cn(
                                                            "inline-block text-[10px] font-bold uppercase tracking-wide px-2 py-1 rounded",
                                                            verdictStyle(row.verdict)
                                                        )}
                                                    >
                                                        {row.verdict}
                                                    </span>
                                                )}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>

                    {/* Claims feed */}
                    {activeTab !== "claim-timeline" && (
                        <div>
                            <div className="border-t-2 border-ink pt-3 flex items-baseline justify-between mb-4">
                                <h2 className="text-xl font-black text-ink">
                                    {activeTab === "by-pundit"
                                        ? `Claims by Pundit`
                                        : `All Claims about ${entity.entity_name}`}
                                </h2>
                            </div>

                            {claims.length === 0 && (
                                <div className="rounded-xl border border-editorial-border bg-editorial-card py-12 text-center text-ink-3 text-sm">
                                    No claims found for this entity yet.
                                </div>
                            )}

                            <div className="space-y-3">
                                {visibleClaims.map((claim) => (
                                    <ClaimCard key={claim.claim_id} claim={claim} />
                                ))}
                            </div>

                            {claims.length > claimsShown && (
                                <div className="text-center mt-6">
                                    <button
                                        onClick={() => setClaimsShown((n) => n + 10)}
                                        className="text-sm font-semibold text-accent-editorial hover:text-accent-editorial-light transition-colors font-mono"
                                    >
                                        Load more →
                                    </button>
                                    <span className="text-xs text-ink-3 ml-3 font-mono">
                                        Showing {claimsShown} of {claims.length}
                                    </span>
                                </div>
                            )}
                        </div>
                    )}

                    {/* Claim Timeline tab */}
                    {activeTab === "claim-timeline" && (
                        <div>
                            <div className="border-t-2 border-ink pt-3 mb-4">
                                <h2 className="text-xl font-black text-ink">Claim Timeline</h2>
                            </div>
                            <div className="space-y-0">
                                {timeline.map((evt, i) => (
                                    <div
                                        key={i}
                                        className="grid grid-cols-[80px_1fr] gap-4 py-4 border-b border-editorial-border last:border-b-0"
                                    >
                                        <div className="font-mono text-[11px] text-ink-3 leading-5 whitespace-pre-line">
                                            {evt.date_str}
                                        </div>
                                        <div className="text-sm text-ink-2 leading-5">
                                            <span className="font-bold text-ink">{evt.pundit_name}</span>{" "}
                                            {evt.summary.replace(/ — (correct|incorrect|pending)$/, "")}
                                            {" — "}
                                            <span
                                                className={cn(
                                                    "font-semibold",
                                                    evt.status === "correct"
                                                        ? "text-correct"
                                                        : evt.status === "incorrect"
                                                        ? "text-incorrect"
                                                        : "text-pending"
                                                )}
                                            >
                                                {evt.status}
                                            </span>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>

                {/* Sidebar */}
                <div className="space-y-5">
                    {/* Related entities */}
                    <div className="bg-editorial-card border border-editorial-border p-5 rounded">
                        <div className="text-[11px] font-bold uppercase tracking-[2px] text-gold border-b border-editorial-border pb-3 mb-4">
                            Related Entities
                        </div>
                        <div className="space-y-0 divide-y divide-editorial-border">
                            {relatedEntities.map((rel) => (
                                <Link
                                    key={rel.entity_id}
                                    href={`/entity/${rel.entity_type}/${encodeURIComponent(rel.entity_id)}`}
                                    className="flex items-center justify-between py-3 group"
                                >
                                    <div className="flex items-center gap-3">
                                        <div className="w-8 h-8 rounded bg-editorial-bg border border-editorial-border flex items-center justify-center text-[10px] font-bold text-ink-2 shrink-0">
                                            {rel.initials ?? getInitials(rel.entity_name)}
                                        </div>
                                        <div>
                                            <div className="text-sm font-semibold text-ink group-hover:text-accent-editorial transition-colors">
                                                {rel.entity_name}
                                            </div>
                                            {rel.entity_subtype && (
                                                <div className="text-[11px] text-ink-3 capitalize">
                                                    {ENTITY_TYPE_LABELS[rel.entity_type] ?? rel.entity_type} · {rel.entity_subtype}
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                    <div className="font-mono text-[11px] text-ink-3 tabular-nums">
                                        {rel.co_mention_count.toLocaleString()} claims
                                    </div>
                                </Link>
                            ))}
                        </div>
                    </div>

                    {/* Recent activity timeline */}
                    <div className="bg-editorial-card border border-editorial-border p-5 rounded">
                        <div className="text-[11px] font-bold uppercase tracking-[2px] text-gold border-b border-editorial-border pb-3 mb-4">
                            Recent Activity
                        </div>
                        <div className="space-y-0 divide-y divide-editorial-border">
                            {timeline.map((evt, i) => (
                                <div key={i} className="grid grid-cols-[56px_1fr] gap-3 py-3">
                                    <div className="font-mono text-[10px] text-ink-3 leading-4 whitespace-pre-line">
                                        {evt.date_str}
                                    </div>
                                    <div className="text-xs text-ink-2 leading-4">
                                        <span className="font-bold text-ink">{evt.pundit_name}</span>{" "}
                                        {evt.summary.replace(/ — (correct|incorrect|pending)$/, "")}
                                        {" — "}
                                        <span
                                            className={cn(
                                                "font-semibold",
                                                evt.status === "correct"
                                                    ? "text-correct"
                                                    : evt.status === "incorrect"
                                                    ? "text-incorrect"
                                                    : "text-pending"
                                            )}
                                        >
                                            {evt.status}
                                        </span>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>

                    {/* Entity type browser */}
                    <div className="bg-editorial-card border border-editorial-border p-5 rounded">
                        <div className="text-[11px] font-bold uppercase tracking-[2px] text-gold border-b border-editorial-border pb-3 mb-4">
                            Browse by Type
                        </div>
                        <EntityTypeBrowser />
                    </div>
                </div>
            </div>
        </div>
    );
}

// ---------------------------------------------------------------------------
// Claim card sub-component
// ---------------------------------------------------------------------------

function ClaimCard({ claim }: { claim: ClaimItem }) {
    const borderColor =
        claim.resolution_status === "CORRECT"
            ? "border-l-correct"
            : claim.resolution_status === "INCORRECT"
            ? "border-l-incorrect"
            : "border-l-pending";

    return (
        <div
            className={cn(
                "bg-editorial-card border border-editorial-border border-l-4 p-5 relative",
                borderColor
            )}
        >
            {/* Top row: pundit + status */}
            <div className="flex items-start justify-between gap-3 mb-2">
                <div>
                    <Link
                        href={`/ledger/${encodeURIComponent(claim.pundit_id)}`}
                        className="font-black text-sm text-ink hover:text-accent-editorial transition-colors"
                    >
                        {claim.pundit_name}
                    </Link>
                    {claim.outlet && (
                        <span className="text-ink-3 text-sm"> · {claim.outlet}</span>
                    )}
                    <div className="text-[11px] text-ink-3 font-mono mt-0.5">
                        {claim.claim_date ?? ""}
                        {claim.claim_context ? ` · ${claim.claim_context}` : ""}
                    </div>
                </div>
                <ClaimStatusBadge status={claim.resolution_status} />
            </div>

            {/* Quote */}
            <p className="text-base italic text-ink-2 leading-relaxed mb-3 font-serif">
                &ldquo;{claim.claim_text}&rdquo;
            </p>

            {/* Bottom row: confidence + hash */}
            <div className="flex items-center justify-between">
                <ConfBar confidence={claim.confidence ?? null} status={claim.resolution_status} />
                {claim.hash_short && (
                    <span className="font-mono text-[9px] text-ink-3">
                        {claim.hash_short}
                    </span>
                )}
            </div>
        </div>
    );
}
