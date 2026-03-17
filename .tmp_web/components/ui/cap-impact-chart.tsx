"use client"

import { BarChart, Bar, XAxis, YAxis, ResponsiveContainer, Cell, ReferenceLine, Tooltip } from 'recharts'

export function CapImpactChart({
    teamA,
    impactA,
    teamB,
    impactB
}: {
    teamA: string,
    impactA: number, // Net Cap Savings (Positive = Good)
    teamB: string,
    impactB: number
}) {
    const data = [
        { name: teamA, value: impactA },
        { name: teamB, value: impactB }
    ];

    return (
        <div className="h-[120px] w-full">
            <ResponsiveContainer width="100%" height="100%">
                <BarChart layout="vertical" data={data} margin={{ top: 5, right: 30, left: 40, bottom: 5 }}>
                    <XAxis type="number" hide />
                    <YAxis dataKey="name" type="category" width={40} tick={{ fontSize: 10, fill: '#94a3b8' }} />
                    <Tooltip
                        cursor={{ fill: 'transparent' }}
                        contentStyle={{ backgroundColor: '#1e293b', border: 'none', fontSize: '12px' }}
                        formatter={(value: number | undefined) => [`$${(value || 0).toFixed(2)}M`, "Cap Savings"]}
                    />
                    <ReferenceLine x={0} stroke="#475569" />
                    <Bar dataKey="value" barSize={20} radius={[0, 4, 4, 0]}>
                        {data.map((entry, index) => (
                            <Cell key={`cell-${index}`} fill={entry.value >= 0 ? '#10b981' : '#ef4444'} />
                        ))}
                    </Bar>
                </BarChart>
            </ResponsiveContainer>
        </div>
    )
}
