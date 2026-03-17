"use client";

import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { TrendingDown, TrendingUp, AlertTriangle, ShieldCheck, Activity, Target, Satellite, Radar } from "lucide-react";
import { Button } from "@/components/ui/button";

const DISLOCATIONS = [
    {
        id: "watson",
        name: "Deshaun Watson",
        team: "CLE",
        image: "deshaun_watson.jpg",
        prediction: "CRITICAL SELL",
        metric: "-$42.5M",
        color: "text-rose-500",
        bg: "bg-rose-500/10",
        border: "border-rose-500/30",
        gradient: "from-rose-600/20 to-transparent",
        icon: TrendingDown,
        insight: "Efficiency gap expanding. Structurally untradable."
    },
    {
        id: "miller",
        name: "Von Miller",
        team: "BUF",
        image: "von_miller.jpg",
        prediction: "LIQUIDATE",
        metric: "-$14.2M",
        color: "text-orange-500",
        bg: "bg-orange-500/10",
        border: "border-orange-500/30",
        gradient: "from-orange-600/20 to-transparent",
        icon: AlertTriangle,
        insight: "Age curve acceleration detected in pass rush win rate."
    },
    {
        id: "wilson",
        name: "Russell Wilson",
        team: "DEN",
        image: "russell_wilson.jpg",
        prediction: "TOXIC ASSET",
        metric: "-$85.0M",
        color: "text-red-600",
        bg: "bg-red-600/10",
        border: "border-red-600/30",
        gradient: "from-red-600/20 to-transparent",
        icon: TrendingDown,
        insight: "Historic dead cap realization predicted."
    },
    {
        id: "elliott",
        name: "Ezekiel Elliott",
        team: "DAL",
        image: "ezekiel_elliott.jpg",
        prediction: "UNDERVALUED VALUE",
        metric: "+$4.5M",
        color: "text-emerald-500",
        bg: "bg-emerald-500/10",
        border: "border-emerald-500/30",
        gradient: "from-emerald-600/20 to-transparent",
        icon: TrendingUp,
        insight: "Situational leverage creates surplus value."
    }
];

export function AlphaFeedHero() {
    return (
        <section className="relative w-full pt-32 pb-20 px-6 lg:px-12 bg-black overflow-hidden flex flex-col items-center border-b border-zinc-900">
            {/* Background elements removed for Tufte-approved Data-Ink Ratio maximization */}

            <div className="relative z-10 w-full max-w-7xl mx-auto text-center space-y-8 mb-16">
                <Badge variant="outline" className="bg-emerald-500/10 text-emerald-500 border-emerald-500/30 font-mono tracking-widest uppercase mb-4 py-1 px-4">
                    Intelligence Aggregator & Prediction Engine
                </Badge>
                <h1 className="text-5xl md:text-7xl lg:text-8xl font-black tracking-tighter text-white drop-shadow-lg">
                    Monetize the <span className="text-transparent bg-clip-text bg-gradient-to-r from-emerald-400 to-teal-200">Alpha.</span>
                </h1>
                
                <p className="text-xl text-zinc-400 max-w-3xl mx-auto leading-relaxed font-light">
                    The market is inefficient. We synthesize real-time news telemetry, on-field performance metrics, and salary cap constraints to identify asset dislocation <span className="text-emerald-400 font-medium">before market consensus</span>.
                </p>

                {/* Upcoming Pipeline Teaser */}
                <div className="flex flex-col sm:flex-row items-center justify-center gap-4 mt-8 pt-8 border-t border-zinc-800/80">
                    <div className="flex items-center gap-2 text-sm font-mono text-zinc-500 px-4 py-2 bg-zinc-900/50 rounded-lg border border-zinc-800">
                        <Radar className="w-4 h-4 text-amber-500" />
                        <span>IN DEVELOPMENT: </span>
                        <span className="text-zinc-300 font-semibold">The Pundit Index</span>
                        <span className="opacity-60 hidden md:inline">- Tracking analytical accuracy of sports media consensus vs. empirical outcomes.</span>
                    </div>
                </div>
            </div>

            {/* Live Ticker / Grid of Market Dislocations */}
            <div className="relative z-10 w-full max-w-[1400px] mx-auto">
                <div className="flex items-center justify-between mb-12 px-2">
                    <h2 className="text-xs font-mono tracking-widest uppercase text-zinc-500 flex items-center gap-3 border-b border-zinc-800 pb-2 flex-1">
                        <Activity className="h-4 w-4 text-zinc-400" /> LIVE MARKET DISLOCATIONS (EMPIRICAL)
                    </h2>
                    <div className="text-[10px] font-mono text-zinc-500 tracking-widest bg-zinc-900 px-3 py-1 ml-4 border border-zinc-800">
                        UPDATED: JUST NOW
                    </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                    {DISLOCATIONS.map((asset) => {
                        const Icon = asset.icon;
                        return (
                            <div key={asset.id} className="flex flex-col border-t-2 border-zinc-900 pt-6 group">
                                <div className="flex items-center gap-2 mb-6">
                                    <Icon className={`w-4 h-4 ${asset.color}`} />
                                    <span className={`text-[10px] font-mono tracking-widest uppercase font-bold ${asset.color}`}>
                                        {asset.prediction}
                                    </span>
                                </div>
                                
                                <div className="space-y-1 mb-8">
                                    <h3 className="text-[10px] tracking-widest uppercase font-mono text-zinc-500">
                                        {asset.team}
                                    </h3>
                                    <h2 className="text-2xl font-light text-zinc-100 tracking-tight">
                                        {asset.name}
                                    </h2>
                                </div>

                                <div className="mt-auto">
                                    <p className="text-[10px] font-mono text-zinc-600 uppercase tracking-widest mb-2 font-bold">Projected Liability</p>
                                    <span className={`text-5xl font-black ${asset.color} tracking-tighter`}>
                                        {asset.metric}
                                    </span>
                                </div>
                                
                                <p className="text-zinc-400 text-sm pt-6 mt-6 border-t border-zinc-900 font-light leading-relaxed">
                                    {asset.insight}
                                </p>
                            </div>
                        )
                    })}
                </div>
            </div>
        </section>
    );
}
