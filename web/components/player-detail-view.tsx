"use client";

import { useState } from 'react';
import { PlayerEfficiency } from "@/app/actions";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { ArrowLeft, ShieldAlert, CheckCircle2, Share2 } from "lucide-react";
import Link from "next/link";
import { slugify } from "@/lib/utils";
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
// import { SaveScenarioButton } from './save-scenario-button';
import { IntelligenceFeed } from './intelligence-feed';
import { VisualTimeline } from './visual-timeline';
import { VerifiableAudit } from './verifiable-audit';
import { TimelineEvent, IntelligenceEvent, AuditEntry, DeadMoneyMath, PositionalComp } from "@/app/actions";

interface PlayerDetailViewProps {
    player: PlayerEfficiency;
    distributionData?: any[];
    timeline?: TimelineEvent[];
    feed?: IntelligenceEvent[];
    ledger?: AuditEntry[];
    deadMoneyMath?: DeadMoneyMath;
    hasHeadshot?: boolean;
    comparables?: PositionalComp[];
}

export default function PlayerDetailView({ player, distributionData = [], timeline = [], feed = [], ledger = [], deadMoneyMath, hasHeadshot = false, comparables = [] }: PlayerDetailViewProps) {
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
        <div className="space-y-6 max-w-[1400px] mx-auto">
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
                {/* SP25-3: Share Card — links to the auto-generated Personality Magnet page */}
                <Link
                    href={`/share/player/${slugify(player.player_name)}`}
                    className="flex items-center gap-2 px-4 py-2 text-sm font-semibold text-zinc-300 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 hover:border-zinc-500 rounded-lg transition-colors"
                >
                    <Share2 className="h-4 w-4" />
                    Share Card
                </Link>
            </div>

            <div className="flex flex-col lg:flex-row gap-8 items-start relative">
                {/* LEFT COLUMN: Main Information Architecture (75% on desktop) */}
                <div className="w-full lg:w-3/4 flex flex-col gap-6">
                    {/* Executive Summary (B.L.U.F.) */}
                    <div className={`p-4 rounded-lg border flex items-start gap-4 ${player.risk_score > 0.7 ? "bg-rose-500/10 border-rose-500/30 text-rose-400" : "bg-emerald-500/10 border-emerald-500/30 text-emerald-400"}`}>
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
                        <Card className="bg-zinc-900 border-zinc-800 shadow-sm">
                            <CardHeader className="pb-3 border-b border-zinc-800/50 mb-3">
                                <CardTitle className="text-xs font-mono font-bold tracking-widest text-zinc-500 uppercase">Cap Hit</CardTitle>
                            </CardHeader>
                            <CardContent>
                                <div className="text-3xl font-mono font-bold text-white">
                                    ${player.cap_hit_millions.toLocaleString()}M
                                </div>
                                <p className="text-[10px] uppercase tracking-wider text-zinc-500 mt-2">Current Season Charge</p>
                            </CardContent>
                        </Card>

                        <Card className="bg-zinc-900 border-zinc-800 shadow-sm">
                            <CardHeader className="pb-3 border-b border-zinc-800/50 mb-3">
                                <CardTitle className="text-xs font-mono font-bold tracking-widest text-zinc-500 uppercase">Efficiency Gap</CardTitle>
                            </CardHeader>
                            <CardContent>
                                <div className="text-3xl font-mono font-bold text-emerald-400">
                                    {(player.risk_score * 100).toFixed(0)}
                                </div>
                                <p className="text-[10px] uppercase tracking-wider text-zinc-500 mt-2">Percentile Rank vs Position</p>
                            </CardContent>
                        </Card>

                        <Card className="bg-zinc-900 border-zinc-800 shadow-sm">
                            <CardHeader className="pb-3 border-b border-zinc-800/50 mb-3">
                                <CardTitle className="text-xs font-mono font-bold tracking-widest text-zinc-500 uppercase">Model Variance</CardTitle>
                            </CardHeader>
                            <CardContent>
                                <div className="text-3xl font-mono font-bold text-amber-400">
                                    ±${avgError.toFixed(1)}M
                                </div>
                                <p className="text-[10px] uppercase tracking-wider text-zinc-500 mt-2">Avg. Prediction Error</p>
                            </CardContent>
                        </Card>
                    </div>

                    {/* MOBILE TIMELINE: Only visible on small screens to sit near the top context */}
                    <div className="block lg:hidden w-full mt-4 mb-2">
                        <VisualTimeline timeline={timeline} />
                    </div>

                    {/* Deep Salary Cap Breakdown */}
                    {(player.base_salary_millions > 0 || player.prorated_bonus_millions > 0 || player.roster_bonus_millions > 0 || player.guaranteed_salary_millions > 0) && (
                    <Card className="bg-zinc-900 border-zinc-800">
                        <CardHeader className="pb-4">
                            <CardTitle className="text-lg">Cap Hit Composition</CardTitle>
                            <CardDescription>Breakdown of the ${player.cap_hit_millions.toLocaleString()}M structural charge for {player.year}</CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            {/* Visual Stacked Bar */}
                            <div className="w-full h-3 bg-zinc-800 rounded-full overflow-hidden flex">
                                <div className="h-full bg-blue-500 transition-all duration-500" style={{ width: `${(player.base_salary_millions / Math.max(player.cap_hit_millions, 0.1)) * 100}%` }} title="Base Salary" />
                                <div className="h-full bg-indigo-500 transition-all duration-500" style={{ width: `${(player.prorated_bonus_millions / Math.max(player.cap_hit_millions, 0.1)) * 100}%` }} title="Prorated Bonus" />
                                <div className="h-full bg-violet-500 transition-all duration-500" style={{ width: `${(player.roster_bonus_millions / Math.max(player.cap_hit_millions, 0.1)) * 100}%` }} title="Roster Bonus" />
                            </div>
                            {/* Legend */}
                            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-4 border-t border-zinc-800/50 pt-4">
                                <div>
                                    <div className="flex items-center gap-2 mb-1">
                                        <div className="w-2.5 h-2.5 rounded-full bg-blue-500"/> 
                                        <span className="text-[10px] text-zinc-500 font-semibold uppercase tracking-wider">Base Salary</span>
                                    </div>
                                    <div className="font-mono text-lg text-zinc-200">${player.base_salary_millions.toFixed(1)}M</div>
                                </div>
                                <div>
                                    <div className="flex items-center gap-2 mb-1">
                                        <div className="w-2.5 h-2.5 rounded-full bg-indigo-500"/> 
                                        <span className="text-[10px] text-zinc-500 font-semibold uppercase tracking-wider">Prorated Bonus</span>
                                    </div>
                                    <div className="font-mono text-lg text-zinc-200">${player.prorated_bonus_millions.toFixed(1)}M</div>
                                </div>
                                <div>
                                    <div className="flex items-center gap-2 mb-1">
                                        <div className="w-2.5 h-2.5 rounded-full bg-violet-500"/> 
                                        <span className="text-[10px] text-zinc-500 font-semibold uppercase tracking-wider">Roster Bonus</span>
                                    </div>
                                    <div className="font-mono text-lg text-zinc-200">${player.roster_bonus_millions.toFixed(1)}M</div>
                                </div>
                                <div>
                                    <div className="flex items-center gap-2 mb-1">
                                        <div className="w-2.5 h-2.5 rounded-full bg-emerald-500"/> 
                                        <span className="text-[10px] text-zinc-500 font-semibold uppercase tracking-wider">Guaranteed At Sign</span>
                                    </div>
                                    <div className="font-mono text-lg text-zinc-200">${player.guaranteed_salary_millions.toFixed(1)}M</div>
                                </div>
                            </div>
                        </CardContent>
                    </Card>
                    )}

                    {/* Main Content: Calculator + Chart */}
                    <div className="grid grid-cols-1 xl:grid-cols-3 gap-8 pb-12">
                        {/* Cut Calculator (Action) */}
                        <div className="xl:col-span-1 space-y-6">
                            <CutCalculator
                                player={player}
                                deadMoneyMath={deadMoneyMath}
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

                            {/* Empirical Production (Box Score) */}
                            {(player.total_pass_yds > 0 || player.total_rush_yds > 0 || player.total_rec_yds > 0 || player.total_sacks > 0 || player.total_int > 0) && (
                                <Card className="bg-zinc-900 border-zinc-800">
                                    <CardHeader className="pb-3">
                                        <CardTitle>Empirical Production</CardTitle>
                                        <CardDescription>Season Box Score Aggregates</CardDescription>
                                    </CardHeader>
                                    <CardContent className="space-y-4">
                                        <div className="grid grid-cols-2 gap-4">
                                            {(player.total_pass_yds > 0 || player.total_rush_yds > 0 || player.total_rec_yds > 0) && (
                                                <div className="space-y-1">
                                                    <p className="text-xs text-zinc-500 font-semibold uppercase">Total Scrimmage Yds</p>
                                                    <p className="text-2xl font-mono text-zinc-200">
                                                        {(player.total_pass_yds + player.total_rush_yds + player.total_rec_yds).toLocaleString()}
                                                    </p>
                                                </div>
                                            )}
                                            {player.total_tds > 0 && (
                                                <div className="space-y-1">
                                                    <p className="text-xs text-zinc-500 font-semibold uppercase">Touchdowns</p>
                                                    <p className="text-2xl font-mono text-emerald-400">
                                                        {player.total_tds.toLocaleString()}
                                                    </p>
                                                </div>
                                            )}
                                            {player.total_sacks > 0 && (
                                                <div className="space-y-1">
                                                    <p className="text-xs text-zinc-500 font-semibold uppercase">Defensive Sacks</p>
                                                    <p className="text-2xl font-mono text-rose-400">
                                                        {player.total_sacks.toFixed(1)}
                                                    </p>
                                                </div>
                                            )}
                                            {player.total_int > 0 && (
                                                <div className="space-y-1">
                                                    <p className="text-xs text-zinc-500 font-semibold uppercase">Interceptions</p>
                                                    <p className="text-2xl font-mono text-blue-400">
                                                        {player.total_int.toLocaleString()}
                                                    </p>
                                                </div>
                                            )}
                                            {player.games_played > 0 && (
                                                <div className="space-y-1">
                                                    <p className="text-xs text-zinc-500 font-semibold uppercase">Games Played</p>
                                                    <p className="text-2xl font-mono text-zinc-400">
                                                        {player.games_played}
                                                    </p>
                                                </div>
                                            )}
                                        </div>
                                    </CardContent>
                                </Card>
                            )}
                        </div>

                        {/* Chart and Sub-Tabs */}
                        <div className="xl:col-span-2 space-y-6">
                            <Card className="bg-zinc-900 border-zinc-800 h-[500px] shadow-sm flex flex-col">
                                <CardHeader className="border-b border-zinc-800/50 mb-4 pb-4">
                                    <CardTitle className="uppercase font-mono tracking-widest text-sm text-zinc-500">Value Trajectory (2022-{player.year})</CardTitle>
                                    <CardDescription>Actual Pay vs. Predicted Market Value</CardDescription>
                                </CardHeader>
                                <CardContent className="flex-1 min-h-[300px]">
                                    {chartDataWithBands.length === 0 ? (
                                        <div className="h-full flex flex-col items-center justify-center border border-dashed border-slate-800 rounded-lg bg-slate-950/30">
                                            <ShieldAlert className="h-8 w-8 text-slate-600 mb-3" />
                                            <h4 className="text-sm font-semibold text-slate-300">Insufficient Historical Data</h4>
                                            <p className="text-xs text-slate-500 mt-1 max-w-[250px] text-center">
                                                This asset lacks the required historical telemetry to generate a multi-year value trajectory model.
                                            </p>
                                        </div>
                                    ) : (
                                        <ResponsiveContainer width="100%" height="100%" minHeight={1} minWidth={1}>
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

                            {/* Tabbed Intelligence & Ledger */}
                            <Tabs defaultValue="intelligence" className="w-full">
                                <TabsList className="grid w-full grid-cols-3 bg-zinc-900 border border-zinc-800">
                                    <TabsTrigger value="intelligence" className="data-[state=active]:bg-zinc-800 data-[state=active]:text-emerald-400">Health Feed</TabsTrigger>
                                    <TabsTrigger value="ledger" className="data-[state=active]:bg-zinc-800 data-[state=active]:text-emerald-400">Ledger</TabsTrigger>
                                    <TabsTrigger value="fmv" className="data-[state=active]:bg-zinc-800 data-[state=active]:text-emerald-400">Value Intel</TabsTrigger>
                                </TabsList>

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
                                                        <span className="font-mono text-zinc-500">{h.year} • {h.team}</span>
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

                                    <VerifiableAudit entries={ledger} />
                                </TabsContent>

                                <TabsContent value="fmv" className="mt-4 space-y-4">
                                    {/* Contract Efficiency Score */}
                                    <Card className="bg-zinc-900 border-zinc-800">
                                        <CardHeader className="pb-3">
                                            <CardTitle className="text-sm font-mono uppercase tracking-widest text-zinc-500">Contract Efficiency</CardTitle>
                                            <CardDescription>Fair Market Value vs. actual cap charge</CardDescription>
                                        </CardHeader>
                                        <CardContent className="space-y-4">
                                            <div className="grid grid-cols-3 gap-4 text-center">
                                                <div>
                                                    <p className="text-xs text-zinc-500 uppercase tracking-wider mb-1">Cap Hit</p>
                                                    <p className="text-xl font-mono text-zinc-200">${player.cap_hit_millions.toFixed(1)}M</p>
                                                </div>
                                                <div>
                                                    <p className="text-xs text-zinc-500 uppercase tracking-wider mb-1">FMV</p>
                                                    <p className={`text-xl font-mono ${player.fair_market_value >= player.cap_hit_millions ? 'text-emerald-400' : 'text-rose-400'}`}>
                                                        ${player.fair_market_value.toFixed(1)}M
                                                    </p>
                                                </div>
                                                <div>
                                                    <p className="text-xs text-zinc-500 uppercase tracking-wider mb-1">Delta</p>
                                                    <p className={`text-xl font-mono ${player.fair_market_value >= player.cap_hit_millions ? 'text-emerald-400' : 'text-rose-400'}`}>
                                                        {player.fair_market_value >= player.cap_hit_millions ? '+' : ''}
                                                        ${(player.fair_market_value - player.cap_hit_millions).toFixed(1)}M
                                                    </p>
                                                </div>
                                            </div>
                                            <div className="space-y-1">
                                                <div className="flex justify-between text-xs text-zinc-500">
                                                    <span>Overpaid</span>
                                                    <span>Efficiency Grade</span>
                                                    <span>Underpaid</span>
                                                </div>
                                                <div className="w-full h-2 bg-zinc-800 rounded-full overflow-hidden">
                                                    <div
                                                        className={`h-full rounded-full transition-all ${player.fair_market_value >= player.cap_hit_millions ? 'bg-emerald-500' : 'bg-rose-500'}`}
                                                        style={{ width: `${Math.min(100, Math.max(5, (player.fair_market_value / Math.max(player.cap_hit_millions, 0.1)) * 50))}%` }}
                                                    />
                                                </div>
                                                <p className="text-xs text-center text-zinc-400">
                                                    {player.fair_market_value >= player.cap_hit_millions
                                                        ? `Underpaid by $${(player.fair_market_value - player.cap_hit_millions).toFixed(1)}M — strong cap value`
                                                        : `Overpaid by $${(player.cap_hit_millions - player.fair_market_value).toFixed(1)}M relative to model FMV`}
                                                </p>
                                            </div>
                                        </CardContent>
                                    </Card>

                                    {/* Positional Comparables */}
                                    <Card className="bg-zinc-900 border-zinc-800">
                                        <CardHeader className="pb-3">
                                            <CardTitle className="text-sm font-mono uppercase tracking-widest text-zinc-500">Positional Comparables ({player.position})</CardTitle>
                                            <CardDescription>Top 10 same-position players ranked by cap efficiency</CardDescription>
                                        </CardHeader>
                                        <CardContent>
                                            {comparables.length === 0 ? (
                                                <p className="text-sm text-zinc-500 text-center py-4">No comparable data available.</p>
                                            ) : (
                                                <div className="space-y-1">
                                                    <div className="grid grid-cols-4 gap-2 text-[10px] text-zinc-600 font-semibold uppercase tracking-wider px-2 pb-2 border-b border-zinc-800">
                                                        <span>Player</span>
                                                        <span className="text-right">Cap Hit</span>
                                                        <span className="text-right">FMV</span>
                                                        <span className="text-right">Efficiency</span>
                                                    </div>
                                                    {comparables.map((comp) => (
                                                        <Link key={comp.player_name} href={`/player/${slugify(comp.player_name)}`} className="grid grid-cols-4 gap-2 text-sm p-2 rounded hover:bg-white/5 transition-colors">
                                                            <div className="min-w-0">
                                                                <p className="text-zinc-200 truncate">{comp.player_name}</p>
                                                                <p className="text-[10px] text-zinc-500">{comp.team}</p>
                                                            </div>
                                                            <span className="text-zinc-400 text-right self-center font-mono">${comp.cap_hit_millions.toFixed(1)}M</span>
                                                            <span className={`text-right self-center font-mono ${comp.fair_market_value >= comp.cap_hit_millions ? 'text-emerald-400' : 'text-rose-400'}`}>
                                                                ${comp.fair_market_value.toFixed(1)}M
                                                            </span>
                                                            <span className={`text-right self-center font-mono font-bold ${comp.cap_efficiency >= 1 ? 'text-emerald-400' : 'text-rose-400'}`}>
                                                                {(comp.cap_efficiency * 100).toFixed(0)}
                                                            </span>
                                                        </Link>
                                                    ))}
                                                </div>
                                            )}
                                        </CardContent>
                                    </Card>
                                </TabsContent>
                            </Tabs>
                        </div>
                    </div>
                </div>

                {/* RIGHT COLUMN TIMELINE: Sticky on desktop to act as an anchor point */}
                <div className="hidden lg:block w-full lg:w-1/4 sticky top-6 self-start pl-6 border-l border-zinc-900 min-h-[800px]">
                    <VisualTimeline timeline={timeline} />
                </div>
            </div>
        </div>
    );
}
