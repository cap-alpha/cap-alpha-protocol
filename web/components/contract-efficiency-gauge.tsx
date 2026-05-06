"use client";

import React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";

interface ContractEfficiencyGaugeProps {
  fairMarketValue: number;
  capHit: number;
  playerName: string;
}

export function ContractEfficiencyGauge({
  fairMarketValue,
  capHit,
  playerName,
}: ContractEfficiencyGaugeProps) {
  const delta = fairMarketValue - capHit;
  const absDelta = Math.abs(delta);
  const isFair = absDelta < 0.5;
  const isUnderpaid = delta > 0;

  const label = isFair
    ? "Fair Value"
    : isUnderpaid
    ? `Underpaid by $${absDelta.toFixed(1)}M`
    : `Overpaid by $${absDelta.toFixed(1)}M`;

  const colorClass = isFair
    ? "text-zinc-300"
    : isUnderpaid
    ? "text-emerald-400"
    : "text-rose-400";

  const bgClass = isFair
    ? "bg-zinc-800/50 border-zinc-700/50"
    : isUnderpaid
    ? "bg-emerald-500/10 border-emerald-500/20"
    : "bg-rose-500/10 border-rose-500/20";

  const Icon = isFair ? Minus : isUnderpaid ? TrendingUp : TrendingDown;

  // Build a simple visual bar: cap hit vs FMV fill percentage
  const maxVal = Math.max(fairMarketValue, capHit, 1);
  const fmvPct = Math.min((fairMarketValue / maxVal) * 100, 100);
  const capPct = Math.min((capHit / maxVal) * 100, 100);

  return (
    <Card className="bg-zinc-900 border-zinc-800">
      <CardHeader className="pb-3 border-b border-zinc-800/50">
        <CardTitle className="text-xs font-mono font-bold tracking-widest text-zinc-500 uppercase">
          Contract Efficiency
        </CardTitle>
      </CardHeader>
      <CardContent className="pt-4 space-y-4">
        {/* Main verdict badge */}
        <div className={`flex items-center gap-3 p-3 rounded-lg border ${bgClass}`}>
          <Icon className={`h-5 w-5 flex-shrink-0 ${colorClass}`} />
          <div>
            <p className={`text-lg font-bold font-mono ${colorClass}`}>{label}</p>
            <p className="text-[10px] text-zinc-500 uppercase tracking-wider mt-0.5">
              FMV ${fairMarketValue.toFixed(1)}M vs Cap Hit ${capHit.toFixed(1)}M
            </p>
          </div>
        </div>

        {/* Visual bar comparison */}
        <div className="space-y-2">
          <div>
            <div className="flex justify-between items-center mb-1">
              <span className="text-[10px] uppercase tracking-wider text-zinc-500">
                Fair Market Value
              </span>
              <span className="text-xs font-mono text-emerald-400">
                ${fairMarketValue.toFixed(1)}M
              </span>
            </div>
            <div className="h-2 bg-zinc-800 rounded-full overflow-hidden">
              <div
                className="h-full bg-emerald-500 rounded-full transition-all duration-500"
                style={{ width: `${fmvPct}%` }}
              />
            </div>
          </div>

          <div>
            <div className="flex justify-between items-center mb-1">
              <span className="text-[10px] uppercase tracking-wider text-zinc-500">
                Cap Hit
              </span>
              <span className="text-xs font-mono text-rose-400">
                ${capHit.toFixed(1)}M
              </span>
            </div>
            <div className="h-2 bg-zinc-800 rounded-full overflow-hidden">
              <div
                className="h-full bg-rose-500 rounded-full transition-all duration-500"
                style={{ width: `${capPct}%` }}
              />
            </div>
          </div>
        </div>

        {/* Efficiency ratio */}
        <div className="pt-2 border-t border-zinc-800/50">
          <div className="flex justify-between items-center">
            <span className="text-[10px] uppercase tracking-wider text-zinc-500">
              FMV / Cap Ratio
            </span>
            <span
              className={`text-sm font-mono font-bold ${
                fairMarketValue / Math.max(capHit, 0.01) >= 1
                  ? "text-emerald-400"
                  : "text-rose-400"
              }`}
            >
              {(fairMarketValue / Math.max(capHit, 0.01)).toFixed(2)}x
            </span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
