"use client"

import * as React from "react"
import { getTradeableAssets, getTeams } from "@/app/actions"
import { ScrollArea } from "@/components/ui/scroll-area"
import { DraggablePlayerCard } from "./draggable-player-card"
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select"
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Search, Filter, ArrowUpDown } from "lucide-react"
import { NFL_CONFERENCES, TEAM_TO_CONFERENCE } from "@/lib/constants"
import { Badge } from "@/components/ui/badge"

type SortOption = "cap" | "dead" | "surplus";

export function TeamAssetColumn({ title, onTeamChange, onAssetSelect }: { title: string, onTeamChange?: (team: string) => void, onAssetSelect?: (asset: any) => void }) {
    const [teams, setTeams] = React.useState<string[]>([])
    const [selectedTeam, setSelectedTeam] = React.useState<string>("")
    const [conferenceFilter, setConferenceFilter] = React.useState<"ALL" | "AFC" | "NFC">("ALL")
    const [searchQuery, setSearchQuery] = React.useState("")
    const [assets, setAssets] = React.useState<any[]>([])
    const [sortBy, setSortBy] = React.useState<SortOption>("cap")
    const [isSearching, setIsSearching] = React.useState(false)

    React.useEffect(() => {
        getTeams().then(setTeams)
    }, [])

    // Filter teams based on conference
    const filteredTeams = React.useMemo(() => {
        if (conferenceFilter === "ALL") return teams;
        return teams.filter(t => TEAM_TO_CONFERENCE[t] === conferenceFilter);
    }, [teams, conferenceFilter]);

    // Fetch Logic
    React.useEffect(() => {
        const fetchAssets = async () => {
            setIsSearching(true);
            try {
                // Scenario 1: Search Active (Global Search)
                if (searchQuery.length >= 3) {
                    // Fetch ALL assets if no team selected, or filter selected team?
                    // "Search for individual player" implies global lookup capability.
                    // If a team IS selected, search within it. If NOT, search all.

                    const data = await getTradeableAssets(selectedTeam || undefined); // Pass undefined to get all
                    const filtered = data.filter((a: any) =>
                        a.name.toLowerCase().includes(searchQuery.toLowerCase())
                    );
                    setAssets(sortAssets(filtered, sortBy));
                }
                // Scenario 2: Team Selected (No Search)
                else if (selectedTeam) {
                    const data = await getTradeableAssets(selectedTeam);
                    setAssets(sortAssets(data, sortBy));
                }
                // Scenario 3: Initial State (Empty)
                else {
                    setAssets([]);
                }
            } finally {
                setIsSearching(false);
            }
        };

        // Debounce search
        const timeoutId = setTimeout(fetchAssets, 300);
        return () => clearTimeout(timeoutId);

    }, [selectedTeam, searchQuery, sortBy]);

    // Notify parent on team change
    React.useEffect(() => {
        if (onTeamChange) onTeamChange(selectedTeam);
    }, [selectedTeam, onTeamChange]);

    const sortAssets = (data: any[], criteria: SortOption) => {
        const sorted = [...data];
        switch (criteria) {
            case "cap":
                return sorted.sort((a, b) => b.cap_hit_millions - a.cap_hit_millions);
            case "dead":
                return sorted.sort((a, b) => b.dead_cap_millions - a.dead_cap_millions);
            case "surplus":
                return sorted.sort((a, b) => b.surplus_value - a.surplus_value);
            default:
                return sorted;
        }
    }

    const handleSortChange = (val: string) => {
        const criteria = val as SortOption;
        setSortBy(criteria);
        setAssets(sortAssets(assets, criteria));
    }

    return (
        <Card className="flex flex-col h-[700px] border-border bg-slate-900/50 backdrop-blur-sm">
            <CardHeader className="pb-3 space-y-3">
                <div className="flex items-center justify-between">
                    <CardTitle className="text-sm font-mono uppercase tracking-widest text-emerald-500">{title}</CardTitle>
                    <div className="flex items-center text-[10px] text-muted-foreground gap-1">
                        <ArrowUpDown className="h-3 w-3" />
                        <span>SORT</span>
                    </div>
                </div>


                {/* Search Bar */}
                <div className="relative">
                    <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
                    <Input
                        placeholder="Search Player..."
                        className="pl-8 bg-background/50 border-white/10 text-xs text-white placeholder:text-muted-foreground/50"
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                    />
                </div>

                {/* Filters */}
                <div className="grid grid-cols-5 gap-2">

                    {/* Conference Filter */}
                    <Select onValueChange={(v: any) => {
                        setConferenceFilter(v);
                        setSelectedTeam(""); // Reset team on conference change
                    }} value={conferenceFilter}>
                        <SelectTrigger className="col-span-1 bg-background/50 border-white/10 text-[10px] px-1 text-center font-bold">
                            <SelectValue placeholder="CONF" >{conferenceFilter === 'ALL' ? 'ALL' : conferenceFilter}</SelectValue>
                        </SelectTrigger>
                        <SelectContent>
                            <SelectItem value="ALL">ALL</SelectItem>
                            <SelectItem value="AFC">AFC</SelectItem>
                            <SelectItem value="NFC">NFC</SelectItem>
                        </SelectContent>
                    </Select>

                    {/* Team Selector */}
                    <Select onValueChange={setSelectedTeam} value={selectedTeam} disabled={teams.length === 0}>
                        <SelectTrigger className="col-span-3 bg-background/50 border-white/10 text-white text-xs">
                            <SelectValue placeholder="SELECT FRANCHISE" />
                        </SelectTrigger>
                        <SelectContent className="max-h-[300px]">
                            {filteredTeams.map((team) => (
                                <SelectItem key={team} value={team}>
                                    <span className="font-mono mr-2 text-muted-foreground">{TEAM_TO_CONFERENCE[team]}</span>
                                    {team}
                                </SelectItem>
                            ))}
                        </SelectContent>
                    </Select>

                    {/* Sort */}
                    <Select onValueChange={handleSortChange} value={sortBy}>
                        <SelectTrigger className="col-span-1 bg-background/50 border-white/10 text-xs px-1 text-center">
                            <SelectValue placeholder="Sort" />
                        </SelectTrigger>
                        <SelectContent align="end">
                            <SelectItem value="cap">$ Cap</SelectItem>
                            <SelectItem value="dead">$ Dead</SelectItem>
                            <SelectItem value="surplus">Value</SelectItem>
                        </SelectContent>
                    </Select>
                </div>
            </CardHeader>
            <CardContent className="flex-1 overflow-hidden p-0 relative">
                <div className="absolute inset-0 bg-gradient-to-b from-black/20 via-transparent to-transparent pointer-events-none z-10" />
                <ScrollArea className="h-full px-4 pb-4">
                    {assets.length > 0 ? (
                        <div className="space-y-2">
                            {/* Search Context Source */}
                            {!selectedTeam && searchQuery.length >= 3 && (
                                <div className="text-[10px] text-emerald-500 uppercase font-mono mb-2 text-center">
                                    Global Search Results
                                </div>
                            )}

                            {assets.map((asset) => (
                                <DraggablePlayerCard key={asset.id} player={asset} onSelect={onAssetSelect} />
                            ))}
                        </div>
                    ) : (
                        <div className="flex flex-col items-center justify-center h-full text-muted-foreground opacity-50">
                            <p className="text-xs font-mono uppercase">Waiting for Signal...</p>
                        </div>
                    )}
                </ScrollArea>
            </CardContent>
        </Card>
    )
}
