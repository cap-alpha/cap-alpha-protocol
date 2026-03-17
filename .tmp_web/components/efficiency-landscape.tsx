'use client';

import * as React from 'react';

import { ResponsiveContainer, ScatterChart, Scatter, XAxis, YAxis, ZAxis, Tooltip, ReferenceLine, ReferenceArea, Cell, Label } from 'recharts';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { usePersona } from "@/components/persona-context";


interface EfficiencyLandscapeProps {
    data: {
        player_name: string;
        team: string;
        position: string;
        cap_hit_millions: number;
        surplus_value: number; // FMV
        risk_score: number;
    }[];
    teams?: {
        team: string;
        total_cap: number;
        risk_cap: number;
        count: number;
    }[];
}

export function EfficiencyLandscape({ data, teams = [] }: EfficiencyLandscapeProps) {
    const { persona } = usePersona();
    const [capFilter, setCapFilter] = React.useState<string>("high"); // Default to High Cap to reduce noise
    const [posFilter, setPosFilter] = React.useState<string>("all");

    // Zoom State
    const [refAreaLeft, setRefAreaLeft] = React.useState<string | number | null>(null);
    const [refAreaRight, setRefAreaRight] = React.useState<string | number | null>(null);
    const [left, setLeft] = React.useState<string | number>('dataMin');
    const [right, setRight] = React.useState<string | number>('dataMax');
    const [top, setTop] = React.useState<string | number>('dataMax+1');
    const [bottom, setBottom] = React.useState<string | number>('dataMin-1');

    // Filter Logic
    const chartData = React.useMemo(() => {
        if (persona === 'AGENT') {
            // Agent View: Teams (Cap Space vs Risk)
            // Cap 2024: $255.4M
            const SALARY_CAP = 255.4;
            return teams.map(t => ({
                player_name: t.team,
                team: t.team,
                position: 'TEAM',
                // X: Cap Space
                cap_hit_millions: parseFloat((SALARY_CAP - (t.total_cap / 1e6)).toFixed(1)),
                // Y: Risk Exposure
                surplus_value: parseFloat((t.risk_cap / 1e6).toFixed(1)),
                // Z: Count
                risk_score: t.count * 10, // Scale up for visibility
                efficiency: '0'
            }));
        }

        return data
            .filter(d => {
                // Cap Filter
                if (capFilter === "high" && d.cap_hit_millions < 5) return false; // Focus on major starters > $5M
                if (capFilter === "mid" && (d.cap_hit_millions < 1 || d.cap_hit_millions >= 5)) return false;
                if (capFilter === "low" && d.cap_hit_millions >= 1) return false;

                // Position Filter
                if (posFilter !== "all" && d.position !== posFilter) return false;

                // Noise reduction: trim crazy outliers if showing all
                if (d.cap_hit_millions > 70) return false;

                return true;
            })
            .map(d => ({
                ...d,
                efficiency: (d.surplus_value - d.cap_hit_millions).toFixed(1),
            }));
    }, [data, capFilter, posFilter, persona, teams]);

    const uniquePositions = Array.from(new Set(data.map(d => d.position))).sort();

    const zoom = () => {
        if (refAreaLeft === refAreaRight || refAreaRight === null || refAreaLeft === null) {
            setRefAreaLeft(null);
            setRefAreaRight(null);
            return;
        }

        // Correct order
        let l: string | number = refAreaLeft;
        let r: string | number = refAreaRight;

        if (typeof l === 'number' && typeof r === 'number' && l > r) {
            [l, r] = [r, l];
        }

        setLeft(l);
        setRight(r);
        setRefAreaLeft(null);
        setRefAreaRight(null);
    };

    const zoomOut = () => {
        setLeft('dataMin');
        setRight('dataMax');
        setTop('dataMax+1');
        setBottom('dataMin-1');
    };

    const xLabel = persona === 'AGENT' ? "Cap Space Available" : "Annual Cap Hit (Cost)";
    const yLabel = persona === 'AGENT' ? "Risk Exposure" : "Fair Market Value (Production)";
    const xName = persona === 'AGENT' ? "Cap Space" : "Cost";
    const yName = persona === 'AGENT' ? "Risk" : "Production";

    return (
        <Card className="col-span-4 bg-background border-border shadow-md">
            <CardHeader className="pb-2">
                <div className="flex flex-col gap-4">
                    <div className="flex justify-between items-start">
                        <div>
                            <CardTitle className="text-xl">
                                {persona === 'AGENT' ? 'Team Leverage Landscape' : 'Market Efficiency Landscape'}
                            </CardTitle>
                            <CardDescription>
                                {persona === 'AGENT'
                                    ? <span>Finding <span className="text-emerald-500 font-bold">Cap Space</span> vs. <span className="text-rose-500 font-bold">Risk Exposure</span>.</span>
                                    : <span>Identifying <span className="text-emerald-500 font-bold">Surplus Value</span> vs. <span className="text-rose-500 font-bold">Bad Contracts</span>.</span>
                                }
                            </CardDescription>
                        </div>
                        <div className="flex gap-2">
                            <button onClick={zoomOut} className="text-xs bg-secondary px-2 py-1 rounded hover:bg-secondary/80 transition-colors">
                                Reset Zoom
                            </button>
                            <div className="flex gap-2">
                                <select
                                    className="h-8 rounded-md border border-input bg-background px-3 text-xs"
                                    value={posFilter}
                                    onChange={(e) => setPosFilter(e.target.value)}
                                >
                                    <option value="all">All Positions</option>
                                    {uniquePositions.map(p => <option key={p} value={p}>{p}</option>)}
                                </select>

                                <select
                                    className="h-8 rounded-md border border-input bg-background px-3 text-xs"
                                    value={capFilter}
                                    onChange={(e) => setCapFilter(e.target.value)}
                                >
                                    <option value="all">All Contracts (Noisy)</option>
                                    <option value="high">High Cap ({'>'}$5M)</option>
                                    <option value="mid">Mid Tier ($1M-$5M)</option>
                                    <option value="low">Rookie/Min ({'<'}$1M)</option>
                                </select>
                            </div>
                        </div>
                    </div>

                    {/* PROMINENT LEGEND */}
                    <div className="bg-muted/30 p-3 rounded-lg border border-border grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 text-xs">
                        {/* Risk Color */}
                        <div className="flex items-center gap-4">
                            <span className="font-semibold text-muted-foreground uppercase tracking-wider">Contract Risk:</span>
                            <div className="flex gap-3">
                                <div className="flex items-center gap-1"><div className="w-3 h-3 rounded-full bg-emerald-500"></div> Low</div>
                                <div className="flex items-center gap-1"><div className="w-3 h-3 rounded-full bg-amber-400"></div> Med</div>
                                <div className="flex items-center gap-1"><div className="w-3 h-3 rounded-full bg-rose-500"></div> High</div>
                            </div>
                        </div>

                        {/* Bubble Size */}
                        <div className="flex items-center gap-4">
                            <span className="font-semibold text-muted-foreground uppercase tracking-wider">Bubble Size:</span>
                            <div className="flex items-center gap-2">
                                <div className="w-2 h-2 rounded-full bg-slate-400"></div>
                                <div className="w-3 h-3 rounded-full bg-slate-400"></div>
                                <div className="w-4 h-4 rounded-full bg-slate-400"></div>
                                <span className="text-muted-foreground italic">Larger = Higher Volatility (Consistency Score)</span>
                            </div>
                        </div>

                        {/* Interaction Hint */}
                        <div className="flex items-center gap-2 text-muted-foreground">
                            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8" /><path d="m21 21-4.3-4.3" /><path d="M11 8v6" /><path d="M8 11h6" /></svg>
                            <span>Click & Drag to Zoom</span>
                        </div>
                    </div>
                </div>
            </CardHeader>

            <CardContent className="h-[500px] w-full p-4 select-none">
                <ResponsiveContainer width="100%" height="100%">
                    <ScatterChart
                        margin={{ top: 20, right: 30, bottom: 40, left: 60 }}
                        onMouseDown={(e: any) => e && setRefAreaLeft(e.xValue)}
                        onMouseMove={(e: any) => refAreaLeft && e && setRefAreaRight(e.xValue)}
                        onMouseUp={zoom}
                    >
                        <ReferenceLine y={0} stroke="hsl(var(--border))" />
                        <ReferenceLine x={0} stroke="hsl(var(--border))" />

                        <XAxis
                            type="number"
                            dataKey="cap_hit_millions"
                            name={xName}
                            domain={[left, right]}
                            tickFormatter={(val) => `$${Math.round(Number(val))}M`}
                            allowDecimals={false}
                            allowDataOverflow
                        >
                            <Label value={xLabel} offset={0} position="bottom" style={{ fill: 'hsl(var(--muted-foreground))', fontSize: '12px', fontWeight: 500 }} />
                        </XAxis>
                        <YAxis
                            type="number"
                            dataKey="surplus_value"
                            name={yName}
                            domain={[bottom, 'auto']}
                            tickFormatter={(val) => `$${Math.round(Number(val))}M`}
                            allowDecimals={false}
                            allowDataOverflow
                        >
                            <Label
                                value={yLabel}
                                angle={-90}
                                position="insideLeft"
                                style={{ textAnchor: 'middle', fill: 'hsl(var(--muted-foreground))', fontSize: '12px', fontWeight: 500 }}
                            />
                        </YAxis>

                        <ZAxis type="number" dataKey="risk_score" range={[60, 400]} name="Risk" />

                        <Tooltip
                            cursor={{ strokeDasharray: '3 3' }}
                            content={({ active, payload }) => {
                                if (active && payload && payload.length) {
                                    const d = payload[0].payload;
                                    return (
                                        <div className="rounded-lg border bg-popover p-3 shadow-md z-50 min-w-[200px]">
                                            <div className="flex flex-col gap-1">
                                                <div className="flex justify-between items-center">
                                                    <span className="font-bold text-sm uppercase">{d.player_name}</span>
                                                    <Badge variant="outline" className="text-[10px] h-5">{d.team}</Badge>
                                                </div>
                                                <div className="text-xs text-muted-foreground">{d.position}</div>

                                                <div className="h-px bg-border my-2" />

                                                <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                                                    <span className="text-muted-foreground">Cap Cost:</span>
                                                    <span className="font-mono text-right">${d.cap_hit_millions.toFixed(2)}M</span>

                                                    <span className="text-muted-foreground">Real Value:</span>
                                                    <span className="font-mono text-right text-emerald-500">${d.surplus_value.toFixed(2)}M</span>

                                                    <span className="text-muted-foreground">Net:</span>
                                                    <span className={`font-mono text-right font-bold ${Number(d.efficiency) > 0 ? "text-emerald-500" : "text-rose-500"}`}>
                                                        {Number(d.efficiency) > 0 ? "+" : ""}{d.efficiency}M
                                                    </span>
                                                </div>
                                            </div>
                                        </div>
                                    );
                                }
                                return null;
                            }}
                        />

                        <Scatter name="Players" data={chartData} fill="#8884d8">
                            {chartData.map((entry, index) => (
                                <Cell
                                    key={`cell-${index}`}
                                    fill={entry.risk_score > 0.7 ? '#f43f5e' : entry.risk_score > 0.4 ? '#fbbf24' : '#10b981'}
                                    fillOpacity={0.8}
                                />
                            ))}
                        </Scatter>

                        {refAreaLeft && refAreaRight ? (
                            <ReferenceArea x1={refAreaLeft} x2={refAreaRight} strokeOpacity={0.3} />
                        ) : null}

                    </ScatterChart>
                </ResponsiveContainer>
            </CardContent>
        </Card>
    );
}
