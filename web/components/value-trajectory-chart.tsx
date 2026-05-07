"use client";

import React from "react";
import {
    ComposedChart,
    Line,
    Bar,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    Legend,
    ResponsiveContainer,
    Area
} from "recharts";
import { ShieldAlert } from "lucide-react";

interface ChartDataPoint {
    year: number;
    actual: number;
    predicted: number;
    error: number;
    bounds: [number, number];
}

interface ValueTrajectoryChartProps {
    chartDataWithBands: ChartDataPoint[];
    playerYear?: number;
}

export function ValueTrajectoryChart({ chartDataWithBands, playerYear }: ValueTrajectoryChartProps) {
    if (chartDataWithBands.length === 0) {
        return (
            <div className="h-full flex flex-col items-center justify-center border border-dashed border-slate-800 rounded-lg bg-slate-950/30">
                <ShieldAlert className="h-8 w-8 text-slate-600 mb-3" />
                <h4 className="text-sm font-semibold text-slate-300">Insufficient Historical Data</h4>
                <p className="text-xs text-slate-500 mt-1 max-w-[250px] text-center">
                    This asset lacks the required historical telemetry to generate a multi-year value trajectory model.
                </p>
            </div>
        );
    }

    return (
        <ResponsiveContainer width="100%" height="100%" minHeight={1} minWidth={1}>
            <ComposedChart data={chartDataWithBands} margin={{ top: 20, right: 30, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" opacity={0.15} />
                <XAxis dataKey="year" stroke="#94a3b8" />
                <YAxis stroke="#94a3b8" tickFormatter={(v) => `$${v}M`} />
                <Tooltip
                    contentStyle={{ backgroundColor: '#18181b', borderColor: '#27272a', color: '#fff' }}
                    itemStyle={{ color: '#fff' }}
                    formatter={(value: any, name: any) => name === "Model Variance (95% CI)" ? null : [`$${Number(value).toFixed(2)}M`, name]}
                />
                <Legend wrapperStyle={{ paddingTop: '20px' }} />
                <Area type="monotone" dataKey="bounds" name="Model Variance (95% CI)" fill="#10b981" stroke="none" fillOpacity={0.1} />
                <Line type="monotone" dataKey="predicted" name="Fair Market Value" stroke="#10b981" strokeWidth={2} dot={false} strokeDasharray="5 5" />
                <Line type="monotone" dataKey="actual" name="Actual Cap Hit" stroke="#f472b6" strokeWidth={3} dot={{ r: 4 }} activeDot={{ r: 8 }} />
                <Bar dataKey="error" name="Overpay/Underpay" fill="#64748b" opacity={0.3} barSize={20} />
            </ComposedChart>
        </ResponsiveContainer>
    );
}
