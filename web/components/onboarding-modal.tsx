"use client";

import { useEffect, useState } from "react";
import { useTeam } from "./team-context";
import { getTeams } from "@/app/actions";
import { TEAM_LOGOS, TEAM_NAMES } from "@/lib/team-logos";
import { Loader2, CheckCircle2 } from "lucide-react";
import { cn } from "@/lib/utils";

// All 32 teams — fallback when BigQuery is unavailable
const ALL_TEAMS = Object.keys(TEAM_LOGOS).sort();

function SimpleModal({ open, children }: { open: boolean; children: React.ReactNode }) {
    if (!open) return null;
    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-zinc-950/90 backdrop-blur-md animate-in fade-in duration-300">
            <div className="w-full max-w-4xl rounded-xl border border-white/10 bg-zinc-900 p-8 shadow-2xl animate-in zoom-in-95 duration-300 mx-4">
                {children}
            </div>
        </div>
    );
}

export default function OnboardingModal() {
    const { activeTeam, setActiveTeam, isLoading, isTeamSelectorOpen, setTeamSelectorOpen } = useTeam();
    const [teams, setTeams] = useState<string[]>([]);
    const [loadingTeams, setLoadingTeams] = useState(true);

    useEffect(() => {
        const loadTeams = async () => {
            try {
                const t = await getTeams();
                // Fall back to full 32-team list if BigQuery returns nothing
                setTeams(t.length > 0 ? t : ALL_TEAMS);
            } catch (e) {
                console.error("Failed to load teams", e);
                setTeams(ALL_TEAMS);
            } finally {
                setLoadingTeams(false);
            }
        };
        loadTeams();
    }, []);

    if (!isTeamSelectorOpen) return null;

    return (
        <SimpleModal open={isTeamSelectorOpen}>
            <div className="space-y-8 relative">
                <button
                    onClick={() => setTeamSelectorOpen(false)}
                    className="absolute -top-4 -right-4 text-zinc-400 hover:text-white transition-colors"
                >
                    ✕ Close
                </button>
                <div className="space-y-3 text-center">
                    <h2 className="text-3xl font-bold tracking-tight text-white">
                        {activeTeam ? "Change Franchise" : "Select Your Franchise"}
                    </h2>
                    <p className="text-zinc-400 text-lg">
                        Configure the War Room. Your selection personalizes the Cap Alpha intelligence suite.
                    </p>
                </div>

                {loadingTeams ? (
                    <div className="flex justify-center py-20">
                        <Loader2 className="h-10 w-10 animate-spin text-emerald-500" />
                    </div>
                ) : (
                    <div className="grid grid-cols-4 sm:grid-cols-6 lg:grid-cols-8 gap-4 max-h-[60vh] overflow-y-auto p-2 scrollbar-thin scrollbar-thumb-zinc-700 scrollbar-track-transparent">
                        {teams.map((team) => (
                            <TeamButton
                                key={team}
                                team={team}
                                isActive={activeTeam === team}
                                onSelect={() => {
                                    setActiveTeam(team);
                                    setTeamSelectorOpen(false);
                                }}
                            />
                        ))}
                    </div>
                )}

                <div className="flex justify-center pt-2">
                    <p className="text-xs text-zinc-600 uppercase tracking-widest">
                        Cap Alpha Protocol • v2.0
                    </p>
                </div>
            </div>
        </SimpleModal>
    );
}

function TeamButton({
    team,
    isActive,
    onSelect,
}: {
    team: string;
    isActive: boolean;
    onSelect: () => void;
}) {
    const [imgError, setImgError] = useState(false);
    const logoUrl = TEAM_LOGOS[team];
    const teamName = TEAM_NAMES[team] || team;
    const showLogo = logoUrl && !imgError;

    return (
        <button
            onClick={onSelect}
            className={cn(
                "group relative flex flex-col items-center justify-center p-4 rounded-xl border transition-all duration-200",
                "hover:bg-zinc-800 hover:border-emerald-500/50 hover:scale-105 hover:shadow-lg hover:shadow-emerald-500/10",
                isActive
                    ? "border-emerald-500 bg-emerald-500/10 ring-1 ring-emerald-500"
                    : "border-white/5 bg-zinc-900/50 grayscale hover:grayscale-0"
            )}
        >
            <div className="relative w-12 h-12 mb-3">
                {showLogo ? (
                    /* eslint-disable-next-line @next/next/no-img-element */
                    <img
                        src={logoUrl}
                        alt={teamName}
                        className="w-full h-full object-contain drop-shadow-md"
                        onError={() => setImgError(true)}
                        loading="lazy"
                    />
                ) : (
                    <div className="w-full h-full flex items-center justify-center bg-zinc-800 rounded-full font-bold text-white text-xs">
                        {team}
                    </div>
                )}
                {isActive && (
                    <div className="absolute -top-2 -right-2 bg-emerald-500 rounded-full p-1 text-black shadow-sm">
                        <CheckCircle2 className="w-3 h-3" />
                    </div>
                )}
            </div>
            <span
                className={cn(
                    "text-xs font-medium text-center truncate w-full",
                    isActive ? "text-emerald-400" : "text-zinc-500 group-hover:text-zinc-300"
                )}
            >
                {team}
            </span>
        </button>
    );
}
