import React from "react";
import { getRosterData, getWarRoomData } from "../../actions";

export const dynamic = 'force-dynamic';
import { Activity, TrendingDown } from "lucide-react";
import { GlobalSearch } from "@/components/global-search";
import PersonaSwitcher from "@/components/persona-switcher";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { SectionHeading } from "@/components/ui/heading";
import Link from "next/link";
import { slugify } from "@/lib/utils";

export default async function BettorDashboard() {
    const [rosterData, warRoomData] = await Promise.all([
        getRosterData(),
        getWarRoomData()
    ]);

    // Bettors care about the delta between ML Alert and Media Consensus.
    // Build a lookup from rosterData for cap/risk enrichment of each alert.
    const rosterMap = new Map(rosterData.map((p) => [p.player_name, p]));

    const alphaAlerts = warRoomData.redAlerts.map((alert) => {
        const player = rosterMap.get(alert.player_name);
        const parts: string[] = ["ML model flags high bust probability."];
        if ((player?.cap_hit_millions ?? 0) > 0) {
            parts.push(`$${(player?.cap_hit_millions ?? 0).toFixed(1)}M cap hit.`);
        }
        if ((player?.risk_score ?? 0) > 0) {
            parts.push(`Risk score: ${((player?.risk_score ?? 0) * 100).toFixed(0)}%.`);
        }
        return {
            player_name: alert.player_name,
            team: alert.team,
            issue: parts.join(" "),
        };
    });

    return (
        <main className="min-h-[100dvh] bg-editorial-bg p-8 font-sans text-ink">
            {/* Context Header */}
            <header className="mb-8 flex flex-col md:flex-row md:items-center justify-between border-b border-editorial-border pb-4 gap-4">
                <div className="flex items-center gap-4">
                    <div className="p-3 rounded-lg bg-incorrect/10 border border-incorrect/30">
                        <Activity className="w-8 h-8 text-incorrect" />
                    </div>
                    <div>
                        <SectionHeading size="xl" className="text-ink">
                            Alpha <span className="text-incorrect">Terminal</span>
                        </SectionHeading>
                        <p className="text-ink-2 mt-1 text-sm">
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
                <Card className="bg-editorial-card border-editorial-border shadow-lg">
                    <CardHeader className="pb-4">
                        <div className="flex items-center gap-2">
                            <TrendingDown className="h-5 w-5 text-incorrect" />
                            <CardTitle className="text-xl">Consensus Lead Time (EV+)</CardTitle>
                        </div>
                        <CardDescription>Identified assets where current performance significantly lags multi-year guarantees before public repricing.</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        {alphaAlerts.length === 0 && (
                            <p className="text-sm text-ink-2 text-center py-6">No active ML alerts.</p>
                        )}
                        {alphaAlerts.map((alert, i: number) => (
                            <div key={i} className="flex flex-col p-4 rounded-lg bg-editorial-bg border border-editorial-border group">
                                <div className="flex justify-between items-center mb-2">
                                    <div className="flex items-center gap-2">
                                        <Badge variant="outline" className="bg-incorrect/10 text-incorrect border-incorrect/20 uppercase tracking-widest text-[10px]">
                                            Short Prop
                                        </Badge>
                                        <Link href={`/player/${encodeURIComponent(slugify(alert.player_name))}`} className="font-bold text-ink hover:text-accent-editorial hover:underline transition-colors">{alert.player_name}</Link>
                                    </div>
                                    <span className="text-xs font-mono text-ink-3">{alert.team}</span>
                                </div>
                                <p className="text-sm text-ink-2">
                                    {alert.issue}
                                </p>
                                <div className="mt-3 text-xs text-incorrect font-mono">
                                    Alpha Window: Open (Public consensus unadjusted)
                                </div>
                            </div>
                        ))}
                    </CardContent>
                </Card>

                {/* Model Variance Heatmap (Placeholder) */}
                 <Card className="bg-editorial-card border-editorial-border shadow-lg flex items-center justify-center p-12 text-center h-[500px]">
                    <div>
                        <Activity className="h-16 w-16 text-incorrect/20 mx-auto mb-4" />
                        <CardTitle className="text-2xl font-bold mb-2">Predictive Variance Heatmap</CardTitle>
                        <p className="text-ink-2">Market-Making data visualizations are incoming for Sprint 10.</p>
                    </div>
                </Card>
            </div>
        </main>
    );
}
