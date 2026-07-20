"use client";

import React, { useState } from "react";
import { Info, ChevronDown, ChevronUp, Quote, Cpu, Star, CheckSquare } from "lucide-react";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ProvenanceData {
    /** Verbatim original quote from the pundit */
    raw_assertion_text?: string | null;
    /** LLM-structured testable statement (may differ from raw) */
    extracted_claim?: string | null;
    /** LLM provider that extracted this prediction, e.g. "ollama", "google" */
    llm_provider?: string | null;
    /** Model name, e.g. "qwen2.5:32b", "gemini-1.5-pro" */
    llm_model?: string | null;
    /** Prompt version used during extraction, e.g. "v1.4" */
    prompt_version?: string | null;
    /** Quality score 0.0–1.0 from gold_layer.assertion_quality */
    quality_score?: number | null;
    /** How the outcome was resolved, e.g. "sportsdataio", "pfr", "spotrac", "manual" */
    outcome_source?: string | null;
    /** Human explanation of resolution edge cases */
    outcome_notes?: string | null;
}

interface ProvenanceBadgeProps {
    data: ProvenanceData;
    /** Compact mode — only show the info toggle button, no inline labels */
    compact?: boolean;
    className?: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

// Matches ClaimProvenance's qualityBadge() on the pundit-detail slice
// (web/app/ledger/[pundit_id]/PunditProfileClient.tsx, #1067) — extraction
// quality is a data-confidence scale, not an accuracy/outcome value, so it
// keeps its own 3-tier correct/pending/incorrect coloring rather than the
// navy-chip treatment used for accuracy.
function qualityLabel(score: number): { label: string; color: string } {
    if (score >= 0.7) return { label: "HIGH", color: "text-correct" };
    if (score >= 0.4) return { label: "MED", color: "text-pending" };
    return { label: "LOW", color: "text-incorrect" };
}

function formatModel(provider: string | null | undefined, model: string | null | undefined): string | null {
    if (!provider && !model) return null;
    if (!model) return provider ?? null;

    // Humanize common provider/model combos
    const providerLower = (provider ?? "").toLowerCase();
    const modelLower = (model ?? "").toLowerCase();

    if (providerLower === "ollama") {
        if (modelLower.includes("qwen2.5")) {
            const sizeMatch = model.match(/(\d+)b/i);
            const size = sizeMatch ? ` ${sizeMatch[1]}B` : "";
            return `Qwen 2.5${size} (Ollama)`;
        }
        if (modelLower.includes("llama")) return `Llama (Ollama)`;
        return `${model} (Ollama)`;
    }
    if (providerLower === "google" || providerLower === "gemini") {
        if (modelLower.includes("gemini-1.5")) return "Gemini 1.5";
        if (modelLower.includes("gemini-2")) return "Gemini 2";
        return model ?? "Gemini";
    }
    if (providerLower === "anthropic") return `Claude (${model})`;
    return model;
}

function formatOutcomeSource(source: string | null | undefined): string | null {
    if (!source) return null;
    const map: Record<string, string> = {
        sportsdataio: "SportsData.io",
        pfr: "Pro Football Reference",
        spotrac: "Spotrac transaction wire",
        manual: "Manual review",
        "official-team": "Official team report",
    };
    return map[source.toLowerCase()] ?? source;
}

// ---------------------------------------------------------------------------
// ProvenanceBadge
// ---------------------------------------------------------------------------

/**
 * Collapsible provenance info badge for prediction cards.
 *
 * Collapsed: a small ⓘ icon button.
 * Expanded: shows raw quote, extracted claim (if different), extraction model,
 * quality score, and resolution source.
 *
 * All fields are optional — gracefully hides sections with no data.
 */
export function ProvenanceBadge({ data, compact = false, className }: ProvenanceBadgeProps) {
    const [open, setOpen] = useState(false);

    const {
        raw_assertion_text,
        extracted_claim,
        llm_provider,
        llm_model,
        prompt_version,
        quality_score,
        outcome_source,
        outcome_notes,
    } = data;

    const modelLabel = formatModel(llm_provider, llm_model);
    const sourceLabel = formatOutcomeSource(outcome_source);

    // Only render the badge if there's at least one piece of provenance data
    const hasAnyData =
        raw_assertion_text || modelLabel || quality_score !== null && quality_score !== undefined || sourceLabel;

    if (!hasAnyData) return null;

    const rawDiffersFromClaim =
        raw_assertion_text &&
        extracted_claim &&
        raw_assertion_text.trim() !== extracted_claim.trim();

    const qualityInfo =
        quality_score !== null && quality_score !== undefined
            ? qualityLabel(quality_score)
            : null;

    return (
        <div className={cn("mt-2", className)}>
            {/* Toggle button */}
            <button
                onClick={() => setOpen((v) => !v)}
                className={cn(
                    "inline-flex items-center gap-1 text-[10px] font-mono text-ink-3",
                    "hover:text-ink-2 transition-colors",
                    "border border-editorial-border rounded px-1.5 py-0.5",
                    open && "text-ink-2 border-editorial-border"
                )}
                aria-expanded={open}
                aria-label={open ? "Hide provenance" : "Show provenance"}
            >
                <Info className="w-2.5 h-2.5" />
                {!compact && <span>Source & Provenance</span>}
                {open ? <ChevronUp className="w-2.5 h-2.5" /> : <ChevronDown className="w-2.5 h-2.5" />}
            </button>

            {/* Expanded panel */}
            {open && (
                <div className="mt-2 rounded-lg border border-editorial-border bg-editorial-card p-3 space-y-3 text-xs">
                    {/* Raw quote */}
                    {raw_assertion_text && (
                        <div>
                            <div className="flex items-center gap-1 text-[9px] font-mono uppercase tracking-widest text-ink-3 mb-1">
                                <Quote className="w-2.5 h-2.5" />
                                Raw Quote
                            </div>
                            <p className="text-ink-2 italic leading-snug border-l-2 border-editorial-border pl-2">
                                &ldquo;{raw_assertion_text}&rdquo;
                            </p>
                            {rawDiffersFromClaim && extracted_claim && (
                                <div className="mt-2">
                                    <div className="text-[9px] font-mono uppercase tracking-widest text-ink-3 mb-1">
                                        Extracted Claim
                                    </div>
                                    <p className="text-ink-2 leading-snug border-l-2 border-editorial-border pl-2">
                                        {extracted_claim}
                                    </p>
                                </div>
                            )}
                        </div>
                    )}

                    {/* Extraction model + quality */}
                    {(modelLabel || qualityInfo) && (
                        <div>
                            <div className="flex items-center gap-1 text-[9px] font-mono uppercase tracking-widest text-ink-3 mb-1">
                                <Cpu className="w-2.5 h-2.5" />
                                Extraction
                            </div>
                            <div className="flex flex-wrap items-center gap-2 text-ink-2 font-mono">
                                {modelLabel && (
                                    <span>{modelLabel}</span>
                                )}
                                {prompt_version && (
                                    <span className="text-ink-3">· Prompt {prompt_version}</span>
                                )}
                                {qualityInfo && (
                                    <span className="inline-flex items-center gap-1">
                                        <Star className="w-2.5 h-2.5" />
                                        <span>Quality:&nbsp;</span>
                                        <span className={cn("font-semibold", qualityInfo.color)}>
                                            {quality_score!.toFixed(2)} ({qualityInfo.label})
                                        </span>
                                    </span>
                                )}
                            </div>
                        </div>
                    )}

                    {/* Resolution source */}
                    {(sourceLabel || outcome_notes) && (
                        <div>
                            <div className="flex items-center gap-1 text-[9px] font-mono uppercase tracking-widest text-ink-3 mb-1">
                                <CheckSquare className="w-2.5 h-2.5" />
                                Resolution Source
                            </div>
                            <div className="text-ink-2 font-mono space-y-0.5">
                                {sourceLabel && (
                                    <span>Resolved via {sourceLabel}</span>
                                )}
                                {outcome_notes && (
                                    <p className="text-ink-3 italic leading-snug mt-1">
                                        {outcome_notes}
                                    </p>
                                )}
                            </div>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}
