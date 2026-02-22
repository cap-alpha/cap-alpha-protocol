import React from "react";
import { getRosterData, getTeamCapSummary } from "../actions";
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
import { HeroSearch } from "@/components/hero-search";
import { ProofOfAlphaCarousel } from "@/components/proof-of-alpha-carousel";

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
                    <div className="flex flex-col items-end text-xs font-mono text-muted-foreground ml-2">
                        <span className="text-emerald-500">MARKET: OPEN</span>
                        <span>YEAR: 2026</span>
                    </div>
                </div>
            </header>

            {/* KPI Cards */}
            <div className="grid gap-8 md:grid-cols-2 lg:grid-cols-4 mb-8 py-4 border-b border-border/50">
                <div className="flex flex-col space-y-1">
                    <div className="text-xs font-mono uppercase text-muted-foreground tracking-wider">Total Cap Liabilities</div>
                    <div className="text-3xl font-black tracking-tight">
                        {new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(totalCap * 1000000)}
                    </div>
                    <div className="text-[10px] text-muted-foreground uppercase mt-1">Across {teamSummary.length} Teams</div>
                </div>

                <div className="flex flex-col space-y-1">
                    <div className="text-xs font-mono uppercase text-muted-foreground tracking-wider">Risk Exposure</div>
                    <div className="text-3xl font-black text-rose-500 tracking-tight">
                        {new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(totalRiskCap * 1000000)}
                    </div>
                    <div className="text-[10px] text-muted-foreground uppercase mt-1">Assets with Risk Score {'>'} 0.70</div>
                </div>

                <div className="flex flex-col space-y-1">
                    <div className="text-xs font-mono uppercase text-muted-foreground tracking-wider">Active Contracts</div>
                    <div className="text-3xl font-black tracking-tight">{activePlayers}</div>
                    <div className="text-[10px] text-muted-foreground uppercase mt-1">
                        Updated: {new Intl.DateTimeFormat('en-US', { year: 'numeric', month: 'short', day: 'numeric' }).format(new Date())}
                    </div>
                </div>

                <div className="flex flex-col space-y-1">
                    <div className="text-xs font-mono uppercase text-muted-foreground tracking-wider">Market Efficiency</div>
                    <div className="text-3xl font-black text-emerald-500 tracking-tight">94.2%</div>
                    <div className="text-[10px] text-muted-foreground uppercase mt-1">Model R2 Score (Verification)</div>
                </div>
            </div>

            <ProofOfAlphaCarousel />

            <section className="mb-8 relative">
                <div className="absolute inset-0 bg-gradient-to-r from-background via-transparent to-background z-10 pointer-events-none" />
                <React.Suspense fallback={
                    <div className="w-full h-[500px] bg-secondary/20 animate-pulse rounded-lg border border-border flex items-center justify-center flex-col gap-4">
                        <div className="text-emerald-500 font-mono text-sm uppercase tracking-widest animate-pulse duration-1000">System Initializing...</div>
                        <div className="text-muted-foreground font-mono animate-bounce uppercase">SYNCING LEAGUE-WIDE CONTRACT LEDGER...</div>
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
                    <SignedIn>
                        <TradeMachine />
                    </SignedIn>
                    <SignedOut>
                        <Card className="bg-card border-emerald-500/50 p-12 text-center rounded-lg shadow-lg relative overflow-hidden">
                            <div className="absolute top-0 inset-x-0 h-1 bg-gradient-to-r from-transparent via-emerald-500 to-transparent" />
                            <CardTitle className="text-2xl font-bold mb-4 font-mono text-emerald-500">PREMIUM INTELLIGENCE REQUIRED</CardTitle>
                            <p className="text-muted-foreground mb-8 text-lg max-w-xl mx-auto">
                                The Adversarial Trade Engine is restricted to authenticated Executives. Sign in to simulate multi-team swaps and assess post-trade cap liquidity.
                            </p>
                            <SignInButton mode="modal">
                                <Button className="bg-emerald-500 hover:bg-emerald-600 text-white text-lg px-8 py-6 rounded-md uppercase tracking-wider font-bold">
                                    Unlock The War Room
                                </Button>
                            </SignInButton>
                        </Card>
                    </SignedOut>
                </TabsContent>
            </Tabs>

        </main>
    );
}

