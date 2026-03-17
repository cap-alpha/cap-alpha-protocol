import { getRosterData, getTeamCapSummary, getWarRoomData } from "../../actions";
import { WarRoomDashboard } from "@/components/war-room-dashboard";
import { TradeMachine } from "@/components/trade-machine";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ShieldCheck, TrendingDown } from "lucide-react";
import { MarketTicker } from "@/components/market-ticker";
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
        <main className="min-h-[100dvh] bg-zinc-950 font-sans text-foreground">
            {/* Live Ticker Feed */}
            <MarketTicker totalCap={totalCap} riskCap={totalRiskCap} />
            
            {/* Unified Controls & Blotter */}
            <div className="flex justify-between items-center px-4 py-2 border-b border-white/5 bg-black/40">
                <div className="flex items-center gap-2">
                    <ShieldCheck className="w-5 h-5 text-emerald-500" />
                    <h2 className="text-sm font-mono tracking-widest text-white uppercase flex items-center gap-2">
                        Execution Desk <span className="text-zinc-600">/</span> <span className="text-emerald-500 font-bold">GM</span>
                    </h2>
                </div>
                <PersonaSwitcher />
            </div>

            <div className="p-4 grid gap-4">
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
