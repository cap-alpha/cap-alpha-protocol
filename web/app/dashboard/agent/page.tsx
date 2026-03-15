import React from "react";
import { getRosterData, getTeamCapSummary } from "../../actions";
import { RosterGrid } from "@/components/roster-grid";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Briefcase, DollarSign } from "lucide-react";
import { GlobalSearch } from "@/components/global-search";
import PersonaSwitcher from "@/components/persona-switcher";

export default async function AgentDashboard({ searchParams }: { searchParams: { search?: string } }) {
    const [rosterData, teamSummary] = await Promise.all([
        getRosterData(),
        getTeamCapSummary()
    ]);

    // Sorting by Cap Space (Ascending / Descending depending on how the data is structured)
    const capLeaders = [...teamSummary].sort((a, b) => b.total_cap - a.total_cap).slice(0, 5);

    return (
        <main className="min-h-[100dvh] bg-background p-8 font-sans text-foreground">
            {/* Context Header */}
            <header className="mb-8 flex flex-col md:flex-row md:items-center justify-between border-b border-border pb-4 gap-4">
                <div className="flex items-center gap-4">
                    <div className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/30">
                        <Briefcase className="w-8 h-8 text-emerald-400" />
                    </div>
                    <div>
                        <h1 className="text-3xl font-bold tracking-tight text-foreground">
                            Agent <span className="text-emerald-500">Suite</span>
                        </h1>
                        <p className="text-muted-foreground mt-1 text-sm">
                            Surplus Value Maximization & Cap Targeting
                        </p>
                    </div>
                </div>
                <div className="flex gap-4 items-center">
                    <GlobalSearch />
                    <PersonaSwitcher />
                </div>
            </header>

            <div className="grid grid-cols-1 lg:grid-cols-4 gap-8">
                {/* Cap Targets Side Panel */}
                <div className="lg:col-span-1 space-y-6">
                    <Card className="bg-card border-border shadow-md">
                        <CardHeader className="pb-3 border-b border-border/50">
                            <div className="flex items-center gap-2">
                                <DollarSign className="w-5 h-5 text-emerald-500" />
                                <CardTitle className="text-lg">Target Accounts</CardTitle>
                            </div>
                            <CardDescription>Highest Liability Offloaders</CardDescription>
                        </CardHeader>
                        <CardContent className="pt-4 space-y-4">
                            {capLeaders.map((team: any, i) => (
                                <div key={team.team} className="flex justify-between items-center text-sm">
                                    <span className="font-bold text-slate-300">{team.team}</span>
                                    <span className="font-mono text-emerald-400">
                                        {new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(team.total_cap * 1000000)}
                                    </span>
                                </div>
                            ))}
                        </CardContent>
                    </Card>
                </div>

                {/* Main Client Value Board */}
                <div className="lg:col-span-3">
                    <Card className="bg-card border-border shadow-lg h-full">
                        <CardHeader className="pb-4">
                            <CardTitle className="text-xl text-slate-200">Surplus Value Leaderboard</CardTitle>
                            <CardDescription>Identify clients generating alpha vs market rates.</CardDescription>
                        </CardHeader>
                        <CardContent className="p-0">
                            {/* Filtering logic defaults to only showing players with risk < 0.5 for agents finding 'good' clients */}
                            <RosterGrid data={rosterData} initialSearch={searchParams?.search} />
                        </CardContent>
                    </Card>
                </div>
            </div>
        </main>
    );
}
