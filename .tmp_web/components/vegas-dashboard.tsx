
"use client"

import * as React from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { TrendingUp, TrendingDown, DollarSign, Activity } from "lucide-react"

interface VegasImpact {
    delta_wins: number
    new_win_total: number
    vegas_variance: number
    ceiling: number
    floor: number
    super_bowl_odds_delta: string
}

export function VegasDashboard({
    teamA,
    impactA,
    teamB,
    impactB
}: {
    teamA: string,
    impactA: VegasImpact,
    teamB: string,
    impactB: VegasImpact
}) {
    return (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
            <TeamVegasCard team={teamA} impact={impactA} />
            <TeamVegasCard team={teamB} impact={impactB} />
        </div>
    )
}

function TeamVegasCard({ team, impact }: { team: string, impact: VegasImpact }) {
    const isPositive = impact.delta_wins > 0
    const colorClass = isPositive ? "text-emerald-400" : "text-rose-400"

    return (
        <Card className="bg-slate-950 border-slate-800">
            <CardHeader className="pb-2">
                <div className="flex justify-between items-center">
                    <CardTitle className="text-sm uppercase font-mono text-muted-foreground tracking-widest">
                        {team} Vegas Impact
                    </CardTitle>
                    {isPositive ? <TrendingUp className="h-4 w-4 text-emerald-500" /> : <TrendingDown className="h-4 w-4 text-rose-500" />}
                </div>
            </CardHeader>
            <CardContent>
                <div className="flex items-end justify-between">
                    <div>
                        <div className="text-3xl font-black font-numeric tracking-tighter">
                            {impact.new_win_total}
                            <span className={`text-sm font-bold ml-2 ${colorClass}`}>
                                ({isPositive ? "+" : ""}{impact.delta_wins})
                            </span>
                        </div>
                        <p className="text-xs text-muted-foreground mt-1">Projected Wins</p>
                    </div>

                    <div className="text-right">
                        <div className={`text-xl font-bold font-mono ${colorClass}`}>
                            {impact.super_bowl_odds_delta}
                        </div>
                        <p className="text-xs text-muted-foreground mt-1">Super Bowl Odds</p>
                    </div>
                </div>

                {/* Variance Bar / Spread */}
                <div className="mt-6">
                    <div className="flex justify-between text-[10px] text-muted-foreground mb-1 uppercase font-mono">
                        <span>Floor: {impact.floor}</span>
                        <span>Ceiling: {impact.ceiling}</span>
                    </div>
                    <div className="h-2 bg-slate-800 rounded-full overflow-hidden relative">
                        {/* Variance Indicator */}
                        <div
                            className="absolute h-full bg-indigo-500/50"
                            style={{
                                left: "20%",
                                right: "20%"
                            }}
                        />
                        {/* Median Marker */}
                        <div
                            className="absolute h-full w-1 bg-white"
                            style={{ left: "50%" }}
                        />
                    </div>
                    <p className="text-[10px] text-center text-slate-500 mt-1 italic">
                        Implied Volatility: +/- {impact.vegas_variance} Wins
                    </p>
                </div>
            </CardContent>
        </Card>
    )
}
