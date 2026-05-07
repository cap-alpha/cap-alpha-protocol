"use client";

import React from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Users } from "lucide-react";
import type { PositionalComp } from "@/app/actions";

interface PositionalCompsTableProps {
  data: PositionalComp[];
  currentPlayerName: string;
  position: string;
}

export function PositionalCompsTable({
  data,
  currentPlayerName,
  position,
}: PositionalCompsTableProps) {
  if (!data || data.length === 0) {
    return (
      <Card className="bg-zinc-900 border-zinc-800">
        <CardHeader className="pb-3 border-b border-zinc-800/50">
          <CardTitle className="text-xs font-mono font-bold tracking-widest text-zinc-500 uppercase">
            Positional Comps
          </CardTitle>
          <CardDescription>Top-10 {position} by FMV efficiency</CardDescription>
        </CardHeader>
        <CardContent className="flex items-center justify-center h-[200px]">
          <div className="text-center">
            <Users className="h-8 w-8 text-zinc-700 mx-auto mb-3" />
            <p className="text-sm text-zinc-500">No positional comp data available</p>
          </div>
        </CardContent>
      </Card>
    );
  }

  const normalizedCurrentName = currentPlayerName.toLowerCase();

  return (
    <Card className="bg-zinc-900 border-zinc-800">
      <CardHeader className="pb-3 border-b border-zinc-800/50">
        <CardTitle className="text-xs font-mono font-bold tracking-widest text-zinc-500 uppercase">
          Positional Comps — {position}
        </CardTitle>
        <CardDescription>
          Top 10 by FMV / cap hit efficiency ratio
        </CardDescription>
      </CardHeader>
      <CardContent className="p-0">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-zinc-800/50">
                <th className="text-left px-4 py-3 text-[10px] uppercase tracking-wider text-zinc-500 font-semibold">
                  #
                </th>
                <th className="text-left px-4 py-3 text-[10px] uppercase tracking-wider text-zinc-500 font-semibold">
                  Player
                </th>
                <th className="text-right px-4 py-3 text-[10px] uppercase tracking-wider text-zinc-500 font-semibold">
                  FMV
                </th>
                <th className="text-right px-4 py-3 text-[10px] uppercase tracking-wider text-zinc-500 font-semibold">
                  Cap Hit
                </th>
                <th className="text-right px-4 py-3 text-[10px] uppercase tracking-wider text-zinc-500 font-semibold">
                  Efficiency
                </th>
              </tr>
            </thead>
            <tbody>
              {data.map((comp, i) => {
                const isCurrent =
                  comp.name.toLowerCase() === normalizedCurrentName;
                return (
                  <tr
                    key={`${comp.name}-${comp.team}`}
                    className={`border-b border-zinc-800/30 transition-colors ${
                      isCurrent
                        ? "bg-emerald-500/10"
                        : "hover:bg-white/5"
                    }`}
                  >
                    <td className="px-4 py-2.5 font-mono text-zinc-500 text-xs">
                      {i + 1}
                    </td>
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-2">
                        <span
                          className={`font-medium ${
                            isCurrent ? "text-emerald-400" : "text-zinc-200"
                          }`}
                        >
                          {comp.name}
                        </span>
                        {isCurrent && (
                          <Badge
                            variant="outline"
                            className="text-[9px] px-1 py-0 border-emerald-500/30 text-emerald-400"
                          >
                            Viewed
                          </Badge>
                        )}
                        <span className="text-zinc-500 text-xs">{comp.team}</span>
                      </div>
                    </td>
                    <td className="px-4 py-2.5 text-right font-mono text-zinc-300">
                      ${comp.fmv.toFixed(1)}M
                    </td>
                    <td className="px-4 py-2.5 text-right font-mono text-zinc-300">
                      ${comp.cap_hit.toFixed(1)}M
                    </td>
                    <td className="px-4 py-2.5 text-right">
                      <span
                        className={`font-mono font-semibold ${
                          comp.efficiency >= 1
                            ? "text-emerald-400"
                            : "text-rose-400"
                        }`}
                      >
                        {comp.efficiency.toFixed(2)}x
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
