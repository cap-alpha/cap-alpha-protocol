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
        icon: TrendingDown,
        insight: "Efficiency gap expanding. Structurally untradable."
    },
    {
        id: "jones",
        name: "Daniel Jones",
        team: "NYG",
        image: "daniel_jones.jpg",
        prediction: "LIQUIDATE",
        metric: "-$38.0M",
        color: "text-orange-500",
        icon: AlertTriangle,
        insight: "Catastrophic guarantee execution trigger imminent."
    },
    {
        id: "wilson",
        name: "Russell Wilson",
        team: "DEN",
        image: "russell_wilson.jpg",
        prediction: "TOXIC ASSET",
        metric: "-$85.0M",
        color: "text-red-600",
        icon: TrendingDown,
        insight: "Historic dead cap realization predicted."
    },
    {
        id: "kamara",
        name: "Alvin Kamara",
        team: "NO",
        image: "alvin_kamara.jpg",
        prediction: "CRITICAL SELL",
        metric: "-$18.5M",
        color: "text-rose-500",
        icon: TrendingDown,
        insight: "Efficiency metrics collapsed despite volume preservation."
    },
    {
        id: "miller",
        name: "Von Miller",
        team: "BUF",
        image: "von_miller.jpg",
        prediction: "LIQUIDATE",
        metric: "-$14.2M",
        color: "text-orange-500",
        icon: AlertTriangle,
        insight: "Age curve acceleration detected in pass rush win rate."
    },
    {
        id: "elliott",
        name: "Ezekiel Elliott",
        team: "DAL",
        image: "ezekiel_elliott.jpg",
        prediction: "VALUE SURPLUS",
        metric: "+$4.5M",
        color: "text-emerald-500",
        icon: TrendingUp,
        insight: "Situational leverage creates point-in-time surplus value."
    },
    {
        id: "rodgers",
        name: "Aaron Rodgers",
        team: "NYJ",
        image: "aaron_rodgers.jpg",
        prediction: "UNDERVALUED",
        metric: "+$12.0M",
        color: "text-emerald-500",
        icon: TrendingUp,
        insight: "Pre-season variance is mispriced by current consensus."
    },
    {
        id: "lattimore",
        name: "Marshon Lattimore",
        team: "NO",
        image: "marshon_lattimore.jpg",
        prediction: "TOXIC ASSET",
        metric: "-$15.2M",
        color: "text-red-600",
        icon: AlertTriangle,
        insight: "Recurring soft-tissue history heavily correlated with cap liability."
    }
];

export function AlphaFeedHero() {
    return (
        <section className="relative w-full pt-32 pb-20 px-6 lg:px-12 bg-black overflow-hidden flex flex-col items-center">
            {/* Minimalist void background (Tufte Purge: Grid removed) */}

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
                    <div className="flex items-center gap-2 text-sm font-mono text-zinc-500 px-4 py-2 bg-black rounded-lg border border-zinc-900">
                        <Radar className="w-4 h-4 text-emerald-500 opacity-80" />
                        <span>IN DEVELOPMENT: </span>
                        <span className="text-zinc-300 font-semibold text-emerald-500/90">The Pundit Index Tracker</span>
                        <span className="opacity-60 hidden md:inline">- Tracking accuracy of sports media vs empirical outcomes.</span>
                    </div>
                </div>
            </div>

            {/* Live Ticker / Carousel of Market Dislocations */}
            <div className="relative z-10 w-full mb-12">
                <div className="flex items-center justify-between mb-8 max-w-7xl mx-auto px-4">
                    <h2 className="text-xs font-mono tracking-widest uppercase text-zinc-500 flex items-center gap-3 border-b border-zinc-800 pb-2 flex-1">
                        <Activity className="h-4 w-4 text-zinc-400" /> LIVE MARKET DISLOCATIONS (EMPIRICAL)
                    </h2>
                    <div className="text-[10px] font-mono text-zinc-500 tracking-widest bg-zinc-900 px-3 py-1 ml-4 border border-zinc-800">
                        UPDATED: JUST NOW
                    </div>
                </div>

                {/* Horizontal Scroll Carousel */}
                <div className="flex overflow-x-auto gap-6 pb-12 px-4 md:px-12 snap-x snap-mandatory hide-scrollbars w-full max-w-[100vw]">
                    {DISLOCATIONS.map((asset) => {
                        const Icon = asset.icon;
                        return (
                            <div key={asset.id} className="relative group flex flex-col shrink-0 snap-center w-[85vw] md:w-[400px] h-[450px] overflow-hidden transition-all duration-500">
                                
                                {/* Dramatic Image Background Overlay */}
                                <div className="absolute inset-0 z-0">
                                    <div 
                                        className="absolute inset-0 bg-cover bg-top transition-all duration-700 group-hover:scale-105 opacity-[0.15] group-hover:opacity-40 grayscale group-hover:grayscale-0"
                                        style={{ backgroundImage: `url('/players/${asset.image}')` }}
                                    />
                                    {/* Gradient to ensure text readability */}
                                    <div className="absolute inset-0 bg-gradient-to-t from-black via-black/90 to-black/30 pointer-events-none" />
                                </div>

                                <div className="relative z-10 p-8 flex flex-col h-full flex-1">
                                    <div className="flex items-center gap-2 mb-8">
                                        <div className="w-6 h-6 rounded-full bg-zinc-900 flex items-center justify-center border border-zinc-800">
                                            <Icon className={`w-3 h-3 ${asset.color}`} />
                                        </div>
                                        <span className={`text-[10px] font-mono tracking-widest uppercase font-bold ${asset.color}`}>
                                            {asset.prediction}
                                        </span>
                                    </div>
                                    
                                    <div className="space-y-1 mb-8">
                                        <h3 className="text-xs tracking-widest uppercase font-mono text-zinc-500 font-semibold drop-shadow-md">
                                            {asset.team}
                                        </h3>
                                        <h2 className="text-3xl font-light text-zinc-100 tracking-tight drop-shadow-xl">
                                            {asset.name}
                                        </h2>
                                    </div>

                                    <div className="mt-auto">
                                        <p className="text-[10px] font-mono text-zinc-500 uppercase tracking-widest mb-2 font-bold">Projected Liability</p>
                                        <span className={`text-6xl font-black ${asset.color} tracking-tighter drop-shadow-2xl`}>
                                            {asset.metric}
                                        </span>
                                    </div>
                                    
                                    <p className="text-zinc-400 text-sm pt-6 mt-6 border-t border-zinc-800/50 font-light leading-relaxed h-[80px]">
                                        {asset.insight}
                                    </p>
                                </div>
                            </div>
                        )
                    })}
                </div>
            </div>

            {/* Hide Scrollbar CSS Injection */}
            <style dangerouslySetInnerHTML={{__html: `
                .hide-scrollbars::-webkit-scrollbar {
                    display: none;
                }
                .hide-scrollbars {
                    -ms-overflow-style: none;
                    scrollbar-width: none;
                }
            `}} />
        </section>
    );
}
