import React from "react";
import { WarRoomData } from "@/app/actions";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ShieldAlert, TrendingUp, AlertTriangle } from "lucide-react";
import Link from "next/link";
import { ScrollArea } from "@/components/ui/scroll-area";

interface WarRoomDashboardProps {
    data: WarRoomData;
}

export function WarRoomDashboard({ data }: WarRoomDashboardProps) {
    const { redAlerts, roiMetrics } = data;

    return (
        <div className="space-y-6">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Red Alert Feed (Isolation Forest) */}
                <Card className="bg-rose-950/20 border-rose-500/20 shadow-lg shadow-rose-500/5">
                    <CardHeader className="pb-3 border-b border-rose-500/10">
                        <div className="flex items-center gap-2 text-rose-500">
                            <ShieldAlert className="w-5 h-5" />
                            <CardTitle className="font-mono tracking-widest uppercase">Red Alert Feed</CardTitle>
                        </div>
                        <CardDescription className="text-rose-400/70">
                            Systemic anomalies detected by Isolation Forest. High uncertainty assets.
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="pt-4 p-0">
                        <ScrollArea className="h-[300px] w-full">
                            <div className="divide-y divide-rose-500/10">
                                {redAlerts.length > 0 ? redAlerts.map((alert, idx) => (
                                    <Link key={idx} href={`/player/${encodeURIComponent(alert.player_name)}`}>
                                        <div className="flex items-center justify-between p-4 hover:bg-rose-500/5 cursor-pointer transition-colors">
                                            <div>
                                                <div className="font-bold text-rose-100 flex items-center gap-2">
                                                    {alert.player_name}
                                                    <Badge variant="outline" className="text-[10px] bg-rose-500/10 text-rose-400 border-rose-500/30">
                                                        UNCERTAINTY: {(alert.uncertainty_score * 100).toFixed(1)}%
                                                    </Badge>
                                                </div>
                                                <div className="text-xs text-rose-400/60 mt-1">
                                                    {alert.team} • {alert.year} {alert.week > 0 ? `Wk ${alert.week}` : ''}
                                                </div>
                                            </div>
                                            <AlertTriangle className="w-4 h-4 text-rose-500/50" />
                                        </div>
                                    </Link>
                                )) : (
                                    <div className="p-8 text-center text-rose-500/50 text-sm font-mono">
                                        NO ANOMALIES DETECTED
                                    </div>
                                )}
                            </div>
                        </ScrollArea>
                    </CardContent>
                </Card>

                {/* Alpha ROI Leaderboard */}
                <Card className="bg-emerald-950/20 border-emerald-500/20 shadow-lg shadow-emerald-500/5">
                    <CardHeader className="pb-3 border-b border-emerald-500/10">
                        <div className="flex items-center gap-2 text-emerald-500">
                            <TrendingUp className="w-5 h-5" />
                            <CardTitle className="font-mono tracking-widest uppercase">Alpha ROI Ledger</CardTitle>
                        </div>
                        <CardDescription className="text-emerald-400/70">
                            System validation: Weeks of lead time over mainstream public consensus.
                            <span className="block mt-1 text-emerald-300 font-bold">
                                Avg. Lead: {roiMetrics.averageLeadTime.toFixed(1)} Weeks ({roiMetrics.totalValidations} Verified Calls)
                            </span>
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="pt-4 p-0">
                        <ScrollArea className="h-[300px] w-full">
                            <div className="divide-y divide-emerald-500/10">
                                {roiMetrics.topPerformers.length > 0 ? roiMetrics.topPerformers.map((roi, idx) => (
                                    <Link key={idx} href={`/player/${encodeURIComponent(roi.player_name)}`}>
                                        <div className="flex items-center justify-between p-4 hover:bg-emerald-500/5 cursor-pointer transition-colors">
                                            <div className="max-w-[70%]">
                                                <div className="font-bold text-emerald-100">
                                                    {roi.player_name}
                                                </div>
                                                <div className="text-xs text-emerald-400/60 mt-1 truncate" title={roi.rationale}>
                                                    {roi.rationale}
                                                </div>
                                            </div>
                                            <Badge variant="default" className="bg-emerald-500 text-black font-bold border-none whitespace-nowrap">
                                                +{roi.lead_time} WEEKS
                                            </Badge>
                                        </div>
                                    </Link>
                                )) : (
                                    <div className="p-8 text-center text-emerald-500/50 text-sm font-mono">
                                        NO ROI DATA FOUND
                                    </div>
                                )}
                            </div>
                        </ScrollArea>
                    </CardContent>
                </Card>
            </div>
        </div>
    );
}
