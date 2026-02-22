"use client";

import { useState, useEffect } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ChevronLeft, ChevronRight, TrendingDown, Clock, MessageSquareWarning } from "lucide-react";
import { Button } from "@/components/ui/button";

const RECEIPTS = [
    {
        id: 1,
        date: "2024-02-15",
        player_name: "Russell Wilson",
        team: "DEN",
        contract_size: "$242.5M",
        prediction: "CRITICAL SELL: $85M Dead Cap Restructure imminent.",
        media_sentiment: "Consensus: 'Broncos stuck with Wilson. Payton must fix him.'",
        cap_alpha_insight: "Performance degradation curve signaled unrecoverable efficiency drop. Trade/Cut was strictly dominant.",
        outcome: "Cut 14 days later with historic $85M dead cap hit. $37M cash saved over keeping him.",
        roi: "Avoiding the hit saved Denver 3 years of competitive window.",
        trend: "down"
    },
    {
        id: 2,
        date: "2023-01-20",
        player_name: "Aaron Rodgers",
        team: "GB",
        contract_size: "$150.8M",
        prediction: "SELL: Leverage peak before age-based efficiency cliff.",
        media_sentiment: "Consensus: 'Packers must run it back with back-to-back MVP.'",
        cap_alpha_insight: "Historic age/salary intersection indicated maximum trade value. Holding was negative EV.",
        outcome: "Traded to Jets. GB secured premium draft capital and cleared $40M off books.",
        roi: "Net +$35M Cap Space vs holding.",
        trend: "down"
    },
    {
        id: 3,
        date: "2025-01-15",
        player_name: "Deshaun Watson",
        team: "CLE",
        contract_size: "$230M (Fully Guaranteed)",
        prediction: "TOXIC ASSET: Negative Efficiency Gap commands buyout.",
        media_sentiment: "Consensus: 'Browns hands are tied due to fully guaranteed contract.'",
        cap_alpha_insight: "Sunk cost fallacy. Roster impact is deeply negative relative to replacement level. Take the $92M hit.",
        outcome: "Pending Resolution. Browns effectively benched asset.",
        roi: "Recommendation prevents further compound damage to roster architecture.",
        trend: "down"
    }
];

export function PointInTimeLedger() {
    const [currentIndex, setCurrentIndex] = useState(0);

    // Auto-rotate every 8 seconds
    useEffect(() => {
        const timer = setInterval(() => {
            setCurrentIndex((prev) => (prev + 1) % RECEIPTS.length);
        }, 8000);
        return () => clearInterval(timer);
    }, []);

    const nextSlide = () => setCurrentIndex((prev) => (prev + 1) % RECEIPTS.length);
    const prevSlide = () => setCurrentIndex((prev) => (prev - 1 + RECEIPTS.length) % RECEIPTS.length);

    const currentReceipt = RECEIPTS[currentIndex];

    return (
        <div className="w-full relative group">
            <Card className="bg-card border-border overflow-hidden relative shadow-2xl">
                <div className="absolute top-0 right-0 w-96 h-96 bg-emerald-500/10 rounded-full blur-3xl pointer-events-none -mr-32 -mt-32" />

                <CardContent className="p-0">
                    <div className="grid md:grid-cols-5 min-h-[220px]">

                        {/* Left Col: Asset & Date */}
                        <div className="p-8 border-b md:border-b-0 md:border-r border-border bg-secondary/30 flex flex-col justify-center relative">
                            <Badge variant="outline" className="w-fit mb-4 bg-background px-3 py-1 font-mono text-emerald-500 border-emerald-500/30">
                                <Clock className="w-3 h-3 mr-2" />
                                {currentReceipt.date}
                            </Badge>
                            <h3 className="text-3xl font-black tracking-tight">{currentReceipt.player_name}</h3>
                            <p className="text-muted-foreground font-mono text-sm mt-2">{currentReceipt.team} | TCV: {currentReceipt.contract_size}</p>
                            <div className="mt-6">
                                <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold bg-red-500/10 text-red-500 border border-red-500/20">
                                    <TrendingDown className="w-3 h-3 mr-1" />
                                    {currentReceipt.prediction}
                                </span>
                            </div>
                        </div>

                        {/* Middle Col: The Insight Conflict */}
                        <div className="p-8 md:col-span-2 flex flex-col justify-center border-b md:border-b-0 md:border-r border-border bg-card relative z-10">
                            <div className="space-y-6">
                                <div>
                                    <h4 className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center mb-2">
                                        <MessageSquareWarning className="w-3 h-3 mr-2" />
                                        Prevailing Market Wisdom
                                    </h4>
                                    <p className="text-md italic text-slate-400 border-l-2 border-slate-700 pl-4">{currentReceipt.media_sentiment}</p>
                                </div>
                                <div>
                                    <h4 className="text-xs font-bold uppercase tracking-wider text-emerald-500 mb-2">
                                        Cap Alpha Insight
                                    </h4>
                                    <p className="text-md font-medium">{currentReceipt.cap_alpha_insight}</p>
                                </div>
                            </div>
                        </div>

                        {/* Right Col: The Outcome */}
                        <div className="p-8 md:col-span-2 flex flex-col justify-center bg-card relative z-10">
                            <h4 className="text-sm font-bold uppercase tracking-wider text-muted-foreground mb-4">
                                Reality / Outcome
                            </h4>
                            <p className="text-lg font-medium leading-relaxed mb-6">{currentReceipt.outcome}</p>

                            <div className="p-4 bg-emerald-500/10 border border-emerald-500/20 rounded-md">
                                <h4 className="text-xs font-bold uppercase text-emerald-500 mb-1">Impact</h4>
                                <p className="text-sm font-mono text-emerald-400">{currentReceipt.roi}</p>
                            </div>
                        </div>

                    </div>
                </CardContent>
            </Card>

            {/* Navigation Dots */}
            <div className="flex justify-center gap-2 mt-6">
                {RECEIPTS.map((_, idx) => (
                    <button
                        key={idx}
                        onClick={() => setCurrentIndex(idx)}
                        className={`w-2 h-2 rounded-full transition-all ${idx === currentIndex ? "bg-emerald-500 w-6" : "bg-border hover:bg-muted-foreground"
                            }`}
                        aria-label={`Go to slide ${idx + 1}`}
                    />
                ))}
            </div>

            {/* Arrows */}
            <div className="absolute top-1/2 -translate-y-1/2 -left-12 hidden lg:flex">
                <Button variant="ghost" size="icon" onClick={prevSlide} className="rounded-full h-10 w-10 border border-border bg-background shadow-sm hover:bg-secondary">
                    <ChevronLeft className="h-5 w-5" />
                </Button>
            </div>
            <div className="absolute top-1/2 -translate-y-1/2 -right-12 hidden lg:flex">
                <Button variant="ghost" size="icon" onClick={nextSlide} className="rounded-full h-10 w-10 border border-border bg-background shadow-sm hover:bg-secondary">
                    <ChevronRight className="h-5 w-5" />
                </Button>
            </div>
        </div>
    );
}
