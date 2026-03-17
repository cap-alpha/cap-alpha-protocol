import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { TrendingDown, TrendingUp, AlertCircle, FileText, ArrowRight, Activity, Zap } from "lucide-react";
import { IntelligenceFeed } from "@/components/intelligence-feed";

const THE_TAPE = [
    {
        id: 1,
        time: "10m ago",
        source: "Schefter",
        content: "BREAKING: Chiefs and WR Rashee Rice have agreed to a 4-year, $110M contract extension with $65M guaranteed.",
        type: "CONTRACT EXTENSION",
        impact: "HIGH"
    },
    {
        id: 2,
        time: "1h ago",
        source: "Pelissero",
        content: "The Dallas Cowboys are restructuring Dak Prescott's deal to clear $12.3M in 2026 cap space, converting base salary into a signing bonus.",
        type: "RESTRUCTURE",
        impact: "MEDIUM"
    },
    {
        id: 3,
        time: "3h ago",
        source: "Rapoport",
        content: "Saints DE Cameron Jordan's medicals came back clean after minor knee scope. Expected to be ready for camp.",
        type: "INJURY UPDATE",
        impact: "LOW"
    }
];

export function GlobalAggregator() {
    return (
        <section className="relative w-full py-24 px-6 lg:px-12 bg-zinc-950 border-y border-white/5">
            <div className="w-full max-w-7xl mx-auto">
                <div className="flex flex-col md:flex-row justify-between items-end mb-12 gap-6">
                    <div>
                        <h2 className="text-3xl md:text-5xl font-black tracking-tight text-white mb-4">
                            The Global Aggregator
                        </h2>
                        <p className="text-xl text-slate-400 max-w-2xl font-light">
                            Unstructured "Tape" from Twitter and media goes in. Structured "Alpha" predicting the cap impact comes out.
                        </p>
                    </div>
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 lg:gap-16">
                    {/* Left Column: The Tape */}
                    <div className="space-y-6">
                        <div className="flex items-center gap-3 border-b border-white/10 pb-4 mb-6">
                            <Activity className="h-6 w-6 text-slate-400" />
                            <h3 className="text-2xl font-bold font-mono tracking-tight text-slate-300 uppercase">
                                The Tape
                            </h3>
                            <span className="text-xs font-mono text-slate-500 ml-auto tracking-widest">(Raw Input)</span>
                        </div>

                        <div className="space-y-4">
                            {THE_TAPE.map((news) => (
                                <Card key={news.id} className="bg-black/40 border-slate-800 hover:border-slate-600 transition-colors">
                                    <CardContent className="p-5 flex gap-4">
                                        <div className="w-12 h-12 shrink-0 rounded-full bg-slate-900 border border-slate-700 flex items-center justify-center text-slate-400 font-mono text-xs">
                                            {news.source.substring(0, 3)}
                                        </div>
                                        <div>
                                            <div className="flex items-center gap-3 mb-2">
                                                <Badge variant="outline" className={`bg-slate-900 text-xs font-mono border-slate-700 ${news.impact === 'HIGH' ? 'text-rose-400' : 'text-slate-400'}`}>
                                                    {news.type}
                                                </Badge>
                                                <span className="text-xs text-slate-500 font-mono">{news.time}</span>
                                            </div>
                                            <p className="text-sm text-slate-300 leading-relaxed font-sans italic">
                                                "{news.content}"
                                            </p>
                                        </div>
                                    </CardContent>
                                </Card>
                            ))}
                        </div>
                    </div>

                    {/* Right Column: The Signal */}
                    <div className="space-y-6 relative">
                        {/* Connecting Arrow for larger screens */}
                        <div className="absolute top-1/2 -left-12 -translate-y-1/2 hidden lg:flex items-center justify-center w-8 h-8 rounded-full bg-emerald-500/20 text-emerald-500 border border-emerald-500/30">
                            <ArrowRight className="w-4 h-4" />
                        </div>

                        <div className="flex items-center gap-3 border-b border-emerald-500/30 pb-4 mb-6">
                            <Zap className="h-6 w-6 text-emerald-500 fill-emerald-500/20" />
                            <h3 className="text-2xl font-bold font-mono tracking-tight text-emerald-400 uppercase">
                                The Signal
                            </h3>
                            <span className="text-xs font-mono text-emerald-500/50 ml-auto tracking-widest">(Model Output)</span>
                        </div>

                        {/* Rendering Intelligence Feeds (The synthesized output) */}
                        <div className="h-full space-y-4">
                            <IntelligenceFeed 
                                playerName="Rashee Rice" 
                                riskScore={88}
                                feedEvents={[
                                    { text: "WR age curve model flags immediate regression risk beginning Year 3 of new extension.", type: "PERFORMANCE DECAY", icon: "TrendingDown", color: "text-rose-500" },
                                    { text: "For The Sharp: Chiefs SB odds marginally decrease; implied win total (11.5) remains static despite $65M commitment.", type: "VEGAS IMPACT", icon: "AlertCircle", color: "text-orange-400" },
                                    { text: "For The Suit: Extension structurally locks Kansas City into significant dead cap hit in 2028 if player is released.", type: "CAP LIABILITY", icon: "FileText", color: "text-blue-400" }
                                ]} 
                            />
                        </div>
                    </div>
                </div>
            </div>
        </section>
    );
}
