"use client";

import Link from "next/link";
import { cn } from "@/lib/utils";
import { slugify } from "@/lib/utils";
import { PredictionOutcomeStamp } from "./prediction-outcome-stamp";

type PredictionOutcome = "correct" | "incorrect" | "pending" | "void";

export type PredictionCardPrediction = {
  id: string;
  text: string;
  pundidName: string;
  pundidSlug: string;
  madeAt: string;
  resolvedAt?: string;
  outcome: PredictionOutcome;
  confidence?: number;
};

export type PredictionCardProps = {
  prediction: PredictionCardPrediction;
  variant?: "compact" | "full";
  className?: string;
};

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return iso;
  }
}

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(Math.min(1, Math.max(0, value)) * 100);
  return (
    <div className="flex items-center gap-2">
      <span className="text-[10px] font-mono text-zinc-500 uppercase tracking-wider w-20">
        Confidence
      </span>
      <div className="flex-1 h-1 bg-zinc-800 rounded-full overflow-hidden">
        <div
          className="h-full bg-emerald-500 rounded-full"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-[10px] font-mono text-zinc-400 w-8 text-right">
        {pct}%
      </span>
    </div>
  );
}

export function PredictionCard({
  prediction,
  variant = "full",
  className,
}: PredictionCardProps) {
  const {
    text,
    pundidName,
    pundidSlug,
    madeAt,
    resolvedAt,
    outcome,
    confidence,
  } = prediction;

  if (variant === "compact") {
    return (
      <div
        className={cn(
          "flex items-center gap-3 rounded-lg border border-zinc-800 bg-[#111113] px-4 py-3 shadow-sm",
          className
        )}
      >
        <div className="flex-1 min-w-0">
          <p className="text-sm text-zinc-200 truncate">{text}</p>
          <p className="text-[10px] font-mono text-zinc-500 mt-0.5">
            <Link
              href={`/pundit/${pundidSlug}`}
              className="hover:text-emerald-400 transition-colors"
            >
              {pundidName}
            </Link>
            {" · "}
            {formatDate(madeAt)}
          </p>
        </div>
        <PredictionOutcomeStamp outcome={outcome} size="sm" className="shrink-0" />
      </div>
    );
  }

  // Full variant
  return (
    <div
      className={cn(
        "relative rounded-lg border border-zinc-800 bg-[#111113] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.04)] overflow-hidden",
        className
      )}
    >
      {/* Stamp overlay — top-right, absolute */}
      <div className="absolute top-4 right-4 z-10">
        <PredictionOutcomeStamp outcome={outcome} size="md" />
      </div>

      {/* Card body */}
      <div className="p-5">
        {/* Pundit header */}
        <div className="mb-4 pr-32">
          <Link
            href={`/pundit/${pundidSlug}`}
            className="text-xs font-mono font-bold uppercase tracking-widest text-emerald-400 hover:text-emerald-300 transition-colors"
          >
            {pundidName}
          </Link>
        </div>

        {/* Prediction text */}
        <p className="text-lg font-semibold italic text-zinc-100 leading-snug mb-5">
          &ldquo;{text}&rdquo;
        </p>

        {/* Confidence bar */}
        {confidence !== undefined && (
          <div className="mb-4">
            <ConfidenceBar value={confidence} />
          </div>
        )}

        {/* Date footer */}
        <div className="flex items-center justify-between border-t border-zinc-800/60 pt-3 mt-3">
          <div className="flex items-center gap-4 text-[10px] font-mono text-zinc-500 uppercase tracking-wider">
            <span>Made {formatDate(madeAt)}</span>
            {resolvedAt && <span>Resolved {formatDate(resolvedAt)}</span>}
          </div>
        </div>
      </div>
    </div>
  );
}
