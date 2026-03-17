"use client";

import { Activity, ArrowDownRight, ArrowUpRight, DollarSign, Users } from "lucide-react";
import { useEffect, useState } from "react";

export function MarketTicker({ 
    totalCap, 
    riskCap 
}: { 
    totalCap: number;
    riskCap: number;
}) {
    // Simulated market tick for the 'live' feel
    const [tick, setTick] = useState(0);
    
    useEffect(() => {
        const interval = setInterval(() => setTick(prev => (prev + 1) % 2), 5000);
        return () => clearInterval(interval);
    }, []);

    const formatCurrency = (val: number) => {
        return new Intl.NumberFormat('en-US', {
            style: 'currency',
            currency: 'USD',
            notation: "compact",
            maximumFractionDigits: 1
        }).format(val * 1000000); // Assuming val is in millions initially
    };

    return (
        <div className="w-full bg-zinc-950 border-b border-white/10 flex items-center px-4 py-2 overflow-hidden sticky top-16 z-40">
            <div className="flex items-center gap-2 pr-6 border-r border-white/10 shrink-0">
                <Activity className="w-4 h-4 text-emerald-500 animate-pulse" />
                <span className="text-xs font-mono font-bold tracking-widest text-emerald-500 uppercase">
                    Live Market
                </span>
            </div>
            
            <div className="flex-1 flex items-center overflow-x-auto no-scrollbar gap-8 px-6 text-sm font-mono whitespace-nowrap">
                <div className="flex items-center gap-3">
                    <span className="text-zinc-500 uppercase text-xs">League Total Liabilities</span>
                    <span className="text-white font-medium">{formatCurrency(totalCap)}</span>
                    <span className={`flex items-center text-xs ${tick === 0 ? 'text-emerald-500' : 'text-zinc-500'}`}>
                        <ArrowUpRight className="w-3 h-3" /> 0.2%
                    </span>
                </div>

                <div className="flex items-center gap-3">
                    <span className="text-zinc-500 uppercase text-xs">League Risk Exposure</span>
                    <span className="text-white font-medium">{formatCurrency(riskCap)}</span>
                    <span className={`flex items-center text-xs text-rose-500`}>
                        <ArrowDownRight className="w-3 h-3" /> 1.4%
                    </span>
                </div>
                
                <div className="flex items-center gap-3">
                    <span className="text-zinc-500 uppercase text-xs">Active Contracts</span>
                    <span className="text-white font-medium text-xs flex items-center gap-1"><Users className="w-3 h-3 text-zinc-400"/> 2,048</span>
                </div>

                <div className="flex items-center gap-3">
                    <span className="text-zinc-500 uppercase text-xs">Avg Dead Cap Yield</span>
                    <span className="text-white font-medium text-xs flex items-center gap-1"><DollarSign className="w-3 h-3 text-zinc-400"/> 4.2%</span>
                </div>
            </div>
        </div>
    );
}
