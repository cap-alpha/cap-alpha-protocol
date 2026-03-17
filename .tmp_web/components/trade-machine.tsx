"use client"

import * as React from "react"
import { DndContext, DragEndEvent, useSensor, useSensors, PointerSensor, KeyboardSensor, TouchSensor, MeasuringStrategy } from "@dnd-kit/core"
import { TeamAssetColumn } from "./team-asset-column"
import { TradeSimulationZone } from "./trade-simulation-zone"
import { CapImpactCard } from "./cap-impact-card"
import { TradeAsset, calculateTradeImpact, generateTradeGrade, SimulationResult, generateCounterOffer } from "@/lib/trade-logic"
import { Card, CardHeader, CardTitle, CardContent, CardFooter } from "@/components/ui/card"
import { Switch } from "@/components/ui/switch"
import { Label } from "@/components/ui/label"
import { SidePanel } from "@/components/ui/side-panel"
import { TradeIntelligenceStream } from "./trade-intelligence-stream"
import { Activity, Lock, AlertTriangle, PlusCircle } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { getTradeableAssets } from "@/app/actions"
import { ApiClient, TradeProposal } from "@/lib/api-client"
import { CapImpactChart } from "./ui/cap-impact-chart"
import { VegasDashboard } from "./vegas-dashboard"
import { TradePartnerRolodex } from "./trade-partner-rolodex"
import { usePersona } from "./persona-context"
import { useUser } from "@clerk/nextjs";

