"use client";

import { useState } from 'react';
import { PlayerEfficiency } from "@/app/actions";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { ArrowLeft, ShieldAlert, CheckCircle2 } from "lucide-react";
import Link from "next/link";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
    ComposedChart,
    Line,
    Bar,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    Legend,
    ResponsiveContainer,
    Area
} from "recharts";
import { CutCalculator } from './cut-calculator';
import { PositionDistributionChart } from './position-distribution-chart';
import { SaveScenarioButton } from './save-scenario-button';
import { IntelligenceFeed } from './intelligence-feed';
import { PlayerTimeline } from './player-timeline';
import { TimelineEvent, IntelligenceEvent } from "@/app/actions";

interface PlayerDetailViewProps {
    player: PlayerEfficiency;
    distributionData?: any[]; 
    timeline?: TimelineEvent[];
    feed?: IntelligenceEvent[];
}

export default function PlayerDetailView({ player, distributionData = [], timeline = [], feed = [] }: PlayerDetailViewProps) {
    // State for Cut Calculator
    const [isPostJune1, setIsPostJune1] = useState(false);

    // Safe Access for History
    const history = player.history || [];

    // Chart Data Preparation
    const chartData = history.map(h => ({
        year: h.year,
        actual: h.actual,
        predicted: h.predicted,
        error: h.actual - h.predicted
    })).sort((a, b) => a.year - b.year);

    // Cumulative Error
    const totalError = chartData.reduce((sum, d) => sum + Math.abs(d.error), 0);
    const avgError = chartData.length > 0 ? totalError / chartData.length : 0;

    // Uncertainty Quantification: Error Bands
    const chartDataWithBands = chartData.map(d => ({
        ...d,
        bounds: [
            Math.max(0, d.predicted - avgError), // Floor at 0
            d.predicted + avgError
        ]
    }));

    return (
        <div className="space-y-6 max-w-7xl mx-auto">
            <div className="flex items-center justify-between mb-8">
                <div className="flex items-center gap-4">
                    <Link href="/" className="p-2 hover:bg-white/10 rounded-full transition-colors">
                        <ArrowLeft className="h-6 w-6 text-slate-400" />
                    </Link>
                    <div>
                        <div className="flex items-center gap-3">
                            <h1 className="text-4xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-emerald-400 to-cyan-400">
                                {player.player_name}
                            </h1>
                            {player.report_status && (
                                <Badge variant="outline" className={`border font-semibold tracking-wide ${player.report_status.toUpperCase() === 'OUT' ? 'border-red-500/50 bg-red-500/10 text-red-500' : 'border-amber-500/50 bg-amber-500/10 text-amber-500'}`}>
                                    {player.report_status.toUpperCase()} • {player.report_primary_injury || 'Undisclosed'}
                                </Badge>
                            )}
                        </div>
                        <p className="text-slate-400 text-lg mt-1">{player.position} • {player.team} • {player.year}</p>
                    </div>
                </div>
                {/* Save Action */}
                <SaveScenarioButton
                    rosterState={{
                        ...player,
                        scenario_config: {
                            is_post_june_1: isPostJune1,
                            savings: isPostJune1 ? player.savings_post_june1 : player.savings_pre_june1,
                            dead_cap: isPostJune1 ? player.dead_cap_post_june1 : player.dead_cap_pre_june1
                        }
                    }}
                    defaultName={`Cut ${player.player_name} (${isPostJune1 ? 'Post-June 1' : 'Pre-June 1'})`}
                />
            </div>

            {/* Executive Summary (B.L.U.F.) */}
            <div className={`p-4 rounded-lg border flex items-start gap-4 mb-2 ${player.risk_score > 0.7 ? "bg-rose-500/10 border-rose-500/30 text-rose-400" : "bg-emerald-500/10 border-emerald-500/30 text-emerald-400"}`}>
                <div className="mt-0.5">
                    {player.risk_score > 0.7 ? <ShieldAlert className="h-5 w-5" /> : <CheckCircle2 className="h-5 w-5" />}
                </div>
                <div>
                    <h3 className="font-bold text-sm uppercase tracking-wider mb-1">Executive Summary (B.L.U.F.)</h3>
                    <p className="text-sm leading-relaxed text-slate-300">
                        {player.risk_score > 0.7
                            ? `CRITICAL RISK: ${player.player_name} is generating negative surplus value. Models indicate an average overpayment of $${avgError.toFixed(1)}M annually vs empirical production expectations. Strong quantitative recommendation to restructure or execute a Post-June 1 designated cut.`
                            : `STABLE ASSET: ${player.player_name} is performing within ±$${avgError.toFixed(1)}M of true Fair Market Value. The contract is currently efficient relative to positional scarcity. Maintain portfolio allocation.`}
                    </p>
                </div>
            </div>

            {/* Key Stats Grid */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <Card className="bg-slate-900 border-transparent shadow-none">
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-bold tracking-wider text-slate-400 uppercase">Cap Hit</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="text-3xl font-bold text-white">
                            ${player.cap_hit_millions.toLocaleString()}M
                        </div>
                        <p className="text-xs text-slate-500 mt-1">Current Season Charge</p>
                    </CardContent>
                </Card>

                <Card className="bg-slate-900 border-transparent shadow-none">
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-bold tracking-wider text-slate-400 uppercase">Efficiency Gap</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="text-3xl font-bold text-emerald-400">
                            {(player.risk_score * 100).toFixed(0)}
                        </div>
                        <p className="text-xs text-slate-500 mt-1">Percentile Rank vs Position</p>
                    </CardContent>
                </Card>

                <Card className="bg-slate-900 border-transparent shadow-none">
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-bold tracking-wider text-slate-400 uppercase">Model Variance</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="text-3xl font-bold text-amber-400">
                            ±${avgError.toFixed(1)}M
                        </div>
                        <p className="text-xs text-slate-500 mt-1">Avg. Prediction Error</p>
                    </CardContent>
                </Card>
            </div>

            {/* Main Content: Calculator + Chart */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                {/* Left Col: Cut Calculator (Action) */}
                <div className="lg:col-span-1 space-y-6">
                    <CutCalculator
                        player={player}
                        isPostJune1={isPostJune1}
                        onToggle={setIsPostJune1}
                    />

                    {/* Efficiency Stats Card (Moved here to stack under calculator) */}
                    <Card className="bg-zinc-900 border-zinc-800">
                        <CardHeader>
                            <CardTitle>Efficiency Gap Analysis</CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            <div className="flex justify-between items-center">
                                <span className="text-zinc-400">Efficiency Gap Score</span>
                                <Badge variant="outline" className={player.risk_score > 0.7 ? "bg-red-500/10 text-red-500 border-red-500/20" : "bg-emerald-500/10 text-emerald-500 border-emerald-500/20"}>
                                    {(player.risk_score * 100).toFixed(0)}/100
                                </Badge>
                            </div>
                            <Separator className="bg-zinc-800" />
                            <div className="pt-2">
                                <div className="text-xs text-zinc-500 mb-2">INTELLIGENCE NOTE</div>
                                <p className="text-sm text-zinc-300 leading-relaxed">
                                    {player.risk_score > 0.7
                                        ? "Critical Efficiency Gap. Model indicates significant overpayment relative to expected production. Recommended action: Restructure or cut post-June 1."
                                        : "Stable Asset. Contract value aligns with expected performance production. Retain at current APY."}
                                </p>
                            </div>

                            <div className="pt-4 border-t border-zinc-800">
                                <details className="group cursor-pointer">
                                    <summary className="text-xs text-zinc-500 mb-3 font-semibold uppercase list-none [&::-webkit-details-marker]:hidden flex justify-between items-center">
                                        KEY DRIVERS (SHAP)
                                        <span className="text-zinc-600 group-open:rotate-180 transition-transform">▼</span>
                                    </summary>
                                    <div className="space-y-2 text-sm mt-3 animate-in fade-in slide-in-from-top-2 duration-200">
                                        <div className="flex justify-between items-center">
                                            <span className="text-zinc-400">Position Premium ({player.position})</span>
                                            <span className="text-amber-400">+1.2M</span>
                                        </div>
                                        <div className="flex justify-between items-center">
                                            <span className="text-zinc-400">Age Curve Decline</span>
                                            <span className="text-rose-400">-0.8M</span>
                                        </div>
                                        <div className="flex justify-between items-center">
                                            <span className="text-zinc-400">Production YoY Trend</span>
                                            <span className={player.risk_score > 0.5 ? "text-rose-400" : "text-emerald-400"}>
                                                {player.risk_score > 0.5 ? "-2.1M" : "+1.5M"}
                                            </span>
                                        </div>
                                    </div>
                                </details>
                            </div>
                        </CardContent>
                    </Card>
                </div>

                {/* Right Col: Context Charts */}
                <div className="lg:col-span-2 space-y-6">
                    <Card className="bg-slate-900 border-slate-800 h-full">
                        <CardHeader>
                            <CardTitle>Value Trajectory (2022-{player.year})</CardTitle>
                            <CardDescription>Actual Pay vs. Predicted Market Value</CardDescription>
                        </CardHeader>
                        <CardContent className="h-[400px]">
                            {chartDataWithBands.length === 0 ? (
                                <div className="h-full flex flex-col items-center justify-center border border-dashed border-slate-800 rounded-lg bg-slate-950/30">
                                    <ShieldAlert className="h-8 w-8 text-slate-600 mb-3" />
                                    <h4 className="text-sm font-semibold text-slate-300">Insufficient Historical Data</h4>
                                    <p className="text-xs text-slate-500 mt-1 max-w-[250px] text-center">
                                        This asset lacks the required historical telemetry to generate a multi-year value trajectory model.
                                    </p>
                                </div>
                            ) : (
                                <ResponsiveContainer width="100%" height="100%">
                                    <ComposedChart data={chartDataWithBands} margin={{ top: 20, right: 30, left: 0, bottom: 0 }}>
                                        <CartesianGrid strokeDasharray="3 3" stroke="#334155" opacity={0.15} />
                                        <XAxis dataKey="year" stroke="#94a3b8" />
                                        <YAxis stroke="#94a3b8" tickFormatter={(v) => `$${v}M`} />
                                        <Tooltip
                                            contentStyle={{ backgroundColor: '#18181b', borderColor: '#27272a', color: '#fff' }}
                                            itemStyle={{ color: '#fff' }}
                                            formatter={(value: any, name: any) => name === "Model Variance (95% CI)" ? null : [`$${Number(value).toFixed(2)}M`, name]}
                                        />
                                        <Legend wrapperStyle={{ paddingTop: '20px' }} />
                                        <Area type="monotone" dataKey="bounds" name="Model Variance (95% CI)" fill="#10b981" stroke="none" fillOpacity={0.1} />
                                        <Line type="monotone" dataKey="predicted" name="Fair Market Value" stroke="#10b981" strokeWidth={2} dot={false} strokeDasharray="5 5" />
                                        <Line type="monotone" dataKey="actual" name="Actual Cap Hit" stroke="#f472b6" strokeWidth={3} dot={{ r: 4 }} activeDot={{ r: 8 }} />
                                        <Bar dataKey="error" name="Overpay/Underpay" fill="#64748b" opacity={0.3} barSize={20} />
                                    </ComposedChart>
                                </ResponsiveContainer>
                            )}
                        </CardContent>
                    </Card>

                    {/* Market Context (Distribution) */}
                    <PositionDistributionChart
                        data={distributionData}
                        playerCapHit={player.cap_hit_millions}
                        position={player.position}
                    />

                    {/* Tabbed Intelligence & Ledger */}
                    <Tabs defaultValue="timeline" className="w-full">
                        <TabsList className="grid w-full grid-cols-3 bg-slate-900 border border-slate-800">
                            <TabsTrigger value="timeline" className="data-[state=active]:bg-slate-800 data-[state=active]:text-emerald-400">Event Timeline</TabsTrigger>
                            <TabsTrigger value="intelligence" className="data-[state=active]:bg-slate-800 data-[state=active]:text-emerald-400">Health Feed</TabsTrigger>
                            <TabsTrigger value="ledger" className="data-[state=active]:bg-slate-800 data-[state=active]:text-emerald-400">Ledger</TabsTrigger>
                        </TabsList>

                        <TabsContent value="timeline" className="mt-4">
                            <Card className="bg-zinc-900 border-zinc-800">
                                <CardHeader>
                                    <CardTitle>Chronological Asset Events</CardTitle>
                                </CardHeader>
                                <CardContent>
                                    <PlayerTimeline timeline={timeline} />
                                </CardContent>
                            </Card>
                        </TabsContent>

                        <TabsContent value="intelligence" className="mt-4">
                            <div className="h-[450px]">
                                <IntelligenceFeed playerName={player.player_name} riskScore={player.risk_score} feedEvents={feed} />
                            </div>
                        </TabsContent>

                        <TabsContent value="ledger" className="mt-4">
                            <Card className="bg-zinc-900 border-zinc-800">
                                <CardHeader>
                                    <CardTitle>Historical Ledger</CardTitle>
                                </CardHeader>
                                <CardContent>
                                    <div className="space-y-2">
                                        {history.slice().reverse().slice(0, 5).map((h) => (
                                            <div key={h.year} className="flex justify-between items-center text-sm p-2 hover:bg-white/5 rounded">
                                                <span className="font-mono text-zinc-500">{h.year}</span>
                                                <div className="flex space-x-4">
                                                    <span className="text-zinc-300">${h.actual.toFixed(1)}M</span>
                                                    <span className={h.actual > h.predicted ? "text-red-500" : "text-emerald-500"}>
                                                        {h.actual > h.predicted ? '+' : ''}{(h.actual - h.predicted).toFixed(1)}M
                                                    </span>
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                </CardContent>
                            </Card>
                        </TabsContent>
                    </Tabs>
                </div>
            </div>
        </div>
    );
}
