import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { TrendingDown, TrendingUp, AlertCircle, FileText, ArrowRight, Activity, Zap, CheckCircle2, XCircle } from "lucide-react";
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
        <section className="relative w-full py-24 px-6 lg:px-12 bg-black">
            <div className="w-full max-w-7xl mx-auto">
                <div className="flex flex-col md:flex-row justify-between items-end mb-12 gap-6">
                    <div>
                        <h2 className="text-3xl md:text-5xl font-black tracking-tight text-white mb-4">
                            The Global Aggregator
                        </h2>
                        <p className="text-xl text-zinc-400 max-w-2xl font-light">
                            Unstructured &quot;Tape&quot; from Twitter and media goes in. Structured &quot;Alpha&quot; predicting the cap impact comes out.
                        </p>
                    </div>
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 lg:gap-16">
                    {/* Left Column: The Tape */}
                    <div className="space-y-6">
                        <div className="flex items-center gap-3 border-b border-zinc-900 pb-6 mb-6">
                            <Activity className="h-6 w-6 text-slate-400" />
                            <h3 className="text-2xl font-bold font-mono tracking-tight text-slate-300 uppercase">
                                The Tape
                            </h3>
                            <span className="text-xs font-mono text-slate-500 ml-auto tracking-widest">(Raw Input)</span>
                        </div>

                        <div className="space-y-0">
                            {THE_TAPE.map((news) => (
                                <div key={news.id} className="flex gap-6 py-6 border-b border-zinc-900 hover:bg-zinc-900/20 transition-colors">
                                    <div className="w-12 pt-1 font-mono text-[10px] text-zinc-500 uppercase tracking-widest">
                                        {news.time}
                                    </div>
                                    <div className="flex-1">
                                        <div className="flex items-center gap-3 mb-2">
                                            <span className="font-mono text-zinc-300 text-sm font-bold">{news.source}</span>
                                            <span className={`text-[10px] font-mono tracking-widest px-2 py-0.5 border ${news.impact === 'HIGH' ? 'border-zinc-500 text-zinc-300' : 'border-zinc-800 text-zinc-500'}`}>
                                                {news.type}
                                            </span>
                                        </div>
                                        <p className="text-sm text-zinc-400 leading-relaxed font-light">
                                            {news.content}
                                        </p>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>

                    {/* Right Column: The Signal */}
                    <div className="space-y-6 relative">
                        {/* Decorative connecting arrow removed per Tufte anti-chartjunk principles */}

                        <div className="flex items-center gap-3 border-b border-zinc-900 pb-6 mb-6">
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
                            
                            {/* The Pundit Index Teaser */}
                            <div className="mt-8 border-t border-zinc-800 pt-8">
                                <div className="flex items-center justify-between mb-6">
                                    <h4 className="font-mono text-sm font-bold text-zinc-100 flex items-center gap-2">
                                        <Activity className="w-4 h-4 text-zinc-400" />
                                        THE PUNDIT INDEX (VERIFIABLE CONSENSUS)
                                    </h4>
                                    <span className="text-zinc-600 text-[10px] tracking-widest uppercase font-mono bg-zinc-900 px-2 py-1">
                                        Preview
                                    </span>
                                </div>
                                <div className="space-y-6">
                                    <div className="flex flex-col gap-2">
                                        <div className="flex justify-between items-end border-b border-zinc-900 pb-2">
                                            <span className="text-[10px] font-mono text-zinc-500 tracking-widest">MEDIA CONSENSUS</span>
                                            <span className="text-[10px] font-mono text-zinc-400">84% CONVICTION</span>
                                        </div>
                                        <p className="text-sm text-zinc-400 font-light flex items-start gap-3">
                                            <XCircle className="w-4 h-4 text-zinc-600 shrink-0 mt-0.5" />
                                            &quot;This extension guarantees WR1 production through 2029.&quot;
                                        </p>
                                    </div>
                                    <div className="flex flex-col gap-2">
                                        <div className="flex justify-between items-end border-b border-zinc-900 pb-2">
                                            <span className="text-[10px] font-mono text-zinc-500 tracking-widest">EMPIRICAL REALITY (MODEL)</span>
                                            <span className="text-[10px] font-mono text-emerald-500">SELL PREDICTION</span>
                                        </div>
                                        <p className="text-sm text-zinc-100 font-light flex items-start gap-3">
                                            <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0 mt-0.5" />
                                            Structural overpay. Target separation decay mathematically maps to historically dead-cap contracts.
                                        </p>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </section>
    );
}
