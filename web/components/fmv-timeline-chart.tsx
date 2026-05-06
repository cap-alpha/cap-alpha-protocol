"use client";

import React from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { TrendingUp } from "lucide-react";
import type { FmvHistoryPoint } from "@/app/actions";

interface FmvTimelineChartProps {
  data: FmvHistoryPoint[];
  playerName: string;
}

export function FmvTimelineChart({ data, playerName }: FmvTimelineChartProps) {
  if (!data || data.length === 0) {
    return (
      <Card className="bg-zinc-900 border-zinc-800">
        <CardHeader className="pb-3 border-b border-zinc-800/50">
          <CardTitle className="text-xs font-mono font-bold tracking-widest text-zinc-500 uppercase">
            FMV Timeline
          </CardTitle>
          <CardDescription>Weekly fair market value vs cap hit</CardDescription>
        </CardHeader>
        <CardContent className="flex items-center justify-center h-[260px]">
          <div className="text-center">
            <TrendingUp className="h-8 w-8 text-zinc-700 mx-auto mb-3" />
            <p className="text-sm text-zinc-500">No weekly FMV history available</p>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="bg-zinc-900 border-zinc-800">
      <CardHeader className="pb-3 border-b border-zinc-800/50">
        <CardTitle className="text-xs font-mono font-bold tracking-widest text-zinc-500 uppercase">
          FMV Timeline
        </CardTitle>
        <CardDescription>
          {playerName} — fair market value vs cap hit over time
        </CardDescription>
      </CardHeader>
      <CardContent className="h-[300px] pt-4">
        <ResponsiveContainer width="100%" height="100%" minHeight={1} minWidth={1}>
          <LineChart data={data} margin={{ top: 10, right: 20, left: 0, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" opacity={0.15} />
            <XAxis
              dataKey="week"
              stroke="#94a3b8"
              tick={{ fontSize: 10 }}
              interval="preserveStartEnd"
            />
            <YAxis
              stroke="#94a3b8"
              tick={{ fontSize: 11 }}
              tickFormatter={(v) => `$${Number(v).toFixed(1)}M`}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "#18181b",
                borderColor: "#27272a",
                color: "#fff",
                borderRadius: "8px",
              }}
              itemStyle={{ color: "#fff" }}
              formatter={(value: number | undefined, name: string): [string, string] => {
                if (value == null) return ['—', String(name)]
                return [`$${value.toFixed(1)}M`, String(name)]
              }}
            />
            <Legend wrapperStyle={{ paddingTop: "12px" }} />
            <Line
              type="monotone"
              dataKey="fmv"
              name="Fair Market Value"
              stroke="#10b981"
              strokeWidth={2}
              dot={false}
              strokeDasharray="5 5"
            />
            <Line
              type="monotone"
              dataKey="cap_hit"
              name="Cap Hit"
              stroke="#f472b6"
              strokeWidth={2}
              dot={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
