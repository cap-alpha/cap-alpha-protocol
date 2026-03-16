import React from "react";
import { getRosterData, getWarRoomData } from "../../actions";
import { Activity, TrendingDown } from "lucide-react";
import { GlobalSearch } from "@/components/global-search";
import PersonaSwitcher from "@/components/persona-switcher";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import Link from "next/link";

export default async function BettorDashboard() {
    const [rosterData, warRoomData] = await Promise.all([
        getRosterData(),
        getWarRoomData()
    ]);

    // Bettors care about the delta between ML Alert and Media Consensus
    const alphaAlerts = [
        { player_name: "Travis Kelce", team: "KC", issue: "Athletic decline projected to exceed guaranteed money." },
        { player_name: "Von Miller", team: "BUF", issue: "Severe snap reduction projected despite CAP structure." }
    ];

    return (
        <main className="min-h-[100dvh] bg-background p-8 font-sans text-foreground">
            {/* Context Header */}
            <header className="mb-8 flex flex-col md:flex-row md:items-center justify-between border-b border-border pb-4 gap-4">
                <div className="flex items-center gap-4">
                    <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/30">
                        <Activity className="w-8 h-8 text-rose-500" />
                    </div>
                    <div>
                        <h1 className="text-3xl font-bold tracking-tight text-foreground">
                            Alpha <span className="text-rose-500">Terminal</span>
                        </h1>
                        <p className="text-muted-foreground mt-1 text-sm">
                            Volatility & Information Lag Arbitrage
                        </p>
                    </div>
                </div>
                <div className="flex gap-4 items-center">
                    <GlobalSearch />
                    <PersonaSwitcher />
                </div>
            </header>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                {/* Information Lag Feed */}
                <Card className="bg-card border-border shadow-lg">
                    <CardHeader className="pb-4">
                        <div className="flex items-center gap-2">
                            <TrendingDown className="h-5 w-5 text-rose-500" />
                            <CardTitle className="text-xl">Consensus Lead Time (EV+)</CardTitle>
                        </div>
                        <CardDescription>Identified assets where current performance significantly lags multi-year guarantees before public repricing.</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        {alphaAlerts.map((alert: any, i: number) => (
                            <div key={i} className="flex flex-col p-4 rounded-lg bg-zinc-950/50 border border-zinc-900 group">
                                <div className="flex justify-between items-center mb-2">
                                    <div className="flex items-center gap-2">
                                        <Badge variant="outline" className="bg-rose-500/10 text-rose-500 border-rose-500/20 uppercase tracking-widest text-[10px]">
                                            Short Prop
                                        </Badge>
                                        <Link href={`/player/${alert.player_name.toLowerCase().replace(' ', '-')}`} className="font-bold text-slate-200 hover:text-white hover:underline transition-colors">{alert.player_name}</Link>
                                    </div>
                                    <span className="text-xs font-mono text-slate-500">{alert.team}</span>
                                </div>
                                <p className="text-sm text-slate-400">
                                    {alert.issue}
                                </p>
                                <div className="mt-3 text-xs text-rose-400 font-mono">
                                    Alpha Window: Open (Public consensus unadjusted)
                                </div>
                            </div>
                        ))}
                    </CardContent>
                </Card>

                {/* Model Variance Heatmap (Placeholder) */}
                 <Card className="bg-card border-border shadow-lg flex items-center justify-center p-12 text-center h-[500px]">
                    <div>
                        <Activity className="h-16 w-16 text-rose-500/20 mx-auto mb-4" />
                        <CardTitle className="text-2xl font-bold mb-2">Predictive Variance Heatmap</CardTitle>
                        <p className="text-muted-foreground">Market-Making data visualizations are incoming for Sprint 10.</p>
                    </div>
                </Card>
            </div>
        </main>
    );
}
