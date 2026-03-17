
"use client";

import { LineChart, Line, ResponsiveContainer, YAxis } from "recharts";

import { cn } from "@/lib/utils";

export function CapSparkline({ data, className }: { data: any[], className?: string }) {
    if (!data || data.length < 2) {
        return <div className={cn("h-8 w-16 bg-zinc-800/20 rounded animate-pulse", className)} />;
    }

    // Determine trend color
    const start = data[0].actual;
    const end = data[data.length - 1].actual;
    const isUp = end > start;

    return (
        <div className={cn("h-8 w-24", className)}>
            <ResponsiveContainer width="100%" height="100%">
                <LineChart data={data}>
                    <Line
                        type="monotone"
                        dataKey="actual"
                        stroke={isUp ? "#ef4444" : "#10b981"} // Red if cap hit goes up (bad for team?), Green if down? 
                        // Actually, Cap Hit going up is normal. Let's color by Surplus Value if possible? 
                        // For now, let's just use a neutral color or based on the "Error" delta if available.
                        // Let's stick to simple: Grey for neutral, predicted vs actual.
                        strokeWidth={2}
                        dot={false}
                        isAnimationActive={false}
                    />
                    {/* Invisible YAxis to scale properly */}
                    <YAxis domain={['dataMin', 'dataMax']} hide />
                </LineChart>
            </ResponsiveContainer>
        </div>
    );
}
