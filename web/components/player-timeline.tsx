import { TimelineEvent } from "@/app/actions";
import { ShieldAlert, Newspaper, FileSignature, TrendingDown, Clock } from "lucide-react";

interface PlayerTimelineProps {
    timeline: TimelineEvent[];
}

export function PlayerTimeline({ timeline }: PlayerTimelineProps) {
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
        <div className="relative pl-8 space-y-6 mt-4 before:absolute before:inset-0 before:ml-4 before:-translate-x-px md:before:mx-auto md:before:translate-x-0 before:h-full before:w-0.5 before:bg-gradient-to-b before:from-transparent before:via-zinc-800 before:to-transparent">
            {enrichedTimeline.map((item, idx) => (
                <div key={idx} className="relative flex items-center justify-between md:justify-normal md:odd:flex-row-reverse group is-active">
                    
                    {/* The Icon Node */}
                    <div className={`flex items-center justify-center w-10 h-10 rounded-full border shadow shrink-0 md:order-1 md:group-odd:-translate-x-1/2 md:group-even:translate-x-1/2 ${getBgColor(item.event_type)} bg-zinc-950 z-10 absolute left-[-1.25rem] md:static md:left-auto`}>
                        {getIcon(item.event_type)}
                    </div>
                    
                    {/* The Content Card */}
                    <div className="w-[calc(100%-2.5rem)] md:w-[calc(50%-2.5rem)] p-4 rounded-xl border border-zinc-800/50 bg-zinc-900/50 backdrop-blur-sm shadow shadow-black/5 hover:border-zinc-700 transition-colors ml-4 md:ml-0">
                        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 mb-2">
                            <h3 className="text-sm font-semibold text-zinc-200">
                                {item.event_type === 'ML_ALERT' && 'Alpha Predictive Alert'}
                                {item.event_type === 'MEDIA_CONSENSUS' && 'Media Market Shift'}
                                {item.event_type === 'CONTRACT' && 'Financial Benchmark'}
                                {item.event_type === 'PERFORMANCE_DROP' && 'Empirical Decline'}
                            </h3>
                            <div className="px-2 py-1 rounded bg-zinc-950/50 border border-zinc-800 flex items-center gap-2">
                                <span className="font-mono text-xs font-bold text-emerald-500">
                                    {item.year}
                                </span>
                                {item.week > 0 && (
                                    <span className="font-mono text-xs text-zinc-500 border-l border-zinc-800 pl-2">
                                        WK {item.week}
                                    </span>
                                )}
                            </div>
                        </div>
                        
                        <p className="text-sm text-zinc-400 leading-relaxed">
                            {item.description}
                        </p>

                        {/* Return on Investment Bracket (Lead Time / Proof of Alpha) */}
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
                </div>
            ))}
        </div>
    );
}
