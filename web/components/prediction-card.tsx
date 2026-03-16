"use client";

import React, { useState } from "react";
import { TrendingUp, TrendingDown, Minus, CheckCircle } from "lucide-react";
import { cn } from "@/lib/utils";

interface PredictionCardProps {
    playerId: string;
    playerName: string;
    currentCapHit: number;
    position: string;
    team: string;
}

export function PredictionCard({ playerId, playerName, currentCapHit, position, team }: PredictionCardProps) {
    const [voteDir, setVoteDir] = useState<"BUY" | "HOLD" | "SHORT" | null>(null);
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [hasVoted, setHasVoted] = useState(false);

    const handleVote = async (direction: "BUY" | "HOLD" | "SHORT") => {
        setVoteDir(direction);
        setIsSubmitting(true);
        
        try {
            const res = await fetch("/api/predictions", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ playerId, direction, timestamp: Date.now() }),
            });
            
            if (res.ok) {
                setHasVoted(true);
            }
        } catch (e) {
            console.error(e);
        } finally {
            setIsSubmitting(false);
        }
    };

    const formatMoney = (val: number) => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(val);

    return (
        <div className="bg-card border border-border rounded-lg p-5 shadow-sm">
            <div className="flex mb-4 items-baseline justify-between border-b border-border/50 pb-3">
                <div className="flex items-baseline gap-2">
                    <h3 className="text-lg font-bold text-foreground">{playerName}</h3>
                    <p className="text-xs font-medium text-muted-foreground">{position} • {team}</p>
                </div>
                <div className="text-right">
                    <p className="font-mono text-base font-semibold text-foreground">
                        {formatMoney(currentCapHit)}
                        <span className="text-xs text-muted-foreground ml-1 font-sans font-normal">Cap Hit</span>
                    </p>
                </div>
            </div>

            {hasVoted ? (
                <div className="flex flex-col items-center justify-center p-4 bg-muted/50 rounded-md">
                    <CheckCircle className="h-6 w-6 text-foreground mb-2" />
                    <p className="text-sm font-semibold text-foreground">Prediction Logged</p>
                    <p className="text-xs text-muted-foreground">+50 Alpha Credits</p>
                </div>
            ) : (
                <div className="space-y-3">
                    <div className="text-sm font-medium text-muted-foreground mb-1">
                        Predict Action: {team} vs. {playerName}
                    </div>
                    
                    <div className="grid grid-cols-3 gap-2">
                        <button
                            disabled={isSubmitting}
                            onClick={() => handleVote("BUY")}
                            className={cn(
                                "flex flex-col items-center justify-center py-2 px-1 rounded border border-transparent transition-all",
                                "hover:bg-green-500/10 hover:text-green-500",
                                "disabled:opacity-50",
                                voteDir === "BUY" ? "bg-green-500/10 border-green-500/30 text-green-500" : "bg-muted/30 text-muted-foreground"
                            )}
                        >
                            <TrendingUp className="h-4 w-4 mb-1" />
                            <span className="text-[10px] uppercase font-semibold">Extend</span>
                        </button>

                        <button
                            disabled={isSubmitting}
                            onClick={() => handleVote("HOLD")}
                            className={cn(
                                "flex flex-col items-center justify-center py-2 px-1 rounded border border-transparent transition-all",
                                "hover:bg-amber-500/10 hover:text-amber-500",
                                "disabled:opacity-50",
                                voteDir === "HOLD" ? "bg-amber-500/10 border-amber-500/30 text-amber-500" : "bg-muted/30 text-muted-foreground"
                            )}
                        >
                            <Minus className="h-4 w-4 mb-1" />
                            <span className="text-[10px] uppercase font-semibold">Restructure</span>
                        </button>

                        <button
                            disabled={isSubmitting}
                            onClick={() => handleVote("SHORT")}
                            className={cn(
                                "flex flex-col items-center justify-center py-2 px-1 rounded border border-transparent transition-all",
                                "hover:bg-rose-500/10 hover:text-rose-500",
                                "disabled:opacity-50",
                                voteDir === "SHORT" ? "bg-rose-500/10 border-rose-500/30 text-rose-500" : "bg-muted/30 text-muted-foreground"
                            )}
                        >
                            <TrendingDown className="h-4 w-4 mb-1" />
                            <span className="text-[10px] uppercase font-semibold">Cut/Trade</span>
                        </button>
                    </div>
                </div>
            )}
        </div>
    );
}
