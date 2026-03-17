"use client"

import * as React from "react"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Activity, ExternalLink, RefreshCw } from "lucide-react"
import scenarios from "@/data/trade_scenarios.json"

interface Scenario {
    buyer: string;
    seller: string;
    player: string;
    cap: number;
    cost: string;
    score: number;
    rationale: string;
}

interface TradeIntelligenceStreamProps {
    teamFilter?: string; // If provided, only show trades involving this team
    onSelectScenario?: (scenario: Scenario) => void;
}

export function TradeIntelligenceStream({ teamFilter, onSelectScenario }: TradeIntelligenceStreamProps) {

    const filteredScenarios = React.useMemo(() => {
        if (!teamFilter) return scenarios;
        return scenarios.filter(s => s.buyer === teamFilter || s.seller === teamFilter);
    }, [teamFilter]);

    return (
        <Card className="h-full border-l border-y-0 border-r-0 rounded-none bg-slate-950/80 backdrop-blur-md">
            <CardHeader className="pb-2 border-b border-border/50">
                <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-2">
                        <Activity className="h-4 w-4 text-emerald-500 animate-pulse" />
                        <CardTitle className="text-sm font-mono uppercase tracking-widest text-emerald-500">
                            Intel Stream
                        </CardTitle>
                    </div>
                    <Badge variant="outline" className="text-[10px] font-mono border-emerald-500/50 text-emerald-500">
                        LIVE
                    </Badge>
                </div>
            </CardHeader>
            <CardContent className="p-0 h-[calc(100%-60px)]">
                <ScrollArea className="h-full">
                    <div className="flex flex-col">
                        {filteredScenarios.length === 0 ? (
                            <div className="p-8 text-center text-muted-foreground text-xs font-mono">
                                No active chatter for selected team.
                            </div>
                        ) : (
                            filteredScenarios.map((s, i) => (
                                <div
                                    key={i}
                                    className="p-4 border-b border-border/30 hover:bg-white/5 cursor-pointer transition-colors group"
                                    onClick={() => onSelectScenario && onSelectScenario(s)}
                                >
                                    <div className="flex justify-between items-start mb-2">
                                        <div className="flex gap-2 text-xs font-bold font-mono">
                                            <span className="text-emerald-400">{s.buyer}</span>
                                            <span className="text-muted-foreground">gets</span>
                                            <span className="text-white">{s.player}</span>
                                        </div>
                                        <span className="text-[10px] font-mono text-emerald-600 bg-emerald-950/30 px-1 rounded">
                                            {s.score.toFixed(1)} UTIL
                                        </span>
                                    </div>

                                    <div className="flex justify-between items-center text-[10px] text-muted-foreground mb-2">
                                        <span>from {s.seller}</span>
                                        <span>Cost: {s.cost}</span>
                                    </div>

                                    <p className="text-[10px] leading-relaxed text-zinc-400 border-l-2 border-emerald-500/20 pl-2">
                                        {s.rationale.replace(/\*\*/g, '')}
                                    </p>

                                    <div className="mt-2 opacity-0 group-hover:opacity-100 transition-opacity flex justify-end">
                                        <div className="flex items-center text-[10px] text-emerald-500 uppercase font-bold gap-1">
                                            <span>Load Scenario</span>
                                            <ExternalLink className="h-3 w-3" />
                                        </div>
                                    </div>
                                </div>
                            ))
                        )}
                    </div>
                </ScrollArea>
            </CardContent>
        </Card>
    )
}
