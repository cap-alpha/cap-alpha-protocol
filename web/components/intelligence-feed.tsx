"use client";

import { useState } from "react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Lock, FileText, TrendingDown, TrendingUp, AlertCircle, Info, Filter } from "lucide-react";
import { SignedIn, SignedOut, SignInButton } from "@clerk/nextjs";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { IntelligenceEvent } from "@/app/actions";
import { ProvenanceSnapshot } from "./provenance-snapshot";
import Link from "next/link";
import { slugify } from "@/lib/utils";

export function IntelligenceFeed({ playerName, riskScore, feedEvents = [] }: { playerName: string, riskScore: number, feedEvents?: IntelligenceEvent[] }) {

    const [criticalOnly, setCriticalOnly] = useState(false);

    const displayedEvents = criticalOnly 
        ? feedEvents.filter(e => e.type === 'Warning' || e.type === 'High Uncertainty' || e.color.includes('rose') || e.color.includes('amber'))
        : feedEvents;

    const getIcon = (iconName: string) => {
        switch (iconName) {
            case 'TrendingDown': return TrendingDown;
            case 'TrendingUp': return TrendingUp;
            case 'AlertCircle': return AlertCircle;
            case 'FileText': return FileText;
            default: return Info; // Fallback
        }
    };

    return (
        <Card className="bg-transparent border-0 h-full relative overflow-hidden flex flex-col">
            <CardHeader className="pb-3 border-b border-zinc-900">
                <CardTitle className="flex items-center justify-between text-lg">
                    <span className="flex items-center gap-2">
                        <FileText className="h-5 w-5 text-emerald-500" />
                        Cap Alpha Intelligence
                    </span>
                    <Badge variant="outline" className="bg-emerald-500/10 text-emerald-500 border-emerald-500/20 uppercase">
                        Live Feed
                    </Badge>
                </CardTitle>
                <div className="flex items-center justify-between mt-4">
                    <div className="flex items-center space-x-2">
                        <Filter className="h-4 w-4 text-slate-500" />
                        <Label htmlFor="critical-mode" className="text-xs text-slate-400 font-mono uppercase tracking-wider cursor-pointer">
                            Critical Only
                        </Label>
                    </div>
                    <Switch
                        id="critical-mode"
                        checked={criticalOnly}
                        onChange={(e: React.ChangeEvent<HTMLInputElement>) => setCriticalOnly(e.target.checked)}
                        className="data-[state=checked]:bg-rose-500"
                    />
                </div>
            </CardHeader>
            <CardContent className="pt-4 flex-1">
                <SignedIn>
                    <div className="space-y-4">
                        <p className="text-sm text-slate-400 mb-4">
                            Synthesized intelligence from unstructured scouting reports and contract telemetry.
                        </p>
                        {displayedEvents.length === 0 ? (
                            <div className="flex flex-col items-center justify-center py-10 text-center border border-dashed border-slate-800 rounded-lg bg-slate-950/30">
                                <Info className="h-8 w-8 text-slate-600 mb-3" />
                                <h4 className="text-sm font-semibold text-slate-300">No {criticalOnly ? "Critical " : ""}Intelligence Events</h4>
                                <p className="text-xs text-slate-500 mt-1 max-w-[200px]">
                                    No significant modeling or media shifts detected in the trailing 30 days.
                                </p>
                            </div>
                        ) : (
                            <div className="space-y-3">
                                {displayedEvents.map((item, i) => {
                                    const IconNode = getIcon(item.icon);
                                    return (
                                        <div key={i} className="relative pl-6 pb-6 last:pb-0">
                                            {/* Timeline connector */}
                                            {i !== displayedEvents.length - 1 && (
                                                <div className="absolute left-2.5 top-5 bottom-0 w-px bg-slate-800" />
                                            )}
                                            {/* Timeline node */}
                                            <div className="absolute left-0 top-1.5 h-5 w-5 rounded-full bg-slate-950 border border-slate-700 flex items-center justify-center z-10">
                                                <IconNode className={`h-3 w-3 ${item.color}`} />
                                            </div>
                                            {/* Content */}
                                            <div className="bg-transparent py-2 w-full mt-2 pr-4">
                                                <ProvenanceSnapshot
                                                    source={item.type}
                                                    content={item.text}
                                                    sentiment={item.color.includes('rose') || item.color.includes('amber') ? 0.2 : 0.8}
                                                    timestamp={item.timestamp || new Date().toISOString()}
                                                    provenanceHash={item.provenanceHash}
                                                    snapshotType={item.type === 'Warning' ? 'SYSTEM_ALERT' : (item.type.includes('Media') ? 'WEB_ARCHIVE' : 'DISPATCH_LOG')}
                                                    sourceUrl={item.url}
                                                />
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        )}
                        {/* RAG Chat Assistant placeholder */}
                        <div className="mt-6 pt-4 border-t border-slate-800">
                            <div className="text-xs text-slate-500 uppercase font-mono mb-2">Interrogate the Model</div>
                            <div className="bg-slate-950 rounded-md border border-slate-800 p-3 flex text-sm text-slate-500 italic">
                                Ask a question about <Link href={`/player/${encodeURIComponent(slugify(playerName))}`} className="hover:underline hover:text-emerald-400 transition-colors px-1">{playerName}</Link>&apos;s valuation... (RAG Integration Pending)
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
                            Unlock real-time rumors, scouting synthesis, and RAG-powered contract telemetry for <Link href={`/player/${encodeURIComponent(slugify(playerName))}`} className="hover:underline hover:text-emerald-400 transition-colors font-bold">{playerName}</Link>.
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
