"use client"

import { useDroppable } from "@dnd-kit/core"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Switch } from "@/components/ui/switch"
import { ArrowRightLeft, X, Banknote } from "lucide-react"

export function TradeSimulationZone({
    assetsA,
    assetsB,
    teamA,
    teamB,
    onRemoveAsset,
    onToggleRestructure,
    onSimulate
}: {
    assetsA: any[],
    assetsB: any[],
    teamA: string,
    teamB: string,
    onRemoveAsset: (id: string, team: 'A' | 'B') => void,
    onToggleRestructure?: (id: string, team: 'A' | 'B') => void,
    onSimulate: () => void
}) {
    const { setNodeRef: setNodeRefA, isOver: isOverA } = useDroppable({
        id: 'team-a-trade-zone',
        data: { team: 'A' }
    })

    const { setNodeRef: setNodeRefB, isOver: isOverB } = useDroppable({
        id: 'team-b-trade-zone',
        data: { team: 'B' }
    })

    const totalCapA = assetsA.reduce((acc, a) => acc + a.cap_hit_millions, 0)
    const totalCapB = assetsB.reduce((acc, a) => acc + a.cap_hit_millions, 0)

    return (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Team A Trading Zone */}
            <Card ref={setNodeRefA} className={`border-dashed border-2 min-h-[200px] transition-colors ${isOverA ? 'border-emerald-500 bg-emerald-500/10' : 'border-muted'}`}>
                <CardHeader className="pb-2">
                    <CardTitle className="text-xs font-mono uppercase text-muted-foreground">Assets from {teamA || "Team A"}</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                    {assetsA.map(asset => (
                        <div key={asset.id} className="flex items-center justify-between p-2 bg-secondary rounded-md text-sm">
                            <span>{asset.name} ({asset.position})</span>
                            <div className="flex items-center gap-2">
                                {/* Restructure Toggle (Only for players with significant cap) */}
                                {asset.type === 'player' && asset.cap_hit_millions > 2 && onToggleRestructure && (
                                    <div className="flex items-center space-x-2 mr-2">
                                        <Switch
                                            id={`restructure-${asset.id}`}
                                            checked={!!asset.isRestructured}
                                            onChange={() => onToggleRestructure(asset.id, 'A')}
                                            className={asset.isRestructured ? 'bg-emerald-500' : 'bg-input'}
                                        />
                                        {asset.isRestructured && <Banknote className="h-4 w-4 text-emerald-500 animate-pulse" />}
                                    </div>
                                )}
                                <span className={`font-mono ${asset.isRestructured ? 'text-emerald-500 font-bold decoration-dashed' : 'text-emerald-500'}`}>
                                    ${Number(asset.cap_hit_millions).toFixed(2)}M
                                </span>
                                <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => onRemoveAsset(asset.id, 'A')}>
                                    <X className="h-3 w-3" />
                                </Button>
                            </div>
                        </div>
                    ))}
                    {assetsA.length === 0 && (
                        <div className="text-center py-10 text-muted-foreground text-xs italic">
                            Drag assets here from {teamA || "Team A"}
                        </div>
                    )}
                </CardContent>
            </Card>

            {/* Team B Trading Zone */}
            <Card ref={setNodeRefB} className={`border-dashed border-2 min-h-[200px] transition-colors ${isOverB ? 'border-blue-500 bg-blue-500/10' : 'border-muted'}`}>
                <CardHeader className="pb-2">
                    <CardTitle className="text-xs font-mono uppercase text-muted-foreground">Assets from {teamB || "Team B"}</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                    {assetsB.map(asset => (
                        <div key={asset.id} className="flex items-center justify-between p-2 bg-secondary rounded-md text-sm">
                            <span>{asset.name} ({asset.position})</span>
                            <div className="flex items-center gap-2">
                                {/* Restructure Toggle */}
                                {asset.type === 'player' && asset.cap_hit_millions > 2 && onToggleRestructure && (
                                    <div className="flex items-center space-x-2 mr-2">
                                        <Switch
                                            id={`restructure-${asset.id}`}
                                            checked={!!asset.isRestructured}
                                            onChange={() => onToggleRestructure(asset.id, 'B')}
                                            className={asset.isRestructured ? 'bg-blue-500' : 'bg-input'}
                                        />
                                        {asset.isRestructured && <Banknote className="h-4 w-4 text-blue-500 animate-pulse" />}
                                    </div>
                                )}
                                <span className="font-mono text-blue-500">${Number(asset.cap_hit_millions).toFixed(2)}M</span>
                                <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => onRemoveAsset(asset.id, 'B')}>
                                    <X className="h-3 w-3" />
                                </Button>
                            </div>
                        </div>
                    ))}
                    {assetsB.length === 0 && (
                        <div className="text-center py-10 text-muted-foreground text-xs italic">
                            Drag assets here from {teamB || "Team B"}
                        </div>
                    )}
                </CardContent>
            </Card>

            {/* Summary & Action */}
            <Card className="md:col-span-2 border-border bg-card">
                <CardContent className="p-4 flex flex-col md:flex-row items-center justify-between gap-4">
                    <div className="flex gap-8">
                        <div>
                            <p className="text-xs text-muted-foreground uppercase font-mono">Team A Sending</p>
                            <p className="text-xl font-bold text-emerald-500">${totalCapA.toFixed(1)}M</p>
                        </div>
                        <div className="flex items-center">
                            <ArrowRightLeft className="h-6 w-6 text-muted-foreground" />
                        </div>
                        <div>
                            <p className="text-xs text-muted-foreground uppercase font-mono">Team B Sending</p>
                            <p className="text-xl font-bold text-blue-500">${totalCapB.toFixed(1)}M</p>
                        </div>
                    </div>
                    <Button
                        disabled={assetsA.length === 0 && assetsB.length === 0}
                        onClick={onSimulate}
                        className="bg-emerald-500 hover:bg-emerald-600 text-white font-bold px-8 h-12"
                    >
                        SIMULATE EXCHANGE
                    </Button>
                </CardContent>
            </Card>
        </div>
    )
}
