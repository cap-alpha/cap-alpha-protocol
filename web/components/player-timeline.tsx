import React, { useState, useRef } from 'react';
import { TimelineEvent } from "@/app/actions";
import { ShieldAlert, Newspaper, FileSignature, TrendingDown, Clock, ZoomIn, ZoomOut } from "lucide-react";

interface PlayerTimelineProps {
    timeline: TimelineEvent[];
}

export function PlayerTimeline({ timeline }: PlayerTimelineProps) {
    const [zoomLevel, setZoomLevel] = useState(2); // 0: Min, 1: Med, 2: Max
    const touchRef = useRef({ initialDistance: 0 });

    if (!timeline || timeline.length === 0) {
        return (
            <div className="flex flex-col items-center justify-center p-8 text-center border border-dashed border-zinc-800 rounded-lg bg-zinc-900/50">
                <Clock className="w-8 h-8 text-zinc-600 mb-3" />
                <h4 className="text-sm font-semibold text-zinc-300">Awaiting Telemetry</h4>
                <p className="text-xs text-zinc-500 mt-1 max-w-[250px]">
                    No critical timeline events or chronological intelligence available for this asset.
                </p>
            </div>
        );
    }

    const getIcon = (type: TimelineEvent['event_type']) => {
        switch (type) {
            case 'ML_ALERT': return <ShieldAlert className="w-5 h-5 text-rose-500" />;
            case 'MEDIA_CONSENSUS': return <Newspaper className="w-5 h-5 text-amber-500" />;
            case 'CONTRACT': return <FileSignature className="w-5 h-5 text-emerald-500" />;
            case 'PERFORMANCE_DROP': return <TrendingDown className="w-5 h-5 text-zinc-400" />;
            default: return <div className="w-3 h-3 rounded-full bg-zinc-600" />;
        }
    };

    const getBgColor = (type: TimelineEvent['event_type']) => {
        switch (type) {
            case 'ML_ALERT': return "bg-rose-500/10 border-rose-500/30 shadow-[0_0_15px_rgba(244,63,94,0.15)] ring-1 ring-rose-500/20";
            case 'MEDIA_CONSENSUS': return "bg-amber-500/10 border-amber-500/30 ring-1 ring-amber-500/20";
            case 'CONTRACT': return "bg-emerald-500/10 border-emerald-500/30 ring-1 ring-emerald-500/20";
            default: return "bg-zinc-800 border-zinc-700 ring-1 ring-zinc-700/50";
        }
    };

    // Calculate lead times between ML Alerts and Media Consensus in the same year
    const enrichedTimeline = timeline.map((event, index, arr) => {
        let leadTimeWeeks: number | null = null;
        if (event.event_type === 'MEDIA_CONSENSUS') {
            const previousAlert = arr
                .slice(0, index)
                .reverse()
                .find(e => e.event_type === 'ML_ALERT' && e.year === event.year);
            if (previousAlert && previousAlert.week !== undefined && event.week !== undefined) {
                leadTimeWeeks = event.week - previousAlert.week;
            }
        }
        return { ...event, leadTimeWeeks };
    });

    const getDistance = (touches: React.TouchList) => {
        const dx = touches[0].clientX - touches[1].clientX;
        const dy = touches[0].clientY - touches[1].clientY;
        return Math.sqrt(dx * dx + dy * dy);
    };

    const handleTouchStart = (e: React.TouchEvent) => {
        if (e.touches.length === 2) {
            e.preventDefault(); // Prevent native browser zoom if possible inside this container
            touchRef.current.initialDistance = getDistance(e.touches);
        }
    };

    const handleTouchMove = (e: React.TouchEvent) => {
        if (e.touches.length === 2 && touchRef.current.initialDistance > 0) {
            e.preventDefault();
            const currentDistance = getDistance(e.touches);
            const delta = currentDistance - touchRef.current.initialDistance;
            
            // Zoom threshold (e.g. 60px)
            if (delta > 60 && zoomLevel < 2) {
                setZoomLevel(prev => prev + 1);
                touchRef.current.initialDistance = currentDistance; 
            } else if (delta < -60 && zoomLevel > 0) {
                setZoomLevel(prev => prev - 1);
                touchRef.current.initialDistance = currentDistance;
            }
        }
    };

    const handleTouchEnd = () => {
        touchRef.current.initialDistance = 0;
    };

    return (
        <div className="relative w-full">
            {/* Semantic Zoom Controls for Desktop accessibility */}
            <div className="flex justify-end mb-4">
                <div className="flex items-center space-x-2 bg-zinc-900 border border-zinc-800 rounded-lg p-1 shadow-sm">
                    <button 
                        onClick={() => setZoomLevel(Math.max(0, zoomLevel - 1))}
                        disabled={zoomLevel === 0}
                        className="p-1.5 text-zinc-400 hover:text-white disabled:opacity-30 disabled:hover:text-zinc-400 transition-colors rounded-md hover:bg-zinc-800"
                        title="Zoom Out (Less Detail)"
                    >
                        <ZoomOut className="w-4 h-4" />
                    </button>
                    <div className="flex space-x-1 px-2">
                        {[0, 1, 2].map(level => (
                            <div key={level} className={`w-1.5 h-1.5 rounded-full ${zoomLevel >= level ? 'bg-emerald-500' : 'bg-zinc-700'}`} />
                        ))}
                    </div>
                    <button 
                        onClick={() => setZoomLevel(Math.min(2, zoomLevel + 1))}
                        disabled={zoomLevel === 2}
                        className="p-1.5 text-zinc-400 hover:text-white disabled:opacity-30 disabled:hover:text-zinc-400 transition-colors rounded-md hover:bg-zinc-800"
                        title="Zoom In (More Detail)"
                    >
                        <ZoomIn className="w-4 h-4" />
                    </button>
                </div>
            </div>

            <div 
                className="relative pl-8 space-y-6 mt-4 before:absolute before:inset-0 before:ml-4 before:-translate-x-px md:before:mx-auto md:before:translate-x-0 before:h-full before:w-0.5 before:bg-gradient-to-b before:from-transparent before:via-zinc-800 before:to-transparent select-none"
                onTouchStart={handleTouchStart}
                onTouchMove={handleTouchMove}
                onTouchEnd={handleTouchEnd}
            >
                {enrichedTimeline.map((item, idx) => (
                    <div key={idx} className={`relative flex items-center justify-between md:justify-normal md:odd:flex-row-reverse group transition-all duration-300 ${zoomLevel === 0 ? 'py-1' : 'py-2'}`}>
                        
                        {/* The Icon Node */}
                        <div className={`flex items-center justify-center rounded-full border shadow shrink-0 md:order-1 md:group-odd:-translate-x-1/2 md:group-even:translate-x-1/2 ${getBgColor(item.event_type)} bg-zinc-950 z-10 absolute left-[-1.25rem] md:static md:left-auto transition-all ${zoomLevel === 0 ? 'w-6 h-6' : 'w-10 h-10'}`}>
                            {zoomLevel > 0 ? getIcon(item.event_type) : <div className="w-2 h-2 rounded-full bg-current opacity-70" />}
                        </div>
                        
                        {/* The Content Card */}
                        <div className={`w-[calc(100%-2.5rem)] md:w-[calc(50%-2.5rem)] rounded-xl border border-zinc-800/50 bg-zinc-900/50 backdrop-blur-sm shadow shadow-black/5 hover:border-zinc-700 transition-all ml-4 md:ml-0 overflow-hidden ${zoomLevel === 0 ? 'p-2' : 'p-4'}`}>
                            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2">
                                {/* Title (Visible in Level 1 and 2, but minimal in 0) */}
                                {zoomLevel > 0 && (
                                    <h3 className="text-sm font-semibold text-zinc-200">
                                        {item.event_type === 'ML_ALERT' && 'Alpha Predictive Alert'}
                                        {item.event_type === 'MEDIA_CONSENSUS' && 'Media Market Shift'}
                                        {item.event_type === 'CONTRACT' && 'Financial Benchmark'}
                                        {item.event_type === 'PERFORMANCE_DROP' && 'Empirical Decline'}
                                    </h3>
                                )}
                                
                                <div className={`px-2 rounded bg-zinc-950/50 border border-zinc-800 flex items-center gap-2 ${zoomLevel === 0 ? 'py-0.5' : 'py-1 mb-2 sm:mb-0'}`}>
                                    <span className="font-mono text-xs font-bold text-emerald-500">
                                        {item.year}
                                    </span>
                                    {((item.week && item.week > 0) || zoomLevel === 0) && (
                                        <span className="font-mono text-xs text-zinc-500 border-l border-zinc-800 pl-2">
                                            WK {item.week || '-'}
                                        </span>
                                    )}
                                </div>
                            </div>
                            
                            {/* Description (Visible in Level 2 only) */}
                            {zoomLevel === 2 && (
                                <div className="animate-in fade-in slide-in-from-top-1">
                                    <p className="text-sm text-zinc-400 leading-relaxed mt-2">
                                        {item.description}
                                    </p>

                                    {/* Return on Investment Bracket */}
                                    {item.leadTimeWeeks !== null && item.leadTimeWeeks > 0 && (
                                        <div className="mt-4 p-3 rounded-lg bg-emerald-500/5 border border-emerald-500/20 relative overflow-hidden">
                                            <div className="absolute top-0 right-0 w-32 h-32 bg-emerald-500/10 rounded-full blur-2xl -mr-16 -mt-16 pointer-events-none" />
                                            <div className="flex flex-col relative z-10">
                                                <span className="text-[10px] font-bold text-emerald-500 uppercase tracking-widest mb-1.5 flex items-center gap-1.5">
                                                    <TrendingDown className="w-3 h-3" />
                                                    Alpha Ledger Receipt
                                                </span>
                                                <span className="text-sm text-emerald-50 font-medium">
                                                    Identified critical degradation <strong className="text-emerald-400">{item.leadTimeWeeks} weeks</strong> before market consensus.
                                                </span>
                                                <span className="text-xs text-emerald-500/70 mt-1 italic">
                                                    *Trading/restructure window successfully validated via temporal backtest.
                                                </span>
                                            </div>
                                        </div>
                                    )}
                                </div>
                            )}
                        </div>
                    </div>
                ))}
            </div>
            <p className="text-center text-xs text-zinc-600 mt-6 font-mono tracking-widest uppercase md:hidden flex justify-center items-center gap-2 opacity-50">
                <ZoomIn className="w-3 h-3" /> Pinch to Semantic Zoom
            </p>
        </div>
    );
}
