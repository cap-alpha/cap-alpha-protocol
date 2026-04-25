import React from 'react';
import { TimelineEvent } from "@/app/actions";
import { CheckCircle2, FileSignature, MessageSquareQuote, XCircle } from "lucide-react";
import { ScrollArea } from "@/components/ui/scroll-area";

interface VisualTimelineProps {
    timeline: TimelineEvent[];
}

const EVENT_META: Record<string, { label: string; color: string; Icon: React.ElementType }> = {
    CONTRACT:   { label: 'Cap Catalyst',        color: 'text-sky-400',     Icon: FileSignature },
    PREDICTION: { label: 'Pundit Prediction',   color: 'text-amber-400',   Icon: MessageSquareQuote },
    RESOLUTION: { label: 'Prediction Resolved', color: 'text-emerald-400', Icon: CheckCircle2 },
};

export function VisualTimeline({ timeline }: VisualTimelineProps) {
    if (!timeline || timeline.length === 0) return null;

    return (
        <div className="flex flex-col w-full font-sans">
            <h3 className="text-[10px] font-bold tracking-widest text-zinc-500 uppercase mb-3 border-b border-zinc-800 pb-1">
                Chronological Asset Events
            </h3>
            <ScrollArea className="h-[600px] w-full pr-4">
                <div className="relative border-l border-zinc-800 ml-2 space-y-6 py-2">
                    {timeline.map((event, idx) => {
                        const meta = EVENT_META[event.event_type] ?? { label: event.event_type, color: 'text-zinc-400', Icon: XCircle };
                        const { Icon } = meta;
                        return (
                            <div key={idx} className="relative pl-6">
                                <div className="absolute top-1 left-[-4.5px] w-2 h-2 rounded-full bg-zinc-600 ring-4 ring-zinc-950" />
                                <div className="flex flex-col gap-0.5 mt-[-2px]">
                                    <span className="text-xs font-mono text-zinc-500">
                                        {event.event_date ?? event.event_year}
                                    </span>
                                    <span className="text-sm font-medium text-zinc-200">
                                        {event.title}
                                    </span>
                                    <span className="text-xs text-zinc-400 line-clamp-3">
                                        {event.description}
                                    </span>
                                    <span className={`text-[10px] ${meta.color} mt-1 uppercase tracking-wide flex items-center gap-1`}>
                                        <Icon className="w-3 h-3" /> {meta.label}
                                        {event.source_url && (
                                            <a href={event.source_url} target="_blank" rel="noopener noreferrer"
                                               className="ml-2 text-zinc-500 hover:text-zinc-300 normal-case tracking-normal">
                                                source →
                                            </a>
                                        )}
                                    </span>
                                </div>
                            </div>
                        );
                    })}
                </div>
            </ScrollArea>
        </div>
    );
}
