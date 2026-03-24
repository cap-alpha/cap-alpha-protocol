import React from 'react';
import { TimelineEvent } from "@/app/actions";
import { ShieldAlert, Newspaper, FileSignature, TrendingDown } from "lucide-react";
import { ScrollArea } from "@/components/ui/scroll-area";

interface VisualTimelineProps {
    timeline: TimelineEvent[];
}

export function VisualTimeline({ timeline }: VisualTimelineProps) {
    if (!timeline || timeline.length === 0) return null;

    return (
        <div className="flex flex-col w-full font-sans">
            <h3 className="text-[10px] font-bold tracking-widest text-zinc-500 uppercase mb-3 border-b border-zinc-800 pb-1">
                Chronological Asset Events
            </h3>
            <ScrollArea className="h-[600px] w-full pr-4">
                <div className="relative border-l border-zinc-800 ml-2 space-y-6 py-2">
                    {timeline.map((event, idx) => (
                        <div key={idx} className="relative pl-6">
                            {/* Minimalism node point (No heavy colored rings or scaling animations) */}
                            <div className="absolute top-1 left-[-4.5px] w-2 h-2 rounded-full bg-zinc-600 ring-4 ring-zinc-950" />
                            
                            {/* High-density textual presentation */}
                            <div className="flex flex-col gap-0.5 mt-[-2px]">
                                <span className="text-xs font-mono text-zinc-500">
                                    {event.year} 
                                    {event.week ? <span className="text-zinc-600"> W{event.week}</span> : ''}
                                </span>
                                
                                <span className={`text-sm ${event.event_type === 'ML_ALERT' ? 'text-rose-400 font-semibold' : 'text-zinc-300'}`}>
                                    {event.description}
                                </span>

                                {/* Contextual mini-tags */}
                                {event.event_type === 'CONTRACT' && (
                                    <span className="text-[10px] text-zinc-500 mt-1 uppercase tracking-wide flex items-center gap-1">
                                        <FileSignature className="w-3 h-3"/> Cap Catalyst
                                    </span>
                                )}
                                {event.event_type === 'ML_ALERT' && (
                                    <span className="text-[10px] text-rose-500 mt-1 uppercase tracking-wide flex items-center gap-1 opacity-80">
                                        <ShieldAlert className="w-3 h-3"/> Risk Alert
                                    </span>
                                )}
                                {event.event_type === 'MEDIA_CONSENSUS' && (
                                    <span className="text-[10px] text-zinc-500 mt-1 uppercase tracking-wide flex items-center gap-1">
                                        <Newspaper className="w-3 h-3"/> Media Shift
                                    </span>
                                )}
                                {event.event_type === 'PERFORMANCE_DROP' && (
                                    <span className="text-[10px] text-zinc-500 mt-1 uppercase tracking-wide flex items-center gap-1">
                                        <TrendingDown className="w-3 h-3"/> Production Drop
                                    </span>
                                )}
                            </div>
                        </div>
                    ))}
                </div>
            </ScrollArea>
        </div>
    );
}
