import { TimelineEvent } from "@/app/actions";
import { ShieldAlert, Newspaper, FileSignature, TrendingDown } from "lucide-react";
import { Fragment } from "react";

interface PlayerTimelineProps {
    timeline: TimelineEvent[];
}

export function PlayerTimeline({ timeline }: PlayerTimelineProps) {
    if (!timeline || timeline.length === 0) {
        return (
            <div className="text-zinc-500 text-sm text-center py-8">
                No chronological events available for this asset.
            </div>
        );
    }

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
            case 'ML_ALERT': return "bg-rose-500/10 border-rose-500/30";
            case 'MEDIA_CONSENSUS': return "bg-amber-500/10 border-amber-500/30";
            case 'CONTRACT': return "bg-emerald-500/10 border-emerald-500/30";
            default: return "bg-zinc-800 border-zinc-700";
        }
    };

    // Calculate lead times between ML Alerts and Media Consensus in the same year
    const enrichedTimeline = timeline.map((event, index, arr) => {
        let leadTimeWeeks = null;
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

    return (
        <div className="relative pl-6 space-y-8 mt-2">
            {/* The Vertical Line */}
            <div className="absolute left-3 top-2 bottom-2 w-px bg-zinc-800" />

            {enrichedTimeline.map((item, idx) => (
                <div key={idx} className="relative">
                    {/* The Node */}
                    <div className={`absolute -left-6 w-6 h-6 rounded-full border flex items-center justify-center bg-zinc-950 ${getBgColor(item.event_type)}`}>
                        {getIcon(item.event_type)}
                    </div>

                    <div className="flex flex-col ml-4">
                        <div className="flex items-center gap-2 mb-1">
                            <span className="text-xs font-mono font-bold text-zinc-400">
                                {item.year} {item.week > 0 ? `Wk ${item.week}` : ''}
                                {item.date_of_event ? ` • ${item.date_of_event}` : ''}
                            </span>
                        </div>
                        <div className="text-sm text-zinc-300 leading-relaxed">
                            {item.description}
                        </div>

                        {/* Return on Investment Bracket (Lead Time) */}
                        {item.leadTimeWeeks !== null && item.leadTimeWeeks > 0 && (
                            <div className="mt-4 p-3 rounded bg-emerald-500/10 border border-emerald-500/20 flex flex-col items-start shadow-sm shadow-emerald-900/10">
                                <span className="text-xs font-bold text-emerald-400 uppercase tracking-widest mb-1">Alpha ROI Realized</span>
                                <span className="text-sm text-emerald-300">
                                    Model identified asset failure <strong>{item.leadTimeWeeks} weeks</strong> before mainstream public consensus. 
                                    (Trading Window Closed)
                                </span>
                            </div>
                        )}
                    </div>
                </div>
            ))}
        </div>
    );
}
