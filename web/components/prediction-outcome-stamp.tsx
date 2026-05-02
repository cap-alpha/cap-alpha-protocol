"use client";

import { cn } from "@/lib/utils";

export type OutcomeStampOutcome = "correct" | "incorrect" | "pending" | "void";

export type OutcomeStampProps = {
  outcome: OutcomeStampOutcome;
  size?: "sm" | "md" | "lg";
  className?: string;
};

const OUTCOME_CONFIG: Record<
  OutcomeStampOutcome,
  {
    label: string;
    color: string;
    bg: string;
    rotation: string;
  }
> = {
  correct: {
    label: "CORRECT \u2713",
    color: "#22c55e",
    bg: "rgba(34,197,94,0.08)",
    rotation: "-8deg",
  },
  incorrect: {
    label: "INCORRECT \u2717",
    color: "#ef4444",
    bg: "rgba(239,68,68,0.08)",
    rotation: "-8deg",
  },
  pending: {
    label: "PENDING",
    color: "#f59e0b",
    bg: "rgba(245,158,11,0.08)",
    rotation: "0deg",
  },
  void: {
    label: "VOID",
    color: "#71717a",
    bg: "rgba(113,113,122,0.08)",
    rotation: "-8deg",
  },
};

const SIZE_CLASSES: Record<
  NonNullable<OutcomeStampProps["size"]>,
  { text: string; padding: string; border: string }
> = {
  sm: { text: "text-xs", padding: "px-2 py-0.5", border: "border-[1.5px]" },
  md: { text: "text-sm", padding: "px-3 py-1", border: "border-2" },
  lg: { text: "text-base", padding: "px-4 py-1.5", border: "border-2" },
};

export function PredictionOutcomeStamp({
  outcome,
  size = "md",
  className,
}: OutcomeStampProps) {
  const config = OUTCOME_CONFIG[outcome];
  const sizeConfig = SIZE_CLASSES[size];

  return (
    <span
      data-testid="outcome-stamp"
      data-outcome={outcome}
      className={cn(
        "inline-flex items-center justify-center font-black uppercase tracking-widest font-mono select-none",
        sizeConfig.text,
        sizeConfig.padding,
        sizeConfig.border,
        "motion-reduce:![transform:none]",
        className
      )}
      style={{
        color: config.color,
        borderColor: config.color,
        backgroundColor: config.bg,
        transform: `rotate(${config.rotation})`,
        outline: `2px solid ${config.color}`,
        outlineOffset: "3px",
      }}
    >
      {config.label}
    </span>
  );
}
