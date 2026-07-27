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
        "bg-emerald-900/20 text-emerald-400 border border-emerald-500/30",
    Reliable:
        "bg-emerald-900/10 text-emerald-400 border border-emerald-500/20",
    Average:
        "bg-amber-900/20 text-amber-400 border border-amber-500/30",
    Avoid:
        "bg-red-900/20 text-red-400 border border-red-500/30",
};

function verdictStyle(verdict: string | null): string {
    if (!verdict) return "bg-zinc-800 text-zinc-400 border border-zinc-700";
    return VERDICT_STYLE[verdict as VerdictKind] ?? "bg-zinc-800 text-zinc-400 border border-zinc-700";
}

function getAccuracyClass(pct: number | null): string {
    if (pct === null) return "text-zinc-500";
    if (pct >= 70) return "text-emerald-400";
    if (pct >= 55) return "text-amber-400";
    return "text-red-400";
}

function getBrierClass(score: number | null): string {
    if (score === null) return "text-zinc-500";
    if (score <= 0.2) return "text-emerald-400";
    if (score <= 0.35) return "text-amber-400";
    return "text-red-400";
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
            <span className="inline-flex items-center gap-1 rounded-full bg-emerald-900/40 px-2.5 py-1 text-[11px] font-semibold text-emerald-400 ring-1 ring-emerald-500/30 shrink-0">
                <CheckCircle2 className="w-3 h-3" /> Correct
            </span>
        );
    if (status === "INCORRECT")
        return (
            <span className="inline-flex items-center gap-1 rounded-full bg-red-900/40 px-2.5 py-1 text-[11px] font-semibold text-red-400 ring-1 ring-red-500/30 shrink-0">
                <XCircle className="w-3 h-3" /> Incorrect
            </span>
        );
    return (
        <span className="inline-flex items-center gap-1 rounded-full bg-amber-900/30 px-2.5 py-1 text-[11px] font-semibold text-amber-400 ring-1 ring-amber-500/30 shrink-0">
            <Clock className="w-3 h-3" /> Pending
        </span>
    );
}

