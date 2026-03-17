"use client";

import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { TrendingDown, TrendingUp, AlertTriangle, ShieldCheck, Activity, Target } from "lucide-react";
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
        <section className="relative w-full pt-32 pb-20 px-6 lg:px-12 bg-black overflow-hidden flex flex-col items-center border-b border-white/5">
            {/* Background elements */}
            <div className="absolute top-0 inset-x-0 h-[500px] bg-gradient-to-b from-emerald-900/20 to-transparent pointer-events-none" />
            <div className="absolute inset-0 bg-[url('/grid.svg')] bg-center [mask-image:linear-gradient(180deg,black,rgba(0,0,0,0))] pointer-events-none opacity-20" />
            


            <div className="relative z-10 w-full max-w-7xl mx-auto text-center space-y-8 mb-16">
                <Badge variant="outline" className="bg-emerald-500/10 text-emerald-500 border-emerald-500/30 font-mono tracking-widest uppercase mb-4 py-1 px-4">
                    Intelligence Aggregator & Prediction Market
                </Badge>
                <h1 className="text-5xl md:text-7xl lg:text-8xl font-black tracking-tighter text-white drop-shadow-lg">
                    Monetize the <span className="text-transparent bg-clip-text bg-gradient-to-r from-emerald-400 to-teal-200">Alpha.</span>
                </h1>
                <p className="text-xl text-slate-400 max-w-3xl mx-auto leading-relaxed font-light">
                    We synthesize real-time news, contract telemetry, and machine-learning models to predict the future market value of NFL assets before the consensus catches on.
                </p>
            </div>

            {/* Live Ticker / Grid of Market Dislocations */}
            <div className="relative z-10 w-full max-w-[1400px] mx-auto">
                <div className="flex items-center justify-between mb-6 px-4">
                    <h2 className="text-sm font-mono tracking-widest uppercase text-slate-400 flex items-center gap-2">
                        <Activity className="h-4 w-4 text-emerald-500 animate-pulse" /> Live Market Dislocations
                    </h2>
                    <div className="text-xs font-mono text-emerald-500 bg-emerald-500/10 px-3 py-1 rounded-full border border-emerald-500/20">
                        Updated: Just Now
                    </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                    {DISLOCATIONS.map((asset) => {
                        const Icon = asset.icon;
                        return (
                            <Card key={asset.id} className={`bg-zinc-950 border overflow-hidden relative group hover:border-white/50 transition-all duration-500 ${asset.border}`}>
                                {/* Image Overlay */}
                                <div className="absolute inset-0 z-0">
                                    <div 
                                        className="absolute inset-0 bg-cover bg-center bg-no-repeat transition-transform duration-700 group-hover:scale-110 opacity-40 group-hover:opacity-60"
                                        style={{ backgroundImage: `url('/players/${asset.image}')` }}
                                    />
                                    <div className={`absolute inset-0 bg-gradient-to-t ${asset.gradient} via-black/80 to-black pointer-events-none`} />
                                </div>
                                
                                <CardContent className="p-6 relative z-10 flex flex-col h-[320px] justify-end">
                                    <div className="absolute top-4 left-4 right-4 flex justify-between items-start">
                                        <Badge variant="outline" className={`bg-black/50 backdrop-blur-md ${asset.color} ${asset.border} font-mono text-xs font-bold px-2 py-0.5`}>
                                            <Icon className="w-3 h-3 mr-1" /> {asset.prediction}
                                        </Badge>
                                        <span className={`text-xl font-black ${asset.color} drop-shadow-md`}>
                                            {asset.metric}
                                        </span>
                                    </div>
                                    
                                    <div className="mt-auto space-y-1">
                                        <h3 className="text-sm tracking-widest uppercase font-mono text-slate-400">
                                            {asset.team}
                                        </h3>
                                        <h2 className="text-3xl font-black text-white tracking-tight drop-shadow-md">
                                            {asset.name}
                                        </h2>
                                        <p className="text-slate-300 text-sm italic pt-2 border-t border-white/10 mt-3 font-medium">
                                            "{asset.insight}"
                                        </p>
                                    </div>
                                </CardContent>
                            </Card>
                        )
                    })}
                </div>
            </div>
        </section>
    );
}
