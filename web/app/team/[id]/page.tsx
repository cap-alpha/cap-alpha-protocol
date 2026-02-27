import { getRosterData, getTeamCapSummary, getTeams } from '@/app/actions';
import { RosterGrid } from '@/components/roster-grid';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { notFound } from 'next/navigation';
import Link from 'next/link';
import { ArrowLeft, ShieldAlert, TrendingUp } from 'lucide-react';
import { IntelligenceFeed } from '@/components/intelligence-feed';

export async function generateStaticParams() {
    const teams = await getTeams();
    return teams.map((team) => ({
        id: encodeURIComponent(team),
    }));
}

export default async function TeamPage({ params }: { params: { id: string } }) {
    const teamName = decodeURIComponent(params.id);
    const rosterData = await getRosterData();
    const allTeamsSummary = await getTeamCapSummary();

    // Filter roster for this specific team
    const teamRoster = rosterData.filter((p) => p.team === teamName);
    const teamSummary = allTeamsSummary.find((t) => t.team === teamName);

    if (!teamRoster.length || !teamSummary) {
        notFound();
    }

    // Prepare overview metrics
    const totalCap = teamSummary.total_cap || 0;
    const riskCap = teamSummary.risk_cap || 0;
    const riskPercentage = totalCap > 0 ? (riskCap / totalCap) * 100 : 0;

    return (
        <main className="min-h-[100dvh] bg-background text-foreground p-8">
            <div className="max-w-7xl mx-auto space-y-8">
                {/* Header Section */}
                <div className="flex items-center gap-4 border-b border-border pb-6">
                    <Link href="/dashboard" className="p-2 hover:bg-slate-800 rounded-full transition-colors text-slate-400">
                        <ArrowLeft className="h-6 w-6" />
                    </Link>
                    <div>
                        <h1 className="text-4xl font-bold tracking-tight uppercase text-emerald-500">
                            {teamName}
                        </h1>
                        <p className="text-muted-foreground uppercase tracking-widest text-sm mt-1">Franchise Intelligence Overview</p>
                    </div>
                </div>

                {/* Top Metrics Cards */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                    <Card className="bg-card border-transparent shadow-none">
                        <CardHeader className="pb-2">
                            <CardTitle className="text-xs text-muted-foreground font-mono">
                                <span className="uppercase font-bold tracking-wider">Total Cap Liabilities</span>
                            </CardTitle>
                        </CardHeader>
                        <CardContent>
                            <div className="text-3xl font-black text-white">
                                {new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(totalCap * 1000000)}
                            </div>
                            <p className="text-xs text-slate-500 mt-1">Across {teamRoster.length} Active Roster Contracts</p>
                        </CardContent>
                    </Card>

                    <Card className="bg-card border-transparent shadow-none">
                        <CardHeader className="pb-2">
                            <CardTitle className="text-xs text-muted-foreground font-mono flex items-center gap-2">
                                <ShieldAlert className="h-4 w-4 text-rose-500" />
                                <span className="uppercase font-bold tracking-wider text-rose-500">Portfolio Risk</span>
                            </CardTitle>
                        </CardHeader>
                        <CardContent>
                            <div className="text-3xl font-black text-rose-500">
                                {riskPercentage.toFixed(1)}%
                            </div>
                            <p className="text-xs text-slate-500 mt-1">
                                {new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(riskCap * 1000000)} in High-Risk Cap
                            </p>
                        </CardContent>
                    </Card>

                    <Card className="bg-card border-transparent shadow-none">
                        <CardHeader className="pb-2">
                            <CardTitle className="text-xs text-muted-foreground font-mono flex items-center gap-2">
                                <TrendingUp className="h-4 w-4 text-emerald-500" />
                                <span className="uppercase font-bold tracking-wider text-emerald-500">Roster Grade</span>
                            </CardTitle>
                        </CardHeader>
                        <CardContent>
                            <div className="text-3xl font-black text-emerald-400">
                                {riskPercentage > 30 ? "C-" : riskPercentage > 15 ? "B" : "A"}
                            </div>
                            <p className="text-xs text-slate-500 mt-1">Cap Alpha Efficiency Rating</p>
                        </CardContent>
                    </Card>
                </div>

                {/* Team Intelligence & Roster Split view */}
                <div className="grid grid-cols-1 lg:grid-cols-4 gap-8">
                    <div className="lg:col-span-3 space-y-6">
                        <Card className="bg-card border-border h-full">
                            <CardHeader>
                                <CardTitle className="uppercase font-mono tracking-widest text-sm text-slate-400">Current Roster Taxonomy</CardTitle>
                            </CardHeader>
                            <CardContent className="p-0">
                                <RosterGrid data={teamRoster} initialSearch="" />
                            </CardContent>
                        </Card>
                    </div>

                    <div className="lg:col-span-1 h-[600px] lg:h-auto">
                        {/* RAG Risk Explainer (Use Case A placeholder) */}
                        <IntelligenceFeed playerName={`${teamName} Franchise`} riskScore={riskPercentage / 100} />
                    </div>
                </div>
            </div>
        </main>
    );
}
