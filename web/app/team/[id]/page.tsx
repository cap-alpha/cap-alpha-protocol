import { getTeamRoster, getTeamCapSummary, getTeams, getRosterData } from '@/app/actions';
import { RosterGrid } from '@/components/roster-grid';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { notFound } from 'next/navigation';
import Link from 'next/link';
import { ArrowLeft, ShieldAlert, TrendingUp, MapPin } from 'lucide-react';
import { IntelligenceFeed } from '@/components/intelligence-feed';
import { TEAM_LOGOS, TEAM_NAMES } from '@/lib/team-logos';
import { PositionalSpendingChart } from '@/components/positional-spending-chart';
import { headers, cookies } from 'next/headers';

export const revalidate = 3600; // Cache for 1 hour (ISR)

export default async function TeamPage({ params }: { params: { id: string } }) {
    const teamName = decodeURIComponent(params.id);
    const teamRoster = await getTeamRoster(teamName);
    const allTeamsSummary = await getTeamCapSummary();
    const fullRoster = await getRosterData(); // Still needed for league pos averages
    
    // SP25-2: Instant Personalization Inference
    const headersList = headers();
    const userCity = headersList.get('x-vercel-ip-city');
    const fullTeamName = TEAM_NAMES[teamName] || teamName;
    const isLocalMarket = userCity && fullTeamName.toLowerCase().includes(userCity.toLowerCase());

    const cookieStore = cookies();
    const trackedTeam = cookieStore.get('nfl_tracked_team')?.value;
    const isTrackedTeam = trackedTeam === teamName;

    const teamSummary = allTeamsSummary.find((t) => t.team === teamName);

    if (!teamRoster.length || !teamSummary) {
        notFound();
    }

    // Prepare overview metrics
    const totalCap = teamSummary.total_cap || 0;
    const riskCap = teamSummary.risk_cap || 0;
    const riskPercentage = totalCap > 0 ? (riskCap / totalCap) * 100 : 0;

    // Calculate Positional Spending
    const teamPosSpending: Record<string, number> = {};
    teamRoster.forEach(p => {
        teamPosSpending[p.position] = (teamPosSpending[p.position] || 0) + (p.cap_hit_millions || 0);
    });

    const leaguePosSpendingTotal: Record<string, number> = {};
    const numTeams = allTeamsSummary.length || 32;
    fullRoster.forEach(p => {
        leaguePosSpendingTotal[p.position] = (leaguePosSpendingTotal[p.position] || 0) + (p.cap_hit_millions || 0);
    });
    
    const leaguePosAverage: Record<string, number> = {};
    Object.keys(leaguePosSpendingTotal).forEach(pos => {
        leaguePosAverage[pos] = leaguePosSpendingTotal[pos] / numTeams;
    });

    const positionalChartData = Object.keys(teamPosSpending).map(pos => ({
        position: pos,
        teamSpend: teamPosSpending[pos],
        leagueAvg: leaguePosAverage[pos] || 0
    })).sort((a,b) => b.teamSpend - a.teamSpend);

    return (
        <main className="min-h-[100dvh] bg-background text-foreground p-8">
            <div className="max-w-7xl mx-auto space-y-8">
                {/* Header Section */}
                <div className="flex items-center gap-6 border-b border-border pb-6">
                    <Link href="/dashboard" className="p-2 hover:bg-slate-800 rounded-full transition-colors text-slate-400">
                        <ArrowLeft className="h-6 w-6" />
                    </Link>
                    {TEAM_LOGOS[teamName] && (
                        <div className="w-16 h-16 relative flex-shrink-0 bg-white rounded-full p-2 border border-border shadow-sm">
                            {/* eslint-disable-next-line @next/next/no-img-element */}
                            <img src={TEAM_LOGOS[teamName]} alt={`${teamName} logo`} className="object-contain w-full h-full drop-shadow-sm" />
                        </div>
                    )}
                    <div>
                        <h1 className="text-4xl font-bold tracking-tight uppercase text-emerald-500">
                            {TEAM_NAMES[teamName] || teamName}
                        </h1>
                        <p className="text-muted-foreground uppercase tracking-widest text-sm mt-1">Franchise Intelligence Overview</p>
                    </div>
                </div>

                {/* Instant Personalization Banner */}
                {(isLocalMarket || isTrackedTeam) && (
                    <div className="bg-emerald-500/10 border border-emerald-500/30 p-4 rounded-lg flex items-center gap-3 mb-6 animate-in slide-in-from-top-4 fade-in duration-700">
                        {isLocalMarket ? <MapPin className="h-5 w-5 text-emerald-500" /> : <ShieldAlert className="h-5 w-5 text-emerald-500" />}
                        <div>
                            <p className="font-bold text-sm text-emerald-400">
                                {isLocalMarket ? `${userCity} Local Market Intel` : 'Direct Portfolio Analytics'}
                            </p>
                            <p className="text-xs text-emerald-500/80 mt-0.5">
                                {isLocalMarket 
                                    ? `Displaying deep cap liabilities tailored for the ${userCity} broadcast region.` 
                                    : `High-priority cap alerts enabled. Rendering absolute portfolio risk for your synced franchise.`}
                            </p>
                        </div>
                    </div>
                )}

                {/* Top Metrics Cards */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                    <Card className="bg-zinc-900 border-zinc-800 shadow-sm">
                        <CardHeader className="pb-3 border-b border-zinc-800/50 mb-3">
                            <CardTitle className="text-xs text-zinc-500 font-mono flex items-center gap-2">
                                <span className="uppercase font-bold tracking-widest">Total Cap Liabilities</span>
                            </CardTitle>
                        </CardHeader>
                        <CardContent>
                            <div className="text-3xl font-mono font-bold text-white">
                                {new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(totalCap * 1000000)}
                            </div>
                            <p className="text-[10px] uppercase tracking-wider text-zinc-500 mt-2">Across {teamRoster.length} Active Roster Contracts</p>
                        </CardContent>
                    </Card>

                    <Card className="bg-zinc-900 border-zinc-800 shadow-sm">
                        <CardHeader className="pb-3 border-b border-zinc-800/50 mb-3">
                            <CardTitle className="text-xs text-zinc-500 font-mono flex items-center gap-2">
                                <ShieldAlert className="h-4 w-4 text-rose-500" />
                                <span className="uppercase font-bold tracking-widest text-rose-500">Portfolio Risk</span>
                            </CardTitle>
                        </CardHeader>
                        <CardContent>
                            <div className="text-3xl font-mono font-bold text-rose-500">
                                {riskPercentage.toFixed(1)}%
                            </div>
                            <p className="text-[10px] uppercase tracking-wider text-zinc-500 mt-2">
                                {new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(riskCap * 1000000)} in High-Risk Cap
                            </p>
                        </CardContent>
                    </Card>

                    <Card className="bg-zinc-900 border-zinc-800 shadow-sm">
                        <CardHeader className="pb-3 border-b border-zinc-800/50 mb-3">
                            <CardTitle className="text-xs text-zinc-500 font-mono flex items-center gap-2">
                                <TrendingUp className="h-4 w-4 text-emerald-500" />
                                <span className="uppercase font-bold tracking-widest text-emerald-500">Roster Grade</span>
                            </CardTitle>
                        </CardHeader>
                        <CardContent>
                            <div className="text-3xl font-mono font-bold text-emerald-400">
                                {riskPercentage > 30 ? "C-" : riskPercentage > 15 ? "B" : "A"}
                            </div>
                            <p className="text-[10px] uppercase tracking-wider text-zinc-500 mt-2">Cap Alpha Efficiency Rating</p>
                        </CardContent>
                    </Card>
                </div>

                {/* Team Intelligence & Roster Split view */}
                <div className="grid grid-cols-1 lg:grid-cols-4 gap-8">
                    <div className="lg:col-span-3 space-y-6">
                        <PositionalSpendingChart data={positionalChartData} teamName={teamName} />

                        <Card className="bg-zinc-900 border-zinc-800 h-full shadow-sm">
                            <CardHeader className="border-b border-zinc-800/50 mb-4">
                                <CardTitle className="uppercase font-mono tracking-widest text-sm text-zinc-500">Current Roster Taxonomy</CardTitle>
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
