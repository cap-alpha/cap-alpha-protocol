import React from "react";
import { getRosterData, getTeamCapSummary } from "./actions";
import { RosterGrid } from "@/components/roster-grid";
import { EfficiencyLandscape } from "@/components/efficiency-landscape";
import { RosterCard } from "@/components/roster-card";
import { TradeMachine } from "@/components/trade-machine";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import PersonaSwitcher from "@/components/persona-switcher";
import { SignInButton, SignedIn, SignedOut, UserButton } from "@clerk/nextjs";
import { Button } from "@/components/ui/button";
import { GlobalSearch } from "@/components/global-search";

export default async function Home({ searchParams }: { searchParams: { search?: string } }) {
    // Get Data (hydrated from JSON with Mock Fallback if needed)
    const rosterData = await getRosterData();
    const teamSummary = await getTeamCapSummary();

    const totalCap = teamSummary.reduce((acc: number, t: any) => acc + t.total_cap, 0);
    const totalRiskCap = teamSummary.reduce((acc: number, t: any) => acc + t.risk_cap, 0);
    const activePlayers = rosterData.length;

    return (
        // Fix: Use 100dvh for mobile viewport consistency
        <main className="min-h-[100dvh] bg-background p-8 font-sans text-foreground">

            {/* Header: The War Room */}
            <header className="mb-8 flex items-center justify-between border-b border-border pb-4">
                <div>
                    <h1 className="text-4xl font-bold tracking-tight text-foreground">CAP ALPHA PROTOCOL // <span className="text-emerald-500">EXECUTIVE SUITE</span></h1>
                    <p className="text-muted-foreground mt-2">Advanced Roster Architecture // v2026.02.14 // <span className="text-emerald-500">BETA ACCESS</span></p>
                </div>
                <div className="flex gap-4 items-center">
                    <SignedOut>
                        <SignInButton mode="modal">
                            <Button variant="outline" className="border-emerald-500 text-emerald-500 hover:bg-emerald-500/10">
                                Sign In
                            </Button>
                        </SignInButton>
                    </SignedOut>
                    <SignedIn>
                        <UserButton afterSignOutUrl="/" />
                    </SignedIn>
                    <GlobalSearch />
                    <PersonaSwitcher />
                    <Badge variant="outline" className="text-lg px-4 py-1 border-emerald-500 text-emerald-500">MARKET: OPEN</Badge>
                    <Badge variant="secondary" className="text-lg px-4 py-1">League Year: 2026</Badge>
                </div>
            </header>

            {/* KPI Cards */}
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4 mb-8">
                <Card className="bg-card border-border">
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-xs font-mono uppercase text-muted-foreground">Total Cap Liabilities</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">
                            {new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(totalCap * 1000000)}
                        </div>
                        <p className="text-[10px] text-muted-foreground uppercase mt-1">
                            Across {teamSummary.length} Teams
                        </p>
                    </CardContent>
                </Card>

                <Card className="bg-card border-border">
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-xs font-mono uppercase text-muted-foreground">Risk Exposure</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold text-rose-500">
                            {new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(totalRiskCap * 1000000)}
                        </div>
                        <p className="text-[10px] text-muted-foreground uppercase mt-1">
                            Assets with Risk Score {'>'} 0.70
                        </p>
                    </CardContent>
                </Card>

                <Card className="bg-card border-border">
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-xs font-mono uppercase text-muted-foreground">Active Contracts</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">{activePlayers}</div>
                        <p className="text-[10px] text-muted-foreground uppercase mt-1">
                            Updated: {new Intl.DateTimeFormat('en-US', { year: 'numeric', month: 'short', day: 'numeric' }).format(new Date())}
                        </p>
                    </CardContent>
                </Card>

                <Card className="bg-card border-border">
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-xs font-mono uppercase text-muted-foreground">Market Efficiency</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold text-emerald-500">94.2%</div>
                        <p className="text-[10px] text-muted-foreground uppercase mt-1">
                            Model R2 Score (Verification)
                        </p>
                    </CardContent>
                </Card>
            </div>

            <section className="mb-8 relative">
                <div className="absolute inset-0 bg-gradient-to-r from-background via-transparent to-background z-10 pointer-events-none" />
                <React.Suspense fallback={
                    <div className="w-full h-[500px] bg-secondary/20 animate-pulse rounded-lg border border-border flex items-center justify-center">
                        <div className="text-muted-foreground font-mono animate-bounce">LOADING MARKET EFFICIENCY DATA...</div>
                    </div>
                }>
                    {/* @ts-ignore */}
                    <EfficiencyLandscape data={rosterData} />
                </React.Suspense>
            </section>

            {/* Main Content: Tabs */}
            <Tabs defaultValue={searchParams?.search ? "grid" : "portfolio"} className="space-y-4">
                <TabsList className="bg-secondary/50 p-1">
                    <TabsTrigger value="portfolio" className="px-8 font-mono uppercase">Portfolio Library</TabsTrigger>
                    <TabsTrigger value="grid" className="px-8 font-mono uppercase">Data Grid</TabsTrigger>
                    <TabsTrigger value="trade" className="px-8 font-mono uppercase">The War Room (Trade)</TabsTrigger>
                </TabsList>

                <TabsContent value="portfolio" className="space-y-4">
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                        {rosterData.slice(0, 24).map((player: any) => (
                            // @ts-ignore
                            <RosterCard key={`${player.player_name}-${player.team}`} player={player} />
                        ))}
                    </div>
                    {rosterData.length > 24 && (
                        <div className="text-center mt-4">
                            <Badge variant="outline">Showing Top 24 of {rosterData.length} Assets</Badge>
                        </div>
                    )}
                </TabsContent>

                <TabsContent value="grid" className="space-y-4">
                    <Card className="bg-card border-border">
                        <CardContent className="p-0">
                            <RosterGrid data={rosterData} initialSearch={searchParams?.search} />
                        </CardContent>
                    </Card>
                </TabsContent>

                <TabsContent value="trade" className="space-y-4">
                    <TradeMachine />
                </TabsContent>
            </Tabs>

        </main>
    );
}

