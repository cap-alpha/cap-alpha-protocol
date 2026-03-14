import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import Link from "next/link";
import { ArrowRight } from "lucide-react";

interface TeamCardProps {
    team: {
        team: string;
        total_cap: number;
        risk_cap: number;
        count: number;
    };
}

export function TeamCard({ team }: TeamCardProps) {
    const riskPercentage = team.total_cap > 0 ? (team.risk_cap / team.total_cap) * 100 : 0;
    const isHighRisk = riskPercentage > 30;

    const fmt = (n: number) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(n * 1000000);

    return (
        <Link href={`/team/${encodeURIComponent(team.team)}`} className="block group">
            <Card className={cn(
                "overflow-hidden transition-all hover:shadow-lg border-l-4 h-full relative",
                isHighRisk ? "border-l-rose-500" : "border-l-emerald-500 cursor-pointer"
            )}>
                <div className="absolute top-4 right-4 text-muted-foreground group-hover:text-emerald-500 transition-colors">
                    <ArrowRight className="h-5 w-5" />
                </div>
                <CardHeader className="p-4 pb-2">
                    <div className="flex justify-between items-center">
                        <h3 className="font-bold text-2xl tracking-tight leading-none group-hover:text-emerald-500 transition-colors uppercase">
                            {team.team}
                        </h3>
                    </div>
                    <p className="text-xs text-muted-foreground mt-1 uppercase tracking-wider">{team.count} Active Contracts</p>
                </CardHeader>
                
                <CardContent className="p-4 pt-4 space-y-4">
                    <div className="grid grid-cols-2 gap-4">
                        <div>
                            <div className="text-[10px] text-muted-foreground uppercase font-mono tracking-wider mb-1">Total Cap</div>
                            <div className="font-bold text-lg">{fmt(team.total_cap)}</div>
                        </div>
                        <div>
                            <div className="text-[10px] text-rose-500/70 uppercase font-mono tracking-wider mb-1">Risk Exposure</div>
                            <div className="font-bold text-lg text-rose-500">{fmt(team.risk_cap)}</div>
                        </div>
                    </div>
                    
                    <div className="space-y-1.5 pt-2 border-t border-border/50">
                        <div className="flex justify-between text-[10px] uppercase text-muted-foreground font-mono">
                            <span>Portfolio Risk</span>
                            <span className={cn(isHighRisk ? "text-rose-500" : "text-emerald-500")}>{riskPercentage.toFixed(1)}%</span>
                        </div>
                        <Progress value={riskPercentage} className={cn("h-1.5", isHighRisk ? "bg-rose-100 [&>div]:bg-rose-500" : "bg-emerald-100 [&>div]:bg-emerald-500")} />
                    </div>
                </CardContent>
            </Card>
        </Link>
    );
}
