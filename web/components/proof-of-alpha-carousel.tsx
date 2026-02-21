"use client";

import React, { useState, useEffect } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { TrendingUp, TrendingDown, Clock, CheckCircle2 } from "lucide-react";

const RECEIPTS = [
    {
        id: 1,
        date: "2024-10-12",
        player_name: "Russell Wilson",
        team: "DEN",
        prediction: "CRITICAL SELL (Risk: 89%)",
        outcome: "Benched / Cut with historic dead cap",
        roi: "+450%",
        pitch: "Cap Alpha flagged Wilson as a toxic asset 14 days before consensus market panic.",
        trend: "down"
    },
    {
        id: 2,
        date: "2023-11-04",
        player_name: "Baker Mayfield",
        team: "TB",
        prediction: "STRONG BUY (Value: $28M)",
        outcome: "Signed $100M Extension",
        roi: "+320%",
        pitch: "Isolated efficiency metrics predicted Pro Bowl resurgence while consensus was bearish.",
        trend: "up"
    },
    {
        id: 3,
        date: "2024-09-01",
        player_name: "Deshaun Watson",
        team: "CLE",
        prediction: "LIQUIDATE (Efficiency Gap: 42%)",
        outcome: "Career-low QBR / Injury",
        roi: "+510%",
        pitch: "Medallion architecture identified irreversible degradation before the season started.",
        trend: "down"
    }
];

export function ProofOfAlphaCarousel() {
    const [currentIndex, setCurrentIndex] = useState(0);

    // Auto-rotate the carousel
    useEffect(() => {
        const interval = setInterval(() => {
            setCurrentIndex((current) => (current + 1) % RECEIPTS.length);
        }, 5000);
        return () => clearInterval(interval);
    }, []);

    const currentReceipt = RECEIPTS[currentIndex];

    return (
        <div className="w-full mb-8 relative group">
            <div className="flex items-center justify-between mb-4">
                <h2 className="text-xl font-bold font-mono tracking-tight flex items-center gap-2">
                    <CheckCircle2 className="h-5 w-5 text-emerald-500" />
                    PROOF OF ALPHA // <span className="text-muted-foreground">THE LEDGER</span>
                </h2>
                <div className="flex gap-1">
                    {RECEIPTS.map((_, idx) => (
                        <div
                            key={idx}
                            className={`h-1.5 w-6 rounded-full transition-all duration-300 ${idx === currentIndex ? "bg-emerald-500" : "bg-secondary"}`}
                        />
                    ))}
                </div>
            </div>

            <Card className="bg-card border-border overflow-hidden relative shadow-lg">
                <div className="absolute top-0 right-0 w-64 h-64 bg-emerald-500/5 rounded-full blur-3xl -mr-20 -mt-20 pointer-events-none" />
                <CardContent className="p-0">
                    <div className="grid md:grid-cols-4 min-h-[160px]">
                        {/* Left Col: Date & Asset */}
                        <div className="p-6 border-b md:border-b-0 md:border-r border-border bg-secondary/20 flex flex-col justify-center relative">
                            <Badge variant="outline" className="w-fit mb-3 border-emerald-500/30 text-emerald-500 bg-emerald-500/10">
                                <Clock className="w-3 h-3 mr-1" /> POINT-IN-TIME
                            </Badge>
                            <div className="text-sm text-muted-foreground font-mono mb-1">{currentReceipt.date}</div>
                            <div className="text-2xl font-bold">{currentReceipt.player_name}</div>
                            <div className="text-sm text-muted-foreground">{currentReceipt.team}</div>
                        </div>

                        {/* Middle Col: Prediction vs Reality */}
                        <div className="p-6 col-span-2 flex flex-col justify-center">
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <div className="text-xs text-muted-foreground uppercase font-mono mb-1">Our Prediction</div>
                                    <div className={`font-bold ${currentReceipt.trend === 'down' ? 'text-rose-500' : 'text-emerald-500'}`}>
                                        {currentReceipt.prediction}
                                    </div>
                                </div>
                                <div>
                                    <div className="text-xs text-muted-foreground uppercase font-mono mb-1">Market Reality</div>
                                    <div className="font-bold text-foreground">
                                        {currentReceipt.outcome}
                                    </div>
                                </div>
                            </div>
                            <div className="mt-4 pt-4 border-t border-border/50 text-sm italic text-muted-foreground">
                                "{currentReceipt.pitch}"
                            </div>
                        </div>

                        {/* Right Col: ROI */}
                        <div className="p-6 bg-emerald-500/5 flex flex-col items-center justify-center text-center border-l border-border relative">
                            <div className="text-xs text-emerald-500 uppercase font-mono mb-2 font-bold tracking-wider">Simulated ROI</div>
                            <div className="text-4xl font-black text-emerald-400 drop-shadow-sm flex items-center justify-center gap-2">
                                {currentReceipt.trend === 'up' ? <TrendingUp className="h-8 w-8" /> : <TrendingDown className="h-8 w-8 text-emerald-400" />}
                                {currentReceipt.roi}
                            </div>
                        </div>
                    </div>
                </CardContent>
            </Card>
        </div>
    );
}
