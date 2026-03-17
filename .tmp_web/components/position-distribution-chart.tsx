"use client";

import {
    BarChart,
    Bar,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    ResponsiveContainer,
    Cell
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";

interface DistributionBucket {
    range: string;
    count: number;
    players: string[];
    min: number;
}

interface PositionDistributionChartProps {
    data: DistributionBucket[];
    playerCapHit: number;
    position: string;
}

export function PositionDistributionChart({ data, playerCapHit, position }: PositionDistributionChartProps) {
    // Find which bucket the player falls into to highlight it
    const activeIndex = data.findIndex(d => {
        const [minStr, maxStr] = d.range.replace(/\$/g, '').replace(/M/g, '').split(' - ');
        const min = parseFloat(minStr);
        const max = parseFloat(maxStr);
        return playerCapHit >= min && playerCapHit < max;
    });

    return (
        <Card className="bg-slate-900 border-slate-800 w-full">
            <CardHeader>
                <CardTitle>{position} Contract Distribution</CardTitle>
                <CardDescription>Cap Hit Frequency across the League</CardDescription>
            </CardHeader>
            <CardContent className="h-[350px]">
                <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={data} margin={{ top: 20, right: 30, left: 20, bottom: 50 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#334155" opacity={0.5} />
                        <XAxis
                            dataKey="range"
                            stroke="#94a3b8"
                            tick={{ fontSize: 10 }}
                            interval={2}
                            label={{ value: 'Salary Buckets ($M)', position: 'insideBottom', offset: -25, fill: '#64748b', fontSize: 12 }}
                        />
                        <YAxis stroke="#94a3b8" label={{ value: 'Contract Count', angle: -90, position: 'insideLeft', offset: -5, fill: '#64748b', fontSize: 12 }} />
                        <Tooltip
                            content={({ active, payload }) => {
                                if (active && payload && payload.length) {
                                    const data = payload[0].payload as DistributionBucket;
                                    return (
                                        <div className="bg-zinc-900 border border-zinc-800 p-2 rounded shadow-xl">
                                            <p className="font-bold text-white">{data.range}</p>
                                            <p className="text-emerald-400">{data.count} Players</p>
                                            <p className="text-xs text-zinc-500 mt-1 truncate max-w-[200px]">
                                                {data.players.slice(0, 3).join(', ')}{data.players.length > 3 ? '...' : ''}
                                            </p>
                                        </div>
                                    );
                                }
                                return null;
                            }}
                        />
                        <Bar dataKey="count" name="Players">
                            {data.map((entry, index) => (
                                <Cell
                                    key={`cell-${index}`}
                                    fill={index === activeIndex ? '#10b981' : '#3f3f46'}
                                    stroke={index === activeIndex ? '#34d399' : 'none'}
                                    strokeWidth={2}
                                />
                            ))}
                        </Bar>
                    </BarChart>
                </ResponsiveContainer>
            </CardContent>
        </Card>
    );
}
