"use client";

import { useState } from "react";
import { FantasySyncWizard } from "@/components/fantasy-sync-wizard";
import { RosterGrid } from "@/components/roster-grid";
import { IntelligenceFeed } from "@/components/intelligence-feed";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Trophy, TrendingUp, AlertTriangle } from "lucide-react";

export function FantasyDashboard({ rosterData }: { rosterData: any[] }) {
    const [isSynced, setIsSynced] = useState(false);

    // Mock a fantasy team by picking top skilled players across different actual teams
    // For realistic mock: 2 QB, 4 WR, 4 RB, 2 TE, 1 K
    const myTeam = rosterData.filter(p =>
        ['QB', 'WR', 'RB', 'TE'].includes(p.position) && p.cap_hit_millions > 15
    ).slice(0, 14);

    const teamRiskCap = myTeam.filter(p => p.risk_score > 0.7).reduce((acc, p) => acc + p.cap_hit_millions, 0);
    const hasRisk = teamRiskCap > 30;

    if (!isSynced) {
        return (
            <div className="flex items-center justify-center min-h-[60vh]">
                <FantasySyncWizard onComplete={() => setIsSynced(true)} />
            </div>
        );
    }

    return (
        <div className="space-y-8 animate-in fade-in duration-500">
            {/* Header Metrics */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <Card className="bg-slate-900 border-transparent shadow-none">
                    <CardHeader className="pb-2">
                        <CardTitle className="text-xs text-emerald-400 font-mono flex items-center gap-2">
                            <Trophy className="h-4 w-4" />
                            <span className="uppercase font-bold tracking-wider">League Projection</span>
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="text-3xl font-black text-white">1st (Proj. 12-2)</div>
                        <p className="text-xs text-slate-500 mt-1">Cap Alpha Win Probability: 78%</p>
                    </CardContent>
                </Card>
                <Card className="bg-slate-900 border-transparent shadow-none">
                    <CardHeader className="pb-2">
                        <CardTitle className="text-xs text-slate-400 font-mono flex items-center gap-2">
                            <TrendingUp className="h-4 w-4 text-emerald-500" />
                            <span className="uppercase font-bold text-emerald-500 tracking-wider">Surplus Value</span>
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="text-3xl font-black text-emerald-400">+$42.5M</div>
                        <p className="text-xs text-slate-500 mt-1">Value accrued vs ADP Cost</p>
                    </CardContent>
                </Card>
                <Card className="bg-slate-900 border-transparent shadow-none">
                    <CardHeader className="pb-2">
                        <CardTitle className="text-xs text-slate-400 font-mono flex items-center gap-2">
                            <AlertTriangle className={hasRisk ? "h-4 w-4 text-rose-500" : "h-4 w-4 text-amber-500"} />
                            <span className={`uppercase font-bold tracking-wider ${hasRisk ? "text-rose-500" : "text-amber-500"}`}>
                                Portfolio Risk
                            </span>
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className={hasRisk ? "text-3xl font-black text-rose-500" : "text-3xl font-black text-amber-400"}>
                            {hasRisk ? "HIGH VOLATILITY" : "MODERATE"}
                        </div>
                        <p className="text-xs text-slate-500 mt-1">Exposure tied to aging RBs</p>
                    </CardContent>
                </Card>
            </div>

            {/* Split View */}
            <div className="grid grid-cols-1 xl:grid-cols-4 gap-8">
                <div className="xl:col-span-3">
                    <Card className="bg-card border-border h-full">
                        <CardHeader className="flex flex-row items-center justify-between pb-4">
                            <div>
                                <CardTitle className="uppercase font-mono tracking-widest text-sm text-slate-400">My Fantasy Roster // 2026</CardTitle>
                            </div>
                            <Badge variant="outline" className="bg-emerald-500/10 text-emerald-500 border-emerald-500/20">Synced LIVE</Badge>
                        </CardHeader>
                        <CardContent className="p-0">
                            <RosterGrid data={myTeam} initialSearch="" />
                        </CardContent>
                    </Card>
                </div>
                <div className="xl:col-span-1 h-[600px] xl:h-auto">
                    {/* Reusing the Mock RAG Feed for fantasy analysis */}
                    <IntelligenceFeed playerName="My Roster" riskScore={hasRisk ? 0.8 : 0.3} />
                </div>
            </div>
        </div>
    );
}
