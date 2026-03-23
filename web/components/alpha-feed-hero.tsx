"use client";

import { useState, useRef, useEffect } from "react";
import { Badge } from "@/components/ui/badge";
import { TrendingDown, TrendingUp, AlertTriangle, Activity, Radar, X, Newspaper } from "lucide-react";
import Link from "next/link";
import { ImageWithFallback } from "./image-with-fallback";
import { ProvenanceSnapshot } from "./provenance-snapshot";

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
        insight: "Efficiency gap expanding. Structurally untradable.",
        news: [
            "Browns cap liability reaches historic levels, models suggest dead cap acceleration is inevitable.",
            "Offensive efficiency strictly negatively correlated with Watson's snap count in Q4.",
            "Restructure options mathematically exhausted; future guarantees lock in long-term dislocation."
        ]
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
        insight: "Catastrophic guarantee execution trigger imminent.",
        news: [
            "Injury guarantees threaten to execute next week, triggering $23M in unavoidable future liability.",
            "Front office actively exploring benching to preserve organizational optionality.",
            "Production models show output matches replacement-level free agent QB (Value: $4M)."
        ]
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
        insight: "Historic dead cap realization predicted.",
        news: [
            "Denver officially absorbing the largest dead cap charge in NFL history ($85M).",
            "Advanced models signaled velocity decline 18 months prior to public consensus.",
            "Structural roster damage limits free agency optionality for next two cycles."
        ]
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
        insight: "Efficiency metrics collapsed despite volume preservation.",
        news: [
            "Rush Yards Over Expected (RYOE) dropped to career lows despite volume remaining stable.",
            "New Orleans salary cap restructure cycles have pushed critical void year hits into current ledger.",
            "Running back aging curve indicates non-recoverable decay trajectory."
        ]
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
        insight: "Age curve acceleration detected in pass rush win rate.",
        news: [
            "Pass Rush Win Rate (PRWR) plummeted post-injury to bottom 15th percentile.",
            "Buffalo's defensive line efficiency actually improves when asset is off the field geometrically.",
            "Cap savings via Post-June 1 cut far outweigh empirical on-field surplus value."
        ]
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
        insight: "Situational leverage creates point-in-time surplus value.",
        news: [
            "Veteran minimum contract guarantees hyper-efficient short-yardage situational conversions.",
            "Return to original scheme masks athletic decay; asset utilization optimized perfectly.",
            "Zero dead-cap liability makes this a pure asymmetric upside holding."
        ]
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
        insight: "Pre-season variance is mispriced by current consensus.",
        news: [
            "Media sentiment heavily indexes Achilles injury, ignoring intact throwing mechanics.",
            "Mathematical leverage of supporting cast (Wilson, Hall) artificially props up floor.",
            "Restructured contract actually provides elite APY flexibility for 2025 cap window."
        ]
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
        insight: "Recurring soft-tissue history heavily correlated with cap liability.",
        news: [
            "Coverage metrics still elite, but availability coefficient wipes out surplus value entirely.",
            "Dead cap prorations limit New Orleans' ability to pivot defensively.",
            "Market trade value significantly lower than internal ledger valuation."
        ]
    }
];

