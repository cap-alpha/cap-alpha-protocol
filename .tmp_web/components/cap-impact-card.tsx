
import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { TradeImpact } from '@/lib/trade-logic';
import { ArrowUpRight, ArrowDownRight, DollarSign } from 'lucide-react';

interface CapImpactCardProps {
    impact: TradeImpact;
    title?: string;
}

export function CapImpactCard({ impact, title }: CapImpactCardProps) {
    const isPositive = impact.net_cap_change >= 0;
    const colorClass = isPositive ? 'text-emerald-500' : 'text-rose-500';
    const bgClass = isPositive ? 'bg-emerald-500/10' : 'bg-rose-500/10';
    const borderClass = isPositive ? 'border-emerald-500/20' : 'border-rose-500/20';

    return (
        <Card className={`bg-card border ${borderClass}`}>
            <CardHeader className="pb-2">
                <CardTitle className="text-xs font-mono uppercase text-muted-foreground flex justify-between">
                    <span>{title || `${impact.team} Cap `}</span>
                    {isPositive ? <ArrowUpRight className="h-4 w-4 text-emerald-500" /> : <ArrowDownRight className="h-4 w-4 text-rose-500" />}
                </CardTitle>
            </CardHeader>
            <CardContent>
                <div className="flex items-baseline space-x-2">
                    <span className={`text-2xl font-bold font-mono ${colorClass}`}>
                        {isPositive ? '+' : ''}{impact.net_cap_change.toFixed(2)}M
                    </span>
                    <span className="text-xs text-muted-foreground">Net Cap Space</span>
                </div>

                <div className="mt-4 space-y-2">
                    {/* Breakdown */}
                    <div className="flex justify-between text-xs">
                        <span className="text-muted-foreground">Salary Shed:</span>
                        <span className="text-emerald-500 font-mono">+{impact.cap_cleared.toFixed(2)}M</span>
                    </div>
                    <div className="flex justify-between text-xs">
                        <span className="text-muted-foreground">Dead Money Hit:</span>
                        <span className="text-rose-500 font-mono">-{impact.dead_money_acceleration.toFixed(2)}M</span>
                    </div>
                    <div className="flex justify-between text-xs pt-2 border-t border-border">
                        <span className="text-muted-foreground">New Salaries:</span>
                        <span className="text-amber-500 font-mono">
                            -{(impact.assets_acquired.reduce((sum, a) => sum + (a.cap_hit_millions * 0.8), 0)).toFixed(2)}M
                        </span>
                    </div>
                </div>
            </CardContent>
        </Card>
    );
}
