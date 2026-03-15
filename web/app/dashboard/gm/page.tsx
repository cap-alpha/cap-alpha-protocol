import React from "react";
import { getRosterData, getTeamCapSummary, getWarRoomData } from "../../actions";
import { WarRoomDashboard } from "@/components/war-room-dashboard";
import { TradeMachine } from "@/components/trade-machine";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ShieldCheck, TrendingDown } from "lucide-react";
import { GlobalSearch } from "@/components/global-search";
import PersonaSwitcher from "@/components/persona-switcher";

export default async function GMDashboard() {
    const [rosterData, teamSummary, warRoomData] = await Promise.all([
        getRosterData(),
        getTeamCapSummary(),
        getWarRoomData()
    ]);

    const totalCap = teamSummary.reduce((acc: number, t: any) => acc + t.total_cap, 0);
    const totalRiskCap = teamSummary.reduce((acc: number, t: any) => acc + t.risk_cap, 0);

    return (
        <main className="min-h-[100dvh] bg-background p-8 font-sans text-foreground">
            {/* Context Header */}
            <header className="mb-8 flex flex-col md:flex-row md:items-center justify-between border-b border-border pb-4 gap-4">
                <div className="flex items-center gap-4">
                    <div className="p-3 rounded-lg bg-blue-500/10 border border-blue-500/30">
                        <ShieldCheck className="w-8 h-8 text-blue-400" />
                    </div>
                    <div>
                        <h1 className="text-3xl font-bold tracking-tight text-foreground">
                            Front Office <span className="text-blue-500">Suite</span>
                        </h1>
                        <p className="text-muted-foreground mt-1 text-sm flex items-center gap-2">
                            Total Liabilities: {new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(totalCap * 1000000)}
                            <span className="text-muted-foreground/50">|</span>
                            Risk Exposure: <span className="text-rose-500 font-bold">{new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(totalRiskCap * 1000000)}</span>
                        </p>
                    </div>
                </div>
                <div className="flex gap-4 items-center">
                    <GlobalSearch />
                    <PersonaSwitcher />
                </div>
            </header>

            <div className="grid gap-8">
                {/* War Room Feed */}
                <WarRoomDashboard data={warRoomData} />

                {/* Adversarial Trade Engine */}
                <Card className="bg-card border-border shadow-lg">
                    <CardHeader className="border-b border-border/50 pb-6 mb-6">
                        <div className="flex items-center gap-2">
                            <TrendingDown className="h-5 w-5 text-blue-500" />
                            <CardTitle className="text-xl">Adversarial Trade Engine</CardTitle>
                        </div>
                        <CardDescription>
                            Simulate multi-team swaps and assess post-trade cap liquidity across the league.
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                         <TradeMachine />
                    </CardContent>
                </Card>
            </div>
        </main>
    );
}
