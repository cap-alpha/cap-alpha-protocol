import { Card, CardContent, CardFooter, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import Link from "next/link";

interface RosterCardProps {
    player: {
        player_name: string;
        team: string;
        position: string;
        cap_hit_millions: number;
        risk_score: number;
        surplus_value: number;
    };
}

export function RosterCard({ player }: RosterCardProps) {
    const isHighRisk = player.risk_score > 0.7;
    const isValue = player.surplus_value > player.cap_hit_millions;

    // Format currency
    const fmt = (n: number) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 }).format(n * 1000000);

    return (
        <Card className={cn(
            "overflow-hidden transition-all hover:shadow-lg border-l-4 group",
            isHighRisk ? "border-l-rose-500" : isValue ? "border-l-emerald-500" : "border-l-border"
        )}>
            <CardHeader className="p-4 pb-2 flex flex-row items-center gap-4 space-y-0 relative">
                <Avatar className="h-10 w-10 border z-10">
                    {/* Placeholder until we have headshots */}
                    <AvatarFallback>{player.position}</AvatarFallback>
                </Avatar>
                <div className="flex-1 overflow-hidden z-10 w-full min-w-0">
                    <div className="flex flex-col">
                        <div className="flex items-center gap-2">
                            <Link href={`/player/${encodeURIComponent(player.player_name.toLowerCase().replace(' ', '-'))}`} className="hover:underline hover:text-emerald-500 transition-colors">
                                <h3 className="font-bold truncate text-base leading-tight relative z-20">{player.player_name}</h3>
                            </Link>
                            {(player.cap_hit_millions > 0 && player.surplus_value === 0) && (
                                <Badge variant="destructive" className="text-[10px] h-4 px-1 rounded-sm relative z-20">DEAD</Badge>
                            )}
                        </div>
                        <p className="text-xs text-muted-foreground mt-0.5 relative z-20 flex items-center gap-1">
                            <Link href={`/team/${encodeURIComponent(player.team)}`} className="hover:text-emerald-500 hover:underline">
                                {player.team}
                            </Link>
                            <span>•</span>
                            <span>{player.position}</span>
                        </p>
                    </div>
                </div>
                <div className="text-right z-10 flex-shrink-0">
                    <div className="font-mono font-bold text-sm tracking-tighter">{fmt(player.cap_hit_millions)}</div>
                    <div className="text-[10px] text-muted-foreground uppercase text-right">Cap Hit</div>
                </div>
            </CardHeader>

            <CardContent className="p-4 pt-2 space-y-3">
                {/* Statistics Grid */}
                <div className="grid grid-cols-2 gap-2 text-xs">
                    <div className="bg-secondary/50 p-2 rounded">
                        <div className="text-[10px] text-muted-foreground uppercase">Fair Value</div>
                        <div className={cn("font-bold", isValue ? "text-emerald-500" : "text-foreground")}>
                            {fmt(player.surplus_value)}
                        </div>
                    </div>
                    <div className="bg-secondary/50 p-2 rounded">
                        <div className="text-[10px] text-muted-foreground uppercase">Efficiency Gap</div>
                        <div className={cn("font-bold", isHighRisk ? "text-rose-500" : "text-amber-500")}>
                            {(player.cap_hit_millions > 0 && player.surplus_value === 0) ? "N/A" : `${(player.risk_score * 100).toFixed(0)}/100`}
                        </div>
                    </div>
                </div>

                {/* Risk Bar */}
                <div className="space-y-1">
                    <div className="flex justify-between text-[10px] uppercase text-muted-foreground">
                        <span>Contract Security</span>
                        <span>{isHighRisk ? "Toxic" : "Secure"}</span>
                    </div>
                    <Progress value={(1 - player.risk_score) * 100} className={cn("h-1", isHighRisk ? "bg-rose-100" : "bg-emerald-100")} />
                </div>
            </CardContent>
        </Card>
    );
}
