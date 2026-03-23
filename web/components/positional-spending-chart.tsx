"use client";

import React from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";

interface PositionalSpendingChartProps {
    data: { position: string; teamSpend: number; leagueAvg: number }[];
    teamName: string;
}

export const PositionalSpendingChart = React.memo(function PositionalSpendingChart({ data, teamName }: PositionalSpendingChartProps) {
    if (!data || data.length === 0) return null;

    return (
        <Card className="bg-card border-border h-full">
            <CardHeader className="pb-2">
                <CardTitle className="uppercase font-mono tracking-widest text-sm text-slate-400">Positional Spending vs League Avg</CardTitle>
            </CardHeader>
            <CardContent className="h-[350px]">
                <ResponsiveContainer width="100%" height="100%" minHeight={1} minWidth={1}>
                    <BarChart data={data} margin={{ top: 20, right: 30, left: 0, bottom: 5 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#334155" opacity={0.2} />
                        <XAxis dataKey="position" stroke="#94a3b8" tick={{ fontSize: 12 }} />
                        <YAxis stroke="#94a3b8" tickFormatter={(v) => `$${v}M`} tick={{ fontSize: 12 }} />
                        <Tooltip 
                            contentStyle={{ backgroundColor: '#18181b', borderColor: '#27272a', color: '#fff', borderRadius: '8px' }}
                            itemStyle={{ color: '#fff' }}
                            formatter={(value: any, name: any) => [`$${Number(value).toFixed(1)}M`, name]}
                        />
                        <Legend wrapperStyle={{ paddingTop: '10px' }} />
                        <Bar dataKey="teamSpend" name={`${teamName}`} fill="#10b981" radius={[4, 4, 0, 0]} barSize={24} />
                        <Bar dataKey="leagueAvg" name="League Avg." fill="#64748b" radius={[4, 4, 0, 0]} barSize={24} opacity={0.6} />
                    </BarChart>
                </ResponsiveContainer>
            </CardContent>
        </Card>
    );
})