function ConfBar({ confidence, status }: { confidence: number | null; status: "CORRECT" | "INCORRECT" | "PENDING" | null }) {
    if (confidence === null) return null;
    const pct = Math.round(confidence * 100);
    const fillClass =
        status === "CORRECT"
            ? "bg-emerald-500"
            : status === "INCORRECT"
            ? "bg-red-500"
            : "bg-amber-500";
    return (
        <div className="flex items-center gap-2 text-[11px] text-zinc-500 font-mono">
            <span>Conf:</span>
            <div className="w-12 h-1 bg-zinc-800 rounded-full overflow-hidden">
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
                    className="flex items-center gap-2 bg-zinc-900/60 border border-zinc-800 hover:border-zinc-600 px-3 py-2.5 text-sm font-semibold text-zinc-300 hover:text-white transition-colors rounded"
                >
                    <span className="text-[10px] font-mono font-bold text-zinc-500 w-4 text-center">
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
            <div className="min-h-screen bg-black text-white flex items-center justify-center">
                <Activity className="w-4 h-4 animate-pulse mr-2 text-emerald-400" />
                <span className="font-mono text-sm text-zinc-400">Loading entity…</span>
            </div>
        );
    }

    const visibleClaims = claims.slice(0, claimsShown);
    const entityInitials = getInitials(entity.entity_name);

    return (
        <div className="min-h-screen bg-black text-white">
            {/* Breadcrumb */}
            <div className="border-b border-zinc-900 bg-zinc-950/50 px-6 py-2">
                <div className="max-w-6xl mx-auto flex items-center gap-2 text-xs text-zinc-500 font-mono">
                    <Link href="/ledger" className="hover:text-emerald-400 transition-colors inline-flex items-center gap-1">
                        <ArrowLeft className="w-3 h-3" /> Leaderboard
                    </Link>
                    <span className="text-zinc-700">›</span>
                    <Link href={`/entity/${entityType}`} className="hover:text-emerald-400 transition-colors capitalize">
                        {entityTypeLabel}s
                    </Link>
                    <span className="text-zinc-700">›</span>
                    <span className="text-zinc-300">{entity.entity_name}</span>
                </div>
            </div>

            {/* Entity Header */}
            <div className="border-b border-zinc-900 bg-zinc-950/70">
                <div className="max-w-6xl mx-auto px-6 py-8">
                    <div className="flex flex-col sm:flex-row items-start gap-6">
                        {/* Avatar */}
                        <div className="w-20 h-20 rounded-lg bg-gradient-to-br from-zinc-800 to-zinc-900 border border-zinc-700 flex items-center justify-center shrink-0">
                            <span className="font-black text-2xl text-emerald-400 font-mono">
                                {entityInitials}
                            </span>
                        </div>

                        {/* Name + meta */}
                        <div className="flex-1 min-w-0">
                            {/* Type badge */}
                            <div className="text-[10px] font-bold tracking-[2px] uppercase text-amber-400 mb-1">
                                {entityTypeLabel}
                                {entity.entity_subtype ? ` · ${entity.entity_subtype}` : ""}
                            </div>
                            <h1 className="text-4xl font-black text-white leading-none mb-2 tracking-tight">
                                {entity.entity_name}
                            </h1>
                            {entity.context && (
                                <div className="text-sm text-zinc-400 mb-3">{entity.context}</div>
                            )}
                            {/* Tags */}
                            {entity.tags && entity.tags.length > 0 && (
                                <div className="flex flex-wrap gap-2">
                                    {entity.tags.map((tag) => (
                                        <span
                                            key={tag}
                                            className="bg-zinc-900 border border-zinc-700 text-zinc-300 text-[11px] font-semibold px-2.5 py-1 uppercase tracking-wide"
                                        >
                                            {tag}
                                        </span>
                                    ))}
                                </div>
                            )}
                        </div>

                        {/* Claim summary boxes */}
                        <div className="flex divide-x divide-zinc-800 border border-zinc-800 bg-zinc-950 shrink-0">
                            <div className="text-center px-6 py-4">
                                <div className="text-3xl font-black font-mono text-white tabular-nums">
                                    {entity.total_claims}
                                </div>
                                <div className="text-[10px] uppercase tracking-widest text-zinc-500 mt-1">
                                    Total Claims
                                </div>
                            </div>
                            <div className="text-center px-6 py-4">
                                <div className="text-3xl font-black font-mono text-emerald-400 tabular-nums">
                                    {entity.correct_claims}
                                </div>
                                <div className="text-[10px] uppercase tracking-widest text-zinc-500 mt-1">
                                    Correct
                                </div>
                            </div>
                            <div className="text-center px-6 py-4">
                                <div className="text-3xl font-black font-mono text-red-400 tabular-nums">
                                    {entity.incorrect_claims}
                                </div>
                                <div className="text-[10px] uppercase tracking-widest text-zinc-500 mt-1">
                                    Wrong
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            {/* Tabs */}
            <div className="border-b border-zinc-900 bg-zinc-950/30">
                <div className="max-w-6xl mx-auto px-6">
                    <div className="flex gap-0">
                        {TABS.map(({ id, label }) => (
                            <button
                                key={id}
                                onClick={() => setActiveTab(id)}
                                className={cn(
                                    "px-5 py-3 text-sm font-semibold uppercase tracking-wide transition-colors border-b-2",
                                    activeTab === id
                                        ? "border-amber-500 text-amber-400"
                                        : "border-transparent text-zinc-500 hover:text-zinc-300"
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
                        <div className="border-t-2 border-white pt-3 flex items-baseline justify-between mb-4">
                            <h2 className="text-xl font-black text-white">
                                Pundit Accuracy on {entity.entity_name}
                            </h2>
                            <Link
                                href="/ledger"
                                className="text-[11px] font-bold uppercase tracking-wide text-amber-400 hover:text-amber-300 transition-colors"
                            >
                                All pundits →
                            </Link>
                        </div>
                        <div className="overflow-x-auto">
                            <table className="w-full border-collapse">
                                <thead>
                                    <tr className="border-b border-zinc-800">
                                        {["Pundit", "Claims", "Correct", "Accuracy", "Brier", "Verdict"].map(
                                            (col, i) => (
                                                <th
                                                    key={col}
                                                    className={cn(
                                                        "text-[10px] font-bold uppercase tracking-widest text-zinc-500 py-2 px-3",
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
                                            className="border-b border-zinc-900 hover:bg-zinc-900/30 transition-colors"
                                        >
                                            <td className="py-3 px-3">
                                                <Link
                                                    href={`/ledger/${encodeURIComponent(row.pundit_id)}`}
                                                    className="font-black text-white hover:text-emerald-400 transition-colors text-sm"
                                                >
                                                    {row.pundit_name}
                                                </Link>
                                                {row.outlet && (
                                                    <div className="text-[11px] text-zinc-500 mt-0.5">
                                                        {row.outlet}
                                                    </div>
                                                )}
                                            </td>
                                            <td className="py-3 px-3 text-right font-mono text-sm text-zinc-300 tabular-nums">
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
                            <div className="border-t-2 border-white pt-3 flex items-baseline justify-between mb-4">
                                <h2 className="text-xl font-black text-white">
                                    {activeTab === "by-pundit"
                                        ? `Claims by Pundit`
                                        : `All Claims about ${entity.entity_name}`}
                                </h2>
                            </div>

                            {claims.length === 0 && (
                                <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 py-12 text-center text-zinc-500 text-sm">
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
                                        className="text-sm font-semibold text-amber-400 hover:text-amber-300 transition-colors font-mono"
                                    >
                                        Load more →
                                    </button>
                                    <span className="text-xs text-zinc-600 ml-3 font-mono">
                                        Showing {claimsShown} of {claims.length}
                                    </span>
                                </div>
                            )}
                        </div>
                    )}

                    {/* Claim Timeline tab */}
                    {activeTab === "claim-timeline" && (
                        <div>
                            <div className="border-t-2 border-white pt-3 mb-4">
                                <h2 className="text-xl font-black text-white">Claim Timeline</h2>
                            </div>
                            <div className="space-y-0">
                                {timeline.map((evt, i) => (
                                    <div
                                        key={i}
                                        className="grid grid-cols-[80px_1fr] gap-4 py-4 border-b border-zinc-900 last:border-b-0"
                                    >
                                        <div className="font-mono text-[11px] text-zinc-500 leading-5 whitespace-pre-line">
                                            {evt.date_str}
                                        </div>
                                        <div className="text-sm text-zinc-300 leading-5">
                                            <span className="font-bold text-white">{evt.pundit_name}</span>{" "}
                                            {evt.summary.replace(/ — (correct|incorrect|pending)$/, "")}
                                            {" — "}
                                            <span
                                                className={cn(
                                                    "font-semibold",
                                                    evt.status === "correct"
                                                        ? "text-emerald-400"
                                                        : evt.status === "incorrect"
                                                        ? "text-red-400"
                                                        : "text-amber-400"
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
                    <div className="bg-zinc-950 border border-zinc-800 p-5 rounded">
                        <div className="text-[11px] font-bold uppercase tracking-[2px] text-amber-400 border-b border-zinc-800 pb-3 mb-4">
                            Related Entities
                        </div>
                        <div className="space-y-0 divide-y divide-zinc-900">
                            {relatedEntities.map((rel) => (
                                <Link
                                    key={rel.entity_id}
                                    href={`/entity/${rel.entity_type}/${encodeURIComponent(rel.entity_id)}`}
                                    className="flex items-center justify-between py-3 group"
                                >
                                    <div className="flex items-center gap-3">
                                        <div className="w-8 h-8 rounded bg-zinc-800 border border-zinc-700 flex items-center justify-center text-[10px] font-bold text-zinc-300 shrink-0">
                                            {rel.initials ?? getInitials(rel.entity_name)}
                                        </div>
                                        <div>
                                            <div className="text-sm font-semibold text-zinc-200 group-hover:text-emerald-400 transition-colors">
                                                {rel.entity_name}
                                            </div>
                                            {rel.entity_subtype && (
                                                <div className="text-[11px] text-zinc-500 capitalize">
                                                    {ENTITY_TYPE_LABELS[rel.entity_type] ?? rel.entity_type} · {rel.entity_subtype}
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                    <div className="font-mono text-[11px] text-zinc-500 tabular-nums">
                                        {rel.co_mention_count.toLocaleString()} claims
                                    </div>
                                </Link>
                            ))}
                        </div>
                    </div>

                    {/* Recent activity timeline */}
                    <div className="bg-zinc-950 border border-zinc-800 p-5 rounded">
                        <div className="text-[11px] font-bold uppercase tracking-[2px] text-amber-400 border-b border-zinc-800 pb-3 mb-4">
                            Recent Activity
                        </div>
                        <div className="space-y-0 divide-y divide-zinc-900">
                            {timeline.map((evt, i) => (
                                <div key={i} className="grid grid-cols-[56px_1fr] gap-3 py-3">
                                    <div className="font-mono text-[10px] text-zinc-500 leading-4 whitespace-pre-line">
                                        {evt.date_str}
                                    </div>
                                    <div className="text-xs text-zinc-400 leading-4">
                                        <span className="font-bold text-zinc-200">{evt.pundit_name}</span>{" "}
                                        {evt.summary.replace(/ — (correct|incorrect|pending)$/, "")}
                                        {" — "}
                                        <span
                                            className={cn(
                                                "font-semibold",
                                                evt.status === "correct"
                                                    ? "text-emerald-400"
                                                    : evt.status === "incorrect"
                                                    ? "text-red-400"
                                                    : "text-amber-400"
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
                    <div className="bg-zinc-950 border border-zinc-800 p-5 rounded">
                        <div className="text-[11px] font-bold uppercase tracking-[2px] text-amber-400 border-b border-zinc-800 pb-3 mb-4">
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
            ? "border-l-emerald-500"
            : claim.resolution_status === "INCORRECT"
            ? "border-l-red-500"
            : "border-l-amber-500";

    return (
        <div
            className={cn(
                "bg-zinc-950 border border-zinc-800 border-l-4 p-5 relative",
                borderColor
            )}
        >
            {/* Top row: pundit + status */}
            <div className="flex items-start justify-between gap-3 mb-2">
                <div>
                    <Link
                        href={`/ledger/${encodeURIComponent(claim.pundit_id)}`}
                        className="font-black text-sm text-white hover:text-emerald-400 transition-colors"
                    >
                        {claim.pundit_name}
                    </Link>
                    {claim.outlet && (
                        <span className="text-zinc-500 text-sm"> · {claim.outlet}</span>
                    )}
                    <div className="text-[11px] text-zinc-500 font-mono mt-0.5">
                        {claim.claim_date ?? ""}
                        {claim.claim_context ? ` · ${claim.claim_context}` : ""}
                    </div>
                </div>
                <ClaimStatusBadge status={claim.resolution_status} />
            </div>

            {/* Quote */}
            <p className="text-base italic text-zinc-300 leading-relaxed mb-3 font-serif">
                &ldquo;{claim.claim_text}&rdquo;
            </p>

            {/* Bottom row: confidence + hash */}
            <div className="flex items-center justify-between">
                <ConfBar confidence={claim.confidence ?? null} status={claim.resolution_status} />
                {claim.hash_short && (
                    <span className="font-mono text-[9px] text-zinc-700">
                        {claim.hash_short}
                    </span>
                )}
            </div>
        </div>
    );
}
