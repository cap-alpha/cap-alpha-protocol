import React from 'react';
import { TimelineEvent } from "@/app/actions";
import { ShieldAlert, Newspaper, FileSignature, TrendingDown, Clock } from "lucide-react";
import { ScrollArea, ScrollBar } from "@/components/ui/scroll-area";
import { Card } from "@/components/ui/card";

interface VisualTimelineProps {
    timeline: TimelineEvent[];
}

export function VisualTimeline({ timeline }: VisualTimelineProps) {
    if (!timeline || timeline.length === 0) return null;

    const getIcon = (type: TimelineEvent['event_type']) => {
        switch (type) {
            case 'ML_ALERT': return <ShieldAlert className="w-4 h-4 text-rose-500" />;
            case 'MEDIA_CONSENSUS': return <Newspaper className="w-4 h-4 text-amber-500" />;
            case 'CONTRACT': return <FileSignature className="w-4 h-4 text-emerald-500" />;
            case 'PERFORMANCE_DROP': return <TrendingDown className="w-4 h-4 text-zinc-400" />;
            default: return <div className="w-2 h-2 rounded-full bg-zinc-600" />;
        }
    };

    const getBgColor = (type: TimelineEvent['event_type']) => {
        switch (type) {
            case 'ML_ALERT': return "bg-rose-500/10 border-rose-500/30 text-rose-400 ring-rose-500/20";
            case 'MEDIA_CONSENSUS': return "bg-amber-500/10 border-amber-500/30 text-amber-400 ring-amber-500/20";
            case 'CONTRACT': return "bg-emerald-500/10 border-emerald-500/30 text-emerald-400 ring-emerald-500/20";
            default: return "bg-zinc-800 border-zinc-700 text-zinc-300 ring-zinc-700/50";
        }
    };

    return (
        <Card className="bg-zinc-950 border-zinc-800 mb-6 p-4 overflow-hidden relative shadow-xl">
            <h3 className="text-xs font-mono font-bold tracking-widest text-zinc-500 uppercase mb-4 flex items-center gap-2">
                <Clock className="w-4 h-4" /> Chronological Asset Events
            </h3>
            <ScrollArea className="w-full whitespace-nowrap pb-6 pt-2">
                <div className="flex w-max min-w-full items-center relative py-4 px-2">
                    {/* The horizontal connecting line */}
                    <div className="absolute top-1/2 left-0 right-0 h-0.5 bg-gradient-to-r from-transparent via-zinc-800 to-transparent -translate-y-1/2 z-0" />
                    
                    {timeline.map((event, idx) => (
                        <div key={idx} className="relative z-10 flex flex-col items-center justify-start group shrink-0 w-[220px] px-4 cursor-pointer">
                            {/* Year / Week Badge (Top) */}
                            <div className={`mb-3 px-2 py-0.5 rounded text-[10px] font-mono border ${getBgColor(event.event_type)} opacity-80 group-hover:opacity-100 transition-opacity bg-zinc-950 shadow-sm`}>
                                {event.year} {event.week ? `W${event.week}` : ''}
                            </div>
                            
                            {/* Node Point */}
                            <div className={`w-8 h-8 rounded-full border-2 flex items-center justify-center bg-zinc-950 ${getBgColor(event.event_type)} group-hover:scale-110 transition-transform ring-4 shadow-lg`}>
                                {getIcon(event.event_type)}
                            </div>
                            
                            {/* Description (Bottom) */}
                            <div className="mt-4 text-center w-full whitespace-normal h-[60px] flex flex-col items-center">
                                <p className="text-xs font-semibold text-zinc-300 line-clamp-2 leading-relaxed">
                                    {event.description}
                                </p>
                                {event.event_type === 'CONTRACT' && (
                                    <p className="text-[9px] text-emerald-500 font-mono tracking-widest mt-1.5 uppercase">Cap Catalyst</p>
                                )}
                                {event.event_type === 'ML_ALERT' && (
                                    <p className="text-[9px] text-rose-500 font-mono tracking-widest mt-1.5 uppercase">Risk Alert</p>
                                )}
                            </div>
                        </div>
                    ))}
                </div>
                <ScrollBar orientation="horizontal" className="bg-zinc-800/80 hover:bg-zinc-700 transition-colors" />
            </ScrollArea>
        </Card>
    );
}