export function TradeMachine() {
    const { persona } = usePersona();
    const [rolodexPlayer, setRolodexPlayer] = React.useState<any>(null);
    const [teamA, setTeamA] = React.useState("")
    const [teamB, setTeamB] = React.useState("")

    // Staging Data
    const [assetsA, setAssetsA] = React.useState<TradeAsset[]>([])
    const [assetsB, setAssetsB] = React.useState<TradeAsset[]>([])

    // Logic Configuration
    const [postJune1, setPostJune1] = React.useState(false)
    const [simulationResult, setSimulationResult] = React.useState<SimulationResult | null>(null)
    const [showIntel, setShowIntel] = React.useState(false)

    // Adversarial State
    const [counterOffer, setCounterOffer] = React.useState<TradeAsset | null>(null)
    const [isSimulating, setIsSimulating] = React.useState(false)

    // AI State
    const [isGeneratingReport, setIsGeneratingReport] = React.useState(false)
    const [aiReport, setAiReport] = React.useState<string | null>(null)
    const { user } = useUser(); // Clerk Hook

    const handleGenerateAIReport = async () => {
        if (!user) {
            // Redirect to login if using Clerk components, or just alert for MVP
            alert("Please sign in to access War Room Intelligence.");
            return;
        }

        setIsGeneratingReport(true);
        try {
            const proposal: TradeProposal = {
                team_a: teamA,
                team_b: teamB,
                team_a_assets: assetsA,
                team_b_assets: assetsB,
                config: { postJune1 }
            };

            const response = await fetch('/api/ai/scouting-report', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ tradeProposal: proposal })
            });

            if (!response.ok) throw new Error("Failed to generate report");

            const data = await response.json();
            setAiReport(data.report);
        } catch (error) {
            console.error("AI Report Error:", error);
            alert("Failed to generate report. Please try again.");
        } finally {
            setIsGeneratingReport(false);
        }
    }

    // DND Sensors
    // We use PointerSensor (mouse/touch) but TouchSensor is more specific for mobile drag
    const sensors = useSensors(
        useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
        useSensor(TouchSensor, { activationConstraint: { delay: 250, tolerance: 5 } }), // Add delay to prevent accidental drags while scrolling
        useSensor(KeyboardSensor)
    )

    // Derived Financial State
    const impactA = React.useMemo(() =>
        calculateTradeImpact(teamA || "Team A", assetsB, assetsA, postJune1),
        [teamA, assetsA, assetsB, postJune1]);

    const impactB = React.useMemo(() =>
        calculateTradeImpact(teamB || "Team B", assetsA, assetsB, postJune1),
        [teamB, assetsA, assetsB, postJune1]);


    const handleDragEnd = (event: DragEndEvent) => {
        const { active, over } = event;
        if (!over) return;

        const asset = active.data.current as TradeAsset;
        const dropZone = over.id as string;

        if (dropZone === 'team-a-trade-zone' && asset.team === teamA) {
            if (!assetsA.find(a => a.id === asset.id)) setAssetsA([...assetsA, asset]);
        }
        else if (dropZone === 'team-b-trade-zone' && asset.team === teamB) {
            if (!assetsB.find(a => a.id === asset.id)) setAssetsB([...assetsB, asset]);
        }
    }

    const removeAsset = (id: string, team: 'A' | 'B') => {
        if (team === 'A') setAssetsA(assetsA.filter(a => a.id !== id));
        else setAssetsB(assetsB.filter(a => a.id !== id));
        // Clear results on change
        setSimulationResult(null);
        setCounterOffer(null);
    }

    const toggleRestructure = (id: string, team: 'A' | 'B') => {
        const updater = (list: TradeAsset[]) => list.map(a => {
            if (a.id === id) {
                return { ...a, isRestructured: !a.isRestructured };
            }
            return a;
        });

        if (team === 'A') setAssetsA(updater(assetsA));
        else setAssetsB(updater(assetsB));

        setSimulationResult(null);
    }

    const handleSimulate = async () => {
        setIsSimulating(true);
        setCounterOffer(null);

        // 1. Construct Proposal Payload
        const proposal: TradeProposal = {
            team_a: teamA,
            team_b: teamB,
            team_a_assets: assetsA,
            team_b_assets: assetsB,
            config: { postJune1 }
        };

        try {
            // 2. Call Adversarial Engine API
            const apiResult = await ApiClient.evaluateTrade(proposal);
            const vegasImpact = await ApiClient.getVegasImpact(proposal);

            // 3. Map API Result to SimulationResult
            // Note: We still use client-side math for the 'Impacts' (Cap numbers) because that needs to be instant
            // But the GRADE and SUMMARY come from the Python brain.

            const result: SimulationResult = {
                success: true,
                grade: apiResult.grade as any, // Cast to strict type
                summary: apiResult.reason,
                impacts: {
                    [teamA]: impactA,
                    [teamB]: impactB
                },
                score: apiResult.grade === 'A+' ? 99 : apiResult.grade === 'F' ? 50 : 75, // Mock score mapping for now
                vegas_impact: vegasImpact || undefined // Add Vegas Data
            };

            setSimulationResult(result);

            // 4. Handle Rejection / Counter-Offer
            if (apiResult.status === 'rejected') {
                const counter = await ApiClient.getCounterOffer(proposal);
                if (counter) {
                    setCounterOffer(counter);
                }
            }

        } catch (error) {
            console.error("Simulation failed:", error);
        } finally {
            setIsSimulating(false);
        }
    }

    const acceptCounter = () => {
        if (!counterOffer) return;

        // Add to the LOSER'S acquired assets? No, add to the WINNER'S traded assets.
        // If Team A is loser, and Team B is winner. Team B gives CounterAsset.
        // So we add to assets of Team B (if Team B is the source).

        if (counterOffer.team === teamA) {
            setAssetsA([...assetsA, counterOffer]);
        } else {
            setAssetsB([...assetsB, counterOffer]);
        }

        setCounterOffer(null);
        setSimulationResult(null); // Force re-sim
    }

    const loadScenario = (scenario: any) => {
        setTeamA(scenario.buyer);
        setTeamB(scenario.seller);
        setAssetsA([]);
        setAssetsB([]);

        const mockPlayerAsset: TradeAsset = {
            id: scenario.player,
            name: scenario.player,
            team: scenario.seller,
            position: 'unk',
            cap_hit_millions: scenario.cap,
            dead_cap_millions: scenario.cap * 0.2,
            risk_score: 0.5,
            surplus_value: scenario.seller_gain + scenario.buyer_gain, // approximate
            type: 'player'
        };

        setAssetsB([mockPlayerAsset]);
        setShowIntel(false);
        setSimulationResult(null);
        setCounterOffer(null);
    }

    return (
        <DndContext sensors={sensors} onDragEnd={handleDragEnd} measuring={{ droppable: { strategy: MeasuringStrategy.Always } }}>
            <div className="space-y-6">

                {/* Control Bar */}
                <div className="flex items-center justify-between bg-secondary/20 p-4 rounded-lg border border-border">
                    <div className="flex items-center space-x-6">
                        <div className="flex items-center space-x-2">
                            <Switch id="post-june-1" checked={postJune1} onChange={(e: React.ChangeEvent<HTMLInputElement>) => setPostJune1(e.target.checked)} />
                            <Label htmlFor="post-june-1" className="font-mono uppercase text-xs">Post-June 1 Designation</Label>
                        </div>
                        <Button
                            variant="outline"
                            size="sm"
                            className="bg-emerald-950/20 border-emerald-500/50 text-emerald-400 hover:text-emerald-300 hover:bg-emerald-900/30"
                            onClick={() => setShowIntel(true)}
                        >
                            <Activity className="mr-2 h-4 w-4" />
                            OPEN INTEL STREAM
                        </Button>
                    </div>
                    <div className="flex items-center space-x-2 text-muted-foreground">
                        <Lock className="h-3 w-3" />
                        <span className="text-[10px] uppercase tracking-widest">Season: 2026</span>
                    </div>
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 h-full">

                    {/* Left: Team A Source */}
                    <div className="lg:col-span-3">
                        <TeamAssetColumn
                            title="Team A (Buyer)"
                            onTeamChange={setTeamA}
                            onAssetSelect={persona === 'AGENT' ? setRolodexPlayer : undefined}
                        />
                    </div>

                    {/* Center: The Exchange & Impact */}
                    <div className="lg:col-span-6 flex flex-col gap-6">

                        {persona === 'AGENT' ? (
                            <TradePartnerRolodex selectedPlayer={rolodexPlayer} />
                        ) : (
                            <>
                                {/* Simulation Zone */}
                                <TradeSimulationZone
                                    teamA={teamA}
                                    teamB={teamB}
                                    assetsA={assetsA}
                                    assetsB={assetsB}
                                    onRemoveAsset={removeAsset}
                                    onToggleRestructure={toggleRestructure}
                                    onSimulate={handleSimulate}
                                />

                                {/* Live Impact Assessment */}
                                {(teamA && teamB) && (
                                    <div className="grid grid-cols-2 gap-4">
                                        <CapImpactCard impact={impactA} title={`${teamA} Cap`} />
                                        <CapImpactCard impact={impactB} title={`${teamB} Cap`} />
                                    </div>
                                )}

                                {/* Simulation Results (Tufte Style) */}
                                {simulationResult && (
                                    <div className="col-span-12 mt-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
                                        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                                            {/* Grade Card */}
                                            <Card className="bg-slate-900 border-emerald-500/50">
                                                <CardHeader>
                                                    <CardTitle className="text-center text-4xl font-black text-emerald-400">
                                                        {simulationResult.grade}
                                                    </CardTitle>
                                                    <p className="text-center text-xs text-muted-foreground uppercase tracking-widest">Trade Grade</p>
                                                </CardHeader>
                                            </Card>

                                            {/* Tufte's Cap Impact Visual */}
                                            <Card className="bg-slate-900 border-border md:col-span-2">
                                                <CardHeader className="pb-2">
                                                    <CardTitle className="text-sm uppercase font-mono text-muted-foreground">Net Cap Impact (Savings)</CardTitle>
                                                </CardHeader>
                                                <CardContent>
                                                    <CapImpactChart
                                                        teamA={teamA}
                                                        impactA={simulationResult.impacts[teamA]?.net_cap_change || 0}
                                                        teamB={teamB}
                                                        impactB={simulationResult.impacts[teamB]?.net_cap_change || 0}
                                                    />
                                                    <p className="text-xs text-muted-foreground mt-2 text-center italic">
                                                        Positive bars indicate cap space created. Red bars indicate cap space consumed.
                                                    </p>
                                                </CardContent>
                                            </Card>
                                        </div>

                                        {/* Analysis Text */}
                                        <div className="mt-4 p-4 border border-dashed border-muted rounded-lg bg-black/20">
                                            <p className="font-mono text-sm text-center text-emerald-500/80">
                                                &quot;{simulationResult.summary}&quot;
                                            </p>
                                        </div>

                                    </div>
                                )}

                                {/* Vegas Dashboard (Bettor Persona) */}
                                {(simulationResult?.vegas_impact && teamA && teamB) && (
                                    <div className="col-span-12 mt-4 animate-in fade-in slide-in-from-bottom-4 duration-700 delay-100">
                                        <VegasDashboard
                                            teamA={teamA}
                                            impactA={simulationResult.vegas_impact[teamA]}
                                            teamB={teamB}
                                            impactB={simulationResult.vegas_impact[teamB]}
                                        />
                                    </div>
                                )}

                                {/* AI War Room Report (Freemium Feature) */}
                                {simulationResult && (
                                    <div className="col-span-12 mt-6">
                                        {!aiReport ? (
                                            <div className="flex flex-col items-center gap-2">
                                                <Button
                                                    size="lg"
                                                    onClick={handleGenerateAIReport}
                                                    disabled={isGeneratingReport || (user?.publicMetadata?.credits as number || 0) < 1}
                                                    className={cn(
                                                        "font-black tracking-wide transform transition-all px-8 py-6 text-lg",
                                                        (user?.publicMetadata?.credits as number || 0) > 0
                                                            ? "bg-amber-500 hover:bg-amber-400 text-black shadow-[0_0_30px_-5px_rgba(245,158,11,0.6)] border border-amber-300 hover:scale-105"
                                                            : "bg-slate-800 text-slate-500 border border-slate-700 cursor-not-allowed"
                                                    )}
                                                >
                                                    {isGeneratingReport ? (
                                                        <>
                                                            <Activity className="mr-2 h-5 w-5 animate-spin" />
                                                            CONSULTING ORACLE...
                                                        </>
                                                    ) : (
                                                        <>
                                                            <Lock className="mr-2 h-5 w-5" />
                                                            {(user?.publicMetadata?.credits as number || 0) > 0
                                                                ? `UNLOCK WAR ROOM INTEL (1 CREDIT)`
                                                                : `INSUFFICIENT CREDITS`
                                                            }
                                                        </>
                                                    )}
                                                </Button>
                                                <p className="text-[10px] text-muted-foreground uppercase tracking-widest">
                                                    Balance: {(user?.publicMetadata?.credits as number) || 0} Credits • Identify Hidden Cap Liabilities
                                                </p>
                                            </div>
                                        ) : (
                                            <Card className="bg-slate-950 border-purple-500/50 shadow-2xl shadow-purple-900/10 animate-in fade-in zoom-in-95 duration-500">
                                                <CardHeader>
                                                    <CardTitle className="flex items-center text-purple-400">
                                                        <Activity className="mr-2 h-5 w-5" />
                                                        War Room Intelligence Report
                                                    </CardTitle>
                                                </CardHeader>
                                                <CardContent>
                                                    <div className="prose prose-invert prose-sm max-w-none">
                                                        <div className="whitespace-pre-wrap font-mono text-emerald-50/90 leading-relaxed">
                                                            {aiReport}
                                                        </div>
                                                    </div>
                                                </CardContent>
                                                <CardFooter className="bg-purple-950/20 border-t border-purple-500/20 py-2">
                                                    <p className="text-[10px] text-purple-300/60 uppercase tracking-widest w-full text-center">
                                                        Generated by CapAlpha AI • Confidential
                                                    </p>
                                                </CardFooter>
                                            </Card>
                                        )}
                                    </div>
                                )}

                                {counterOffer && (
                                    <Card className="border-red-500 bg-red-950/20 animate-in zoom-in-95 duration-300">
                                        <CardHeader className="pb-2 border-b border-red-500/30">
                                            <div className="flex justify-between items-center">
                                                <div className="flex items-center space-x-2 text-red-500">
                                                    <AlertTriangle className="h-5 w-5" />
                                                    <CardTitle className="text-sm font-mono uppercase">Trade Rejected</CardTitle>
                                                </div>
                                                <span className="text-xs font-mono text-red-400 uppercase tracking-widest">Low Value Exchange</span>
                                            </div>
                                        </CardHeader>
                                        <CardContent className="pt-4">
                                            <p className="text-sm text-foreground/90 font-medium leading-relaxed">
                                                The {counterOffer.team} Front Office rejects your proposal. They demand additional value to bridge the gap.
                                            </p>

                                            <div className="mt-4 bg-red-950/40 border border-red-900/50 p-3 rounded-md flex justify-between items-center">
                                                <div>
                                                    <div className="text-[10px] text-red-400 uppercase font-bold mb-1">Counter-Proposal</div>
                                                    <div className="font-mono text-sm font-bold text-white">{counterOffer.name}</div>
                                                    <div className="text-[10px] text-muted-foreground">{counterOffer.position} • Cap: ${counterOffer.cap_hit_millions.toFixed(1)}M</div>
                                                </div>
                                                <Button
                                                    size="sm"
                                                    onClick={acceptCounter}
                                                    className="bg-red-600 hover:bg-red-500 text-white border-0"
                                                >
                                                    <PlusCircle className="mr-2 h-4 w-4" />
                                                    Accept Asset
                                                </Button>
                                            </div>
                                        </CardContent>
                                    </Card>
                                )}
                            </>
                        )}
                    </div>

                    {/* Right: Team B Source */}
                    <div className="lg:col-span-3">
                        <TeamAssetColumn title="Team B (Seller)" onTeamChange={setTeamB} />
                    </div>

                    <SidePanel isOpen={showIntel} onClose={() => setShowIntel(false)}>
                        <TradeIntelligenceStream
                            teamFilter={teamA || teamB}
                            onSelectScenario={loadScenario}
                        />
                    </SidePanel>
                </div>
            </div>
        </DndContext>
    )
}