export function AlphaFeedHero() {
    const scrollRef = useRef<HTMLDivElement>(null);
    const [isHovered, setIsHovered] = useState(false);
    const [expandedCardId, setExpandedCardId] = useState<string | null>(null);

    // Auto-scroll logic utilizing requestAnimationFrame for buttery smooth manual/auto scroll merging
    useEffect(() => {
        let animationFrameId: number;
        
        const scroll = () => {
            if (scrollRef.current && !isHovered && !expandedCardId) {
                scrollRef.current.scrollLeft += 1;
                // Seamless infinite loop check
                if (scrollRef.current.scrollLeft >= scrollRef.current.scrollWidth / 2) {
                    scrollRef.current.scrollLeft = 0;
                }
            }
            animationFrameId = requestAnimationFrame(scroll);
        };

        animationFrameId = requestAnimationFrame(scroll);
        return () => cancelAnimationFrame(animationFrameId);
    }, [isHovered, expandedCardId]);

    // Create a duplicated array for seamless infinite scrolling
    const marqueeItems = [...DISLOCATIONS, ...DISLOCATIONS];

    return (
        <section className="relative w-full pt-32 pb-20 px-6 lg:px-12 bg-black overflow-hidden flex flex-col items-center">
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

                <div className="flex flex-col sm:flex-row items-center justify-center gap-4 mt-8 pt-8 border-t border-zinc-800/80">
                    <div className="flex items-center gap-2 text-sm font-mono text-zinc-500 px-4 py-2 bg-black rounded-lg border border-zinc-900">
                        <Radar className="w-4 h-4 text-emerald-500 opacity-80" />
                        <span>IN DEVELOPMENT: </span>
                        <span className="text-zinc-300 font-semibold text-emerald-500/90">The Pundit Index Tracker</span>
                        <span className="opacity-60 hidden md:inline">- Tracking accuracy of sports media vs empirical outcomes.</span>
                    </div>
                </div>
            </div>

            <div className="relative z-10 w-full mb-12">
                <div className="flex items-center justify-between mb-8 max-w-7xl mx-auto px-4">
                    <h2 className="text-xs font-mono tracking-widest uppercase text-zinc-500 flex items-center gap-3 border-b border-zinc-800 pb-2 flex-1">
                        <Activity className="h-4 w-4 text-zinc-400" /> LIVE MARKET DISLOCATIONS (EMPIRICAL)
                        {expandedCardId && <span className="text-emerald-500 ml-2 animate-pulse">[ PAUSED FOR INTEL ]</span>}
                    </h2>
                    <div className="text-[10px] font-mono text-zinc-500 tracking-widest bg-zinc-900 px-3 py-1 ml-4 border border-zinc-800">
                        UPDATED: JUST NOW
                    </div>
                </div>

                {/* Interactive Carousel */}
                <div 
                    ref={scrollRef}
                    onMouseEnter={() => setIsHovered(true)}
                    onMouseLeave={() => setIsHovered(false)}
                    onTouchStart={() => setIsHovered(true)}
                    onTouchEnd={() => setTimeout(() => setIsHovered(false), 2000)}
                    className="flex overflow-x-auto gap-6 pb-12 px-4 hide-scrollbars w-full max-w-[100vw] snap-x snap-mandatory cursor-grab active:cursor-grabbing"
                    style={{ WebkitOverflowScrolling: 'touch' }}
                >
                    {marqueeItems.map((asset, i) => {
                        const Icon = asset.icon;
                        const isExpanded = expandedCardId === `${asset.id}-${i}`;
                        const slug = asset.name.toLowerCase().replace(/ \s/g, '').replace(/\s+/g, '-');
                        
                        return (
                            <div 
                                key={`${asset.id}-${i}`} 
                                className={`relative group flex flex-col shrink-0 snap-center transition-all duration-500 rounded-xl ring-1 ring-white/10 hover:ring-emerald-500/50 hover:shadow-2xl hover:shadow-emerald-500/10 ${isExpanded ? 'w-[85vw] md:w-[600px] h-[600px] bg-zinc-950 scale-[1.02] z-20' : 'w-[85vw] md:w-[400px] h-[450px] overflow-hidden'}`}
                                onClick={() => !isExpanded && setExpandedCardId(`${asset.id}-${i}`)}
                            >
                                
                                {/* Background Image */}
                                <div className="absolute inset-0 z-0">
                                    <ImageWithFallback
                                        src={`/players/${asset.image}`}
                                        alt={asset.name}
                                        fallbackText={asset.team}
                                        className={`absolute inset-0 w-full h-full object-cover object-top transition-all duration-700 ${isExpanded ? 'opacity-20 grayscale' : 'group-hover:scale-105 opacity-40 group-hover:opacity-60'}`}
                                    />
                                    {/* Gradient to ensure text readability */}
                                    <div className={`absolute inset-0 bg-gradient-to-t pointer-events-none ${isExpanded ? 'from-black via-black/95 to-black/60' : 'from-black via-black/80 to-transparent'}`} />
                                </div>

                                {/* Content Layer */}
                                <div className="relative z-10 p-8 flex flex-col h-full flex-1 w-full justify-between">
                                    
                                    {/* Header Section */}
                                    <div>
                                        <div className="flex items-center justify-between gap-2 mb-8">
                                            <div className="flex items-center gap-2">
                                                <div className="w-6 h-6 rounded-full bg-zinc-900 flex items-center justify-center border border-zinc-800">
                                                    <Icon className={`w-3 h-3 ${asset.color}`} />
                                                </div>
                                                <span className={`text-[10px] font-mono tracking-widest uppercase font-bold ${asset.color}`}>
                                                    {asset.prediction}
                                                </span>
                                            </div>
                                            {isExpanded && (
                                                <button onClick={(e) => { e.stopPropagation(); setExpandedCardId(null); }} className="p-2 hover:bg-zinc-800 rounded-full text-zinc-400 hover:text-white transition-colors">
                                                    <X className="w-5 h-5" />
                                                </button>
                                            )}
                                        </div>
                                        
                                        <div className="space-y-1 mb-8">
                                            <h3 className="text-xs tracking-widest uppercase font-mono text-zinc-500 font-semibold drop-shadow-md">
                                                {asset.team}
                                            </h3>
                                            <h2 className="text-3xl font-light text-zinc-100 tracking-tight drop-shadow-xl">
                                                {asset.name}
                                            </h2>
                                        </div>
                                    </div>

                                    {/* Middle Section: Metrics or News */}
                                    {isExpanded ? (
                                        <div className="flex-1 overflow-y-auto pr-2 scrollbar-thin scrollbar-thumb-zinc-700 scrollbar-track-transparent animate-in fade-in duration-300">
                                            <div className="space-y-4 pt-4 border-t border-zinc-800">
                                                <h4 className="text-xs font-mono tracking-widest text-emerald-500 uppercase flex items-center gap-2">
                                                    <Newspaper className="w-4 h-4" /> Supporting Intelligence
                                                </h4>
                                                {asset.news.map((n, idx) => {
                                                    const isNegative = asset.prediction.includes('SELL') || asset.prediction.includes('TOXIC') || asset.prediction.includes('LIQUIDATE');
                                                    return (
                                                        <ProvenanceSnapshot
                                                            key={idx}
                                                            source="ALPHA PROTOCOL // INTEL SENSOR"
                                                            content={n}
                                                            sentiment={isNegative ? 0.3 : 0.8}
                                                            timestamp={new Date(Date.now() - (idx * 3600000)).toISOString()} // Staggered mock timestamps
                                                            snapshotType="DISPATCH_LOG"
                                                        />
                                                    );
                                                })}
                                                <div className="pt-2 flex justify-between gap-4">
                                                    <Link href={`/player/${slug}`} className="flex-1 bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-500 border border-emerald-500/30 font-mono tracking-widest text-xs py-3 rounded text-center transition-colors">
                                                        VIEW AUDIT LEDGER
                                                    </Link>
                                                </div>
                                            </div>
                                        </div>
                                    ) : (
                                        <div className="mt-auto">
                                            <p className="text-[10px] font-mono text-zinc-500 uppercase tracking-widest mb-2 font-bold flex justify-between">
                                                <span>Projected Liability</span>
                                                <span className="text-emerald-500 opacity-0 group-hover:opacity-100 transition-opacity">CLICK FOR INTEL</span>
                                            </p>
                                            <span className={`text-6xl font-black ${asset.color} tracking-tighter drop-shadow-2xl`}>
                                                {asset.metric}
                                            </span>
                                            <p className="text-zinc-400 text-sm pt-6 mt-6 border-t border-zinc-800/50 font-light leading-relaxed h-[80px]">
                                                {asset.insight}
                                            </p>
                                        </div>
                                    )}
                                </div>
                            </div>
                        )
                    })}
                </div>
            </div>

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
