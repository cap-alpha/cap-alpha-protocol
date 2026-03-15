import React from "react";
import { getRosterData, getTeamCapSummary } from "../../actions";
import { RosterCard } from "@/components/roster-card";
import { TeamCard } from "@/components/team-card";
import { User, Flame } from "lucide-react";
import { GlobalSearch } from "@/components/global-search";
import PersonaSwitcher from "@/components/persona-switcher";

export default async function FanDashboard() {
    const [rosterData, teamSummary] = await Promise.all([
        getRosterData(),
        getTeamCapSummary()
    ]);

    // Fans care about the best & worst grades
    const topPerformers = rosterData.filter((p: any) => p.risk_score < 0.2).slice(0, 8);
    const bustCandidates = rosterData.filter((p: any) => p.risk_score >= 0.8).slice(0, 8);

    return (
        <main className="min-h-[100dvh] bg-background p-8 font-sans text-foreground">
            {/* Context Header */}
            <header className="mb-8 flex flex-col md:flex-row md:items-center justify-between border-b border-border pb-4 gap-4">
                <div className="flex items-center gap-4">
                    <div className="p-3 rounded-lg bg-amber-500/10 border border-amber-500/30">
                        <User className="w-8 h-8 text-amber-500" />
                    </div>
                    <div>
                        <h1 className="text-3xl font-bold tracking-tight text-foreground">
                            Armchair <span className="text-amber-500">GM</span>
                        </h1>
                        <p className="text-muted-foreground mt-1 text-sm">
                            Unbiased Contract Grades & Franchise Scores
                        </p>
                    </div>
                </div>
                <div className="flex gap-4 items-center">
                    <GlobalSearch />
                    <PersonaSwitcher />
                </div>
            </header>

            <div className="space-y-12">
                {/* Team Directory (Visual) */}
                <section>
                    <h2 className="text-2xl font-black mb-6 flex items-center gap-2">
                        <Flame className="w-6 h-6 text-amber-500" />
                        Franchise Power Rankings
                    </h2>
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                        {teamSummary.slice(0, 8).map((team: any) => (
                            <TeamCard key={team.team} team={team} />
                        ))}
                    </div>
                </section>

                {/* The "A+" Grades */}
                <section>
                    <h2 className="text-2xl font-black mb-6 text-emerald-400">
                        Elite Surplus Contracts
                    </h2>
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                        {topPerformers.map((player: any) => (
                            <RosterCard key={`${player.player_name}-${player.team}`} player={{...player, grade: 'A+'}} />
                        ))}
                    </div>
                </section>

                {/* The "F-" Grades */}
                <section>
                    <h2 className="text-2xl font-black mb-6 text-rose-500">
                        Bust Watch (Toxic Assets)
                    </h2>
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                        {bustCandidates.map((player: any) => (
                            <RosterCard key={`${player.player_name}-${player.team}`} player={{...player, grade: 'F-'}} />
                        ))}
                    </div>
                </section>
            </div>
        </main>
    );
}
