"use client"

import { useDraggable } from "@dnd-kit/core"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { GripVertical, Target } from "lucide-react"
import { CapSparkline } from "./ui/cap-sparkline"
import { generateCapHistory } from "@/lib/utils"

export function DraggablePlayerCard({ player, onSelect }: { player: any, onSelect?: (player: any) => void }) {
    const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
        id: player.id,
        data: {
            ...player
        }
    })

    const style = transform ? {
        transform: `translate3d(${transform.x}px, ${transform.y}px, 0)`,
        zIndex: isDragging ? 100 : 1,
        opacity: isDragging ? 0.5 : 1
    } : undefined

    return (
        <div ref={setNodeRef} style={style} {...listeners} {...attributes} className="mb-2 touch-none cursor-grab active:cursor-grabbing">
            <Card className="hover:border-emerald-500 transition-colors">
                <CardContent className="p-3 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <GripVertical className="h-4 w-4 text-muted-foreground" />
                        <div>
                            <div className="flex items-center gap-2">
                                <p className="font-bold text-sm uppercase">{player.name}</p>
                                {(player.cap_hit_millions > 0 && player.surplus_value === 0) && (
                                    <Badge variant="destructive" className="text-[10px] h-4 px-1 rounded-sm">DEAD</Badge>
                                )}
                            </div>
                            <p className="text-xs text-muted-foreground">{player.position} • {player.team}</p>
                        </div>
                    </div>

                    {/* Tufte Sparkline: Cap History */}
                    <div className="hidden sm:block opacity-50 hover:opacity-100 transition-opacity">
                        <CapSparkline
                            data={generateCapHistory(player.cap_hit_millions, player.risk_score)}
                            className="w-12 h-6"
                        />
                    </div>
                    <div className="text-right">
                        <p className="text-sm font-mono text-emerald-500">${Number(player.cap_hit_millions).toFixed(2)}M</p>
                        <Badge variant={player.risk_score > 0.7 ? "destructive" : "outline"} className="text-[10px] py-0 px-1">
                            RISK: {(player.cap_hit_millions > 0 && player.surplus_value === 0) ? "N/A" : player.risk_score.toFixed(2)}
                        </Badge>
                        {onSelect && (
                            <button
                                className="ml-2 p-1 hover:bg-emerald-500/20 rounded-full transition-colors"
                                onPointerDown={(e) => e.stopPropagation()}
                                onClick={(e) => {
                                    e.stopPropagation();
                                    onSelect(player);
                                }}
                                title="Find Buyers"
                            >
                                <Target className="h-4 w-4 text-emerald-500" />
                            </button>
                        )}
                    </div>
                </CardContent>
            </Card>
        </div>
    )
}
