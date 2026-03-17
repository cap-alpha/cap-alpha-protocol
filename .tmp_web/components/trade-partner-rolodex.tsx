
"use client";

import React, { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Loader2, Briefcase, ThumbsUp, ThumbsDown } from "lucide-react";
import { usePersona } from "./persona-context";

interface Partner {
    team: string;
    score: number;
    reason: string;
}

interface RolodexProps {
    selectedPlayer?: {
        name: string;
        cap_hit: number;
        position: string;
    } | null;
}

export function TradePartnerRolodex({ selectedPlayer }: RolodexProps) {
    const { persona } = usePersona();
    const [partners, setPartners] = useState<Partner[]>([]);
    const [loading, setLoading] = useState(false);
    const [lastSearched, setLastSearched] = useState<string | null>(null);

    // Auto-fetch when player changes (if in Agent mode)
    React.useEffect(() => {
        if (persona === "AGENT" && selectedPlayer && selectedPlayer.name !== lastSearched) {
            fetchPartners();
        }
    }, [persona, selectedPlayer, lastSearched]);

    const fetchPartners = async () => {
        if (!selectedPlayer) return;

        setLoading(true);
        setLastSearched(selectedPlayer.name);
        setPartners([]); // Reset

        try {
            const res = await fetch(`/api/trade/find_partner/${selectedPlayer.name}?cap_hit=${selectedPlayer.cap_hit}&position=${selectedPlayer.position}`);
            if (!res.ok) throw new Error("Failed to fetch");
            const data = await res.json();
            setPartners(data.top_partners || []);
        } catch (e) {
            console.error(e);
            // Fallback mock for demo if API fails/offline
            setPartners([
                { team: "LV", score: 95, reason: "Mock: High Cap Space" },
                { team: "WAS", score: 88, reason: "Mock: Rebuilding" }
            ]);
        } finally {
            setLoading(false);
        }
    };

    if (persona !== "AGENT") return null;

    if (!selectedPlayer) {
        return (
            <Card className="bg-slate-900 border-dashed border-slate-700 h-full flex items-center justify-center p-8">
                <div className="text-center text-slate-500">
                    <Briefcase className="h-12 w-12 mx-auto mb-4 opacity-50" />
                    <p>Select a player to find buyers</p>
                </div>
            </Card>
        );
    }

    return (
        <Card className="bg-slate-950 border-emerald-900/50 shadow-2xl">
            <CardHeader className="bg-emerald-950/20 border-b border-emerald-900/30">
                <div className="flex justify-between items-center">
                    <div>
                        <CardTitle className="text-emerald-400 flex items-center gap-2">
                            <Briefcase className="h-5 w-5" />
                            The Rolodex
                        </CardTitle>
                        <CardDescription className="text-emerald-600/80">
                            Searching market for <span className="text-white font-mono">{selectedPlayer.name}</span>
                        </CardDescription>
                    </div>
                    <Badge variant="outline" className="border-emerald-500/50 text-emerald-400 bg-emerald-950/30">
                        ${selectedPlayer.cap_hit}M
                    </Badge>
                </div>
            </CardHeader>
            <CardContent className="p-0">
                {loading ? (
                    <div className="h-48 flex items-center justify-center space-x-2 text-emerald-500">
                        <Loader2 className="h-6 w-6 animate-spin" />
                        <span>Contacting GMs...</span>
                    </div>
                ) : (
                    <div className="divide-y divide-emerald-900/30">
                        {partners.length === 0 ? (
                            <div className="p-8 text-center text-slate-500">No buyers found. Market is cold.</div>
                        ) : (
                            partners.map((p, i) => (
                                <div key={p.team} className="p-4 hover:bg-emerald-950/10 transition-colors flex items-center justify-between group">
                                    <div className="flex items-center gap-4">
                                        <div className="flex items-center justify-center w-10 h-10 rounded-full bg-slate-900 border border-slate-700 font-bold text-slate-300">
                                            {p.team}
                                        </div>
                                        <div>
                                            <div className="font-semibold text-slate-200">
                                                Fit Score: <span className="text-emerald-400">{p.score}</span>
                                            </div>
                                            <div className="text-xs text-slate-500 uppercase tracking-wide">
                                                {p.reason}
                                            </div>
                                        </div>
                                    </div>
                                    <div className="flex gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                                        <button className="p-2 hover:bg-emerald-500/20 rounded-full text-slate-400 hover:text-emerald-400">
                                            <ThumbsUp className="h-4 w-4" />
                                        </button>
                                        <button className="p-2 hover:bg-rose-500/20 rounded-full text-slate-400 hover:text-rose-400">
                                            <ThumbsDown className="h-4 w-4" />
                                        </button>
                                    </div>
                                </div>
                            ))
                        )}
                    </div>
                )}
            </CardContent>
        </Card>
    );
}
