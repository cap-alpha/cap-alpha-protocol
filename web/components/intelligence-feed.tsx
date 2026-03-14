"use client";

import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Lock, FileText, TrendingDown, TrendingUp, AlertCircle } from "lucide-react";
import { SignedIn, SignedOut, SignInButton } from "@clerk/nextjs";
import { Button } from "@/components/ui/button";

export function IntelligenceFeed({ playerName, riskScore }: { playerName: string, riskScore: number }) {
    // Generate some mock intelligence data based on the risk score
    const isRisky = riskScore > 0.5;

    const mockSentiments = isRisky ? [
        { type: "Warning", text: "Scouting reports indicate declining burst metrics in recent film.", icon: TrendingDown, color: "text-rose-400" },
        { type: "Rumor", text: "Front office considering post-June 1 designation to clear cap space for 2026.", icon: AlertCircle, color: "text-amber-400" }
    ] : [
        { type: "Positive", text: "Market value expected to increase by 15% next off-season based on current positional scarcity.", icon: TrendingUp, color: "text-emerald-400" },
        { type: "Contract", text: "Extension talks reportedly progressing. Outstanding guaranteed money aligns with expected production.", icon: FileText, color: "text-blue-400" }
    ];

    return (
        <Card className="bg-slate-900 border-slate-800 h-full relative overflow-hidden flex flex-col">
            <CardHeader className="pb-3 border-b border-slate-800">
                <CardTitle className="flex items-center justify-between text-lg">
                    <span className="flex items-center gap-2">
                        <FileText className="h-5 w-5 text-emerald-500" />
                        Cap Alpha Intelligence
                    </span>
                    <Badge variant="outline" className="bg-emerald-500/10 text-emerald-500 border-emerald-500/20 uppercase">
                        Live Feed
                    </Badge>
                </CardTitle>
            </CardHeader>
            <CardContent className="pt-4 flex-1">
                <SignedIn>
                    <div className="space-y-4">
                        <p className="text-sm text-slate-400 mb-4">
                            Synthesized intelligence from unstructured scouting reports and contract telemetry.
                        </p>
                        <div className="space-y-3">
                            {mockSentiments.map((item, i) => {
                                const Icon = item.icon;
                                return (
                                    <div key={i} className="relative pl-6 pb-6 last:pb-0">
                                        {/* Timeline connector */}
                                        {i !== mockSentiments.length - 1 && (
                                            <div className="absolute left-2.5 top-5 bottom-0 w-px bg-slate-800" />
                                        )}
                                        {/* Timeline node */}
                                        <div className="absolute left-0 top-1.5 h-5 w-5 rounded-full bg-slate-950 border border-slate-700 flex items-center justify-center z-10">
                                            <Icon className={`h-3 w-3 ${item.color}`} />
                                        </div>
                                        {/* Content */}
                                        <div className="bg-slate-950/50 p-3 rounded-md border border-slate-800">
                                            <div className="flex justify-between items-center mb-1">
                                                <div className="text-xs font-bold text-slate-400">{item.type}</div>
                                                <div className="text-[10px] text-slate-600">Generated 2h ago</div>
                                            </div>
                                            <div className="text-sm text-slate-300 leading-relaxed">{item.text}</div>
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                        {/* RAG Chat Assistant placeholder */}
                        <div className="mt-6 pt-4 border-t border-slate-800">
                            <div className="text-xs text-slate-500 uppercase font-mono mb-2">Interrogate the Model</div>
                            <div className="bg-slate-950 rounded-md border border-slate-800 p-3 flex text-sm text-slate-500 italic">
                                Ask a question about {playerName}'s valuation... (RAG Integration Pending)
                            </div>
                        </div>
                    </div>
                </SignedIn>

                <SignedOut>
                    {/* Paywall Overlay */}
                    <div className="absolute inset-0 z-10 bg-gradient-to-t from-slate-950 via-slate-900/90 to-slate-900/50 backdrop-blur-md flex flex-col items-center justify-center p-6 text-center">
                        <Lock className="h-10 w-10 text-emerald-500 mb-4" />
                        <h3 className="text-2xl font-black tracking-tight text-white mb-2">PRO INTELLIGENCE REQUIRED</h3>
                        <p className="text-slate-300 text-sm mb-6 max-w-xs">
                            Unlock real-time rumors, scouting synthesis, and RAG-powered contract telemetry for {playerName}.
                        </p>
                        <SignInButton mode="modal">
                            <Button className="bg-emerald-500 hover:bg-emerald-600 text-white w-full">
                                Upgrade to Executive Tier
                            </Button>
                        </SignInButton>
                    </div>
                    {/* Blurred Background Content */}
                    <div className="space-y-4 opacity-30 select-none" aria-hidden="true">
                        <div className="h-16 bg-slate-800 rounded animate-pulse" />
                        <div className="h-16 bg-slate-800 rounded animate-pulse" />
                        <div className="h-24 bg-slate-800 rounded animate-pulse" />
                    </div>
                </SignedOut>
            </CardContent>
        </Card>
    );
}
