"use client";

import { Share2, Zap, Trophy, AlertTriangle, Check } from "lucide-react";
import { TEAM_LOGOS } from "@/lib/team-logos";
import { useState } from "react";

export function PersonalityMagnetCard({ player }: { player: any }) {
    const [copied, setCopied] = useState(false);
    // Calculate synthetic visual risk indicators
    const isRisky = (player.risk_cap_millions || 0) > (player.cap_hit_millions || 1) * 0.4;
    const gradient = isRisky 
        ? "bg-gradient-to-br from-rose-950 via-zinc-950 to-black" 
        : "bg-gradient-to-br from-emerald-950 via-zinc-950 to-black";

    const borderColor = isRisky ? "border-rose-500/30" : "border-emerald-500/30";
    const accentColor = isRisky ? "text-rose-500" : "text-emerald-500";

    return (
        <div id="personality-magnet-card" className={`relative overflow-hidden rounded-2xl border ${borderColor} ${gradient} p-8 shadow-2xl`}>
            {/* Ambient Background Glows */}
            <div className={`absolute -top-32 -right-32 w-96 h-96 ${isRisky ? 'bg-rose-500/10' : 'bg-emerald-500/10'} rounded-full blur-3xl`} />
            <div className={`absolute -bottom-32 -left-32 w-96 h-96 ${isRisky ? 'bg-rose-500/5' : 'bg-emerald-500/5'} rounded-full blur-3xl`} />
            
            {/* Header Identity Sector */}
            <div className="relative z-10 flex justify-between items-start">
                <div>
                    <h2 className="text-4xl md:text-5xl font-black uppercase tracking-tighter text-white drop-shadow-lg">
                        {player.player_name}
                    </h2>
                    <div className="flex items-center gap-3 mt-3 text-zinc-400 font-mono tracking-widest text-sm">
                        <span className="bg-zinc-800/80 px-2.5 py-1 rounded text-white">{player.position}</span>
                        <span>•</span>
                        <span className="uppercase">{player.team}</span>
                    </div>
                </div>
                {TEAM_LOGOS[player.team] && (
                    <div className="w-20 h-20 opacity-40 mix-blend-screen drop-shadow-2xl">
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img src={TEAM_LOGOS[player.team]} alt="logo" className="w-full h-full object-contain grayscale brightness-200" />
                    </div>
                )}
            </div>

            {/* Core Alpha Metrics */}
            <div className="relative z-10 mt-14 grid grid-cols-2 gap-6">
                <div className="bg-black/40 backdrop-blur-md rounded-xl p-5 border border-white/5 shadow-inner">
                    <p className="text-[10px] uppercase font-bold tracking-widest text-zinc-500 mb-1.5">Cap Burden</p>
                    <p className="text-4xl font-mono font-bold text-white">
                        ${player.cap_hit_millions?.toFixed(1) || '0.0'}M
                    </p>
                </div>
                <div className="bg-black/40 backdrop-blur-md rounded-xl p-5 border border-white/5 shadow-inner flex flex-col justify-center">
                    <p className="text-[10px] uppercase font-bold tracking-widest text-zinc-500 mb-1.5">Market Thesis</p>
                    <div className="flex items-center gap-2">
                        {isRisky ? <AlertTriangle className="h-6 w-6 text-rose-500 animate-pulse" /> : <Trophy className="h-6 w-6 text-emerald-500" />}
                        <p className={`text-3xl font-black uppercase tracking-tight ${accentColor}`}>
                            {isRisky ? 'TOXIC' : 'ALPHA'}
                        </p>
                    </div>
                </div>
            </div>

            {/* Footer / Social Proof Area */}
            <div className="relative z-10 mt-10 pt-6 border-t border-white/10 flex justify-between items-center">
                <div className="flex items-center gap-2">
                    <Zap className="h-4 w-4 text-amber-500" />
                    <span className="text-xs font-mono text-zinc-400 uppercase tracking-widest">NFL Dead Money • Cap Alpha Intel</span>
                </div>
                <button 
                    onClick={() => {
                        navigator.clipboard.writeText(window.location.href);
                        setCopied(true);
                        setTimeout(() => setCopied(false), 2000);
                    }}
                    className="text-xs bg-white text-black px-5 py-2.5 font-bold uppercase tracking-wider rounded-lg hover:bg-zinc-200 transition-colors flex items-center gap-2 shadow-lg shadow-white/5"
                >
                    {copied ? <Check className="h-4 w-4 text-emerald-600" /> : <Share2 className="h-4 w-4" />} 
                    {copied ? "Copied!" : "Export Card"}
                </button>
            </div>
        </div>
    );
}
