"use client"

import * as React from "react"
import {
    ColumnDef,
    ColumnFiltersState,
    SortingState,
    VisibilityState,
    flexRender,
    getCoreRowModel,
    getFilteredRowModel,
    getPaginationRowModel,
    getSortedRowModel,
    useReactTable,
} from "@tanstack/react-table"
import { ArrowUpDown, ChevronDown, MoreHorizontal } from "lucide-react"
import Link from "next/link"

import { Button } from "@/components/ui/button"
import {
    DropdownMenu,
    DropdownMenuCheckboxItem,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuLabel,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Input } from "@/components/ui/input"
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table"
import { Badge } from "@/components/ui/badge"
import { NFL_TEAMS, slugify } from "@/lib/utils"
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from "@/components/ui/tooltip"
import { CapSparkline } from "@/components/ui/cap-sparkline"

export type PlayerMetric = {
    player_name: string
    team: string
    position: string
    cap_hit_millions: number
    risk_score: number
    surplus_value: number
}

export const columns: ColumnDef<PlayerMetric>[] = [
    {
        accessorKey: "player_name",
        header: "Player",
        cell: ({ row }) => (
            <div className="capitalize font-medium">
                <Link
                    href={`/player/${encodeURIComponent(slugify(row.getValue("player_name") as string))}`}
                    className="hover:underline hover:text-emerald-400 transition-colors"
                >
                    {row.getValue("player_name")}
                </Link>
            </div>
        ),
    },
    {
        accessorKey: "team",
        header: "Team",
        cell: ({ row }) => (
            <div className="uppercase text-xs font-bold">
                <Link
                    href={`/team/${encodeURIComponent(row.getValue("team"))}`}
                    className="text-muted-foreground hover:text-emerald-400 hover:underline transition-colors px-2 py-1 -ml-2 rounded-sm"
                >
                    {row.getValue("team")}
                </Link>
            </div>
        ),
    },
    {
        accessorKey: "position",
        header: "Pos",
        cell: ({ row }) => (
            <div className="uppercase text-xs">{row.getValue("position")}</div>
        ),
    },
    {
        accessorKey: "cap_hit_millions",
        header: ({ column }) => {
            return (
                <div className="flex w-full justify-end items-center gap-2">
                    <TooltipProvider>
                        <Tooltip>
                            <TooltipTrigger asChild>
                                <Button
                                    variant="ghost"
                                    className="flex items-center gap-1 hover:bg-transparent px-0"
                                    onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
                                >
                                    Cap Hit ($M)
                                    <ArrowUpDown className="h-4 w-4" />
                                </Button>
                            </TooltipTrigger>
                            <TooltipContent>
                                <p>Current season salary cap charge</p>
                            </TooltipContent>
                        </Tooltip>
                    </TooltipProvider>
                </div>
            )
        },
        cell: ({ row }) => {
            const amount = parseFloat(row.getValue("cap_hit_millions"))
            const formatted = new Intl.NumberFormat("en-US", {
                style: "currency",
                currency: "USD",
                maximumFractionDigits: 2,
            }).format(amount)

            return <div className="text-right font-medium">{formatted}M</div>
        },
    },
    {
        accessorKey: "risk_score",
        header: ({ column }) => {
            return (
                <div className="flex w-full justify-end items-center gap-2">
                    <TooltipProvider>
                        <Tooltip>
                            <TooltipTrigger asChild>
                                <Button
                                    variant="ghost"
                                    className="flex items-center gap-1 hover:bg-transparent px-0"
                                    onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
                                >
                                    Efficiency Gap
                                    <ArrowUpDown className="h-4 w-4" />
                                </Button>
                            </TooltipTrigger>
                            <TooltipContent>
                                <p>Percentile rank of contract efficiency relative to production</p>
                            </TooltipContent>
                        </Tooltip>
                    </TooltipProvider>
                </div>
            )
        },
        cell: ({ row }) => {
            const risk = parseFloat(row.getValue("risk_score"))
            return (
                <div className="text-right">
                    <Badge variant={risk > 0.7 ? "destructive" : risk < 0.3 ? "secondary" : "default"}
                        className={risk < 0.3 ? "bg-emerald-500 hover:bg-emerald-600 text-white" : ""}>
                        {(risk * 100).toFixed(0)}/100
                    </Badge>
                </div>
            )
        }
    },
    {
        id: "trend",
        header: "Cost Trend",
        cell: ({ row }) => {
            // @ts-ignore
            const history = row.original.history || [];
            return (
                <div className="flex justify-end">
                    <CapSparkline data={history} />
                </div>
            )
        }
    },
    {
        accessorKey: "surplus_value",
        header: ({ column }) => {
            return (
                <div className="flex w-full justify-end items-center gap-2">
                    <TooltipProvider>
                        <Tooltip>
                            <TooltipTrigger asChild>
                                <Button
                                    variant="ghost"
                                    className="flex items-center gap-1 hover:bg-transparent px-0"
                                    onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
                                >
                                    Value ($M)
                                    <ArrowUpDown className="h-4 w-4" />
                                </Button>
                            </TooltipTrigger>
                            <TooltipContent>
                                <p>Net Performance Value (Surplus)</p>
                            </TooltipContent>
                        </Tooltip>
                    </TooltipProvider>
                </div>
            )
        },
        cell: ({ row }) => {
            const amount = parseFloat(row.getValue("surplus_value"))
            const formatted = new Intl.NumberFormat("en-US", {
                style: "currency",
                currency: "USD",
                maximumFractionDigits: 2,
            }).format(amount)

            const isPositive = amount > 0

            return <div className={`text-right font-mono ${isPositive ? "text-emerald-500" : "text-rose-500"}`}>{formatted}M</div>
        },
    },
]

export const RosterGrid = React.memo(function RosterGrid({ data, initialSearch = "" }: { data: PlayerMetric[], initialSearch?: string }) {
    const [sorting, setSorting] = React.useState<SortingState>([])
    const [columnFilters, setColumnFilters] = React.useState<ColumnFiltersState>(
        initialSearch ? [{ id: "player_name", value: initialSearch }] : []
    )
    const [columnVisibility, setColumnVisibility] = React.useState<VisibilityState>({})
    const [rowSelection, setRowSelection] = React.useState({})
    const [teamFilter, setTeamFilter] = React.useState<string>("all")
    const [posFilter, setPosFilter] = React.useState<string>("all")
    const [confFilter, setConfFilter] = React.useState<string>("all")
    const [capFilter, setCapFilter] = React.useState<string>("all")

    // Filter Logic
    const filteredData = React.useMemo(() => {
        return data.filter(item => {
            const matchesTeam = teamFilter === "all" || item.team === teamFilter
            const matchesPos = posFilter === "all" || item.position === posFilter
            // @ts-ignore
            const matchesConf = confFilter === "all" || (NFL_TEAMS[item.team] === confFilter)

            let matchesCap = true
            if (capFilter === "high") matchesCap = item.cap_hit_millions >= 2.0
            if (capFilter === "mid") matchesCap = item.cap_hit_millions >= 1.0 && item.cap_hit_millions < 2.0
            if (capFilter === "low") matchesCap = item.cap_hit_millions < 1.0

            return matchesTeam && matchesPos && matchesConf && matchesCap
        })
    }, [data, teamFilter, posFilter, confFilter, capFilter])

    // Keyboard Shortcut: ESC to reset
    React.useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.key === "Escape") {
                setTeamFilter("all")
                setPosFilter("all")
                setConfFilter("all")
                setCapFilter("all")
            }
        }
        window.addEventListener("keydown", handleKeyDown)
        return () => window.removeEventListener("keydown", handleKeyDown)
    }, [])

    const table = useReactTable({
        data: filteredData,
        columns,
        onSortingChange: setSorting,
        onColumnFiltersChange: setColumnFilters,
        getCoreRowModel: getCoreRowModel(),
        getPaginationRowModel: getPaginationRowModel(),
        getSortedRowModel: getSortedRowModel(),
        getFilteredRowModel: getFilteredRowModel(),
        onColumnVisibilityChange: setColumnVisibility,
        onRowSelectionChange: setRowSelection,
        state: {
            sorting,
            columnFilters,
            columnVisibility,
            rowSelection,
        },
    })

    // Get unique values for dropdowns
    const uniqueTeams = Array.from(new Set(data.map(d => d.team))).sort()
    const uniquePositions = Array.from(new Set(data.map(d => d.position))).sort()

    return (
        <div className="w-full">
            <div className="flex items-center py-4 gap-2">
                <Input
                    placeholder="Search players..."
                    value={(table.getColumn("player_name")?.getFilterValue() as string) ?? ""}
                    onChange={(event) =>
                        table.getColumn("player_name")?.setFilterValue(event.target.value)
                    }
                    className="max-w-sm"
                />

                {/* Conference Filter */}
                <select
                    className="h-10 w-[120px] rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                    value={confFilter}
                    onChange={(e) => setConfFilter(e.target.value)}
                >
                    <option value="all">All Conf</option>
                    <option value="AFC">AFC</option>
                    <option value="NFC">NFC</option>
                </select>

                {/* Team Filter */}
                <select
                    className="h-10 w-[100px] rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                    value={teamFilter}
                    onChange={(e) => setTeamFilter(e.target.value)}
                >
                    <option value="all">All Teams</option>
                    {uniqueTeams.map(t => (
                        <option key={t} value={t}>{t}</option>
                    ))}
                </select>

                {/* Position Filter */}
                <select
                    className="h-10 w-[100px] rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                    value={posFilter}
                    onChange={(e) => setPosFilter(e.target.value)}
                >
                    <option value="all">All Pos</option>
                    {uniquePositions.map(p => (
                        <option key={p} value={p}>{p}</option>
                    ))}
                </select>

                {/* Cap Tier Filter */}
                <select
                    className="h-10 w-[130px] rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                    value={capFilter}
                    onChange={(e) => setCapFilter(e.target.value)}
                >
                    <option value="all">All Caps</option>
                    <option value="high">High (&gt;$2M)</option>
                    <option value="mid">Mid ($1-2M)</option>
                    <option value="low">Low (&lt;$1M)</option>
                </select>

                {(teamFilter !== "all" || posFilter !== "all" || confFilter !== "all" || capFilter !== "all" || (table.getColumn("player_name")?.getFilterValue() as string)?.length > 0) && (
                    <Button
                        variant="ghost"
                        onClick={() => {
                            setTeamFilter("all")
                            setPosFilter("all")
                            setConfFilter("all")
                            setCapFilter("all")
                            table.getColumn("player_name")?.setFilterValue("")
                        }}
                        className="h-10 px-2 lg:px-3"
                    >
                        Reset
                        <span className="ml-2 text-xs text-muted-foreground hidden lg:inline-block">
                            (Esc)
                        </span>
                    </Button>
                )}

                <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                        <Button variant="outline" className="ml-auto">
                            Columns <ChevronDown className="ml-2 h-4 w-4" />
                        </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                        {table
                            .getAllColumns()
                            .filter((column) => column.getCanHide())
                            .map((column) => {
                                return (
                                    <DropdownMenuCheckboxItem
                                        key={column.id}
                                        className="capitalize"
                                        checked={column.getIsVisible()}
                                        onCheckedChange={(value) =>
                                            column.toggleVisibility(!!value)
                                        }
                                    >
                                        {column.id}
                                    </DropdownMenuCheckboxItem>
                                )
                            })}
                    </DropdownMenuContent>
                </DropdownMenu>
            </div>
            <div className="rounded-md border">
                <Table>
                    <TableHeader>
                        {table.getHeaderGroups().map((headerGroup) => (
                            <TableRow key={headerGroup.id}>
                                {headerGroup.headers.map((header) => {
                                    return (
                                        <TableHead key={header.id}>
                                            {header.isPlaceholder
                                                ? null
                                                : flexRender(
                                                    header.column.columnDef.header,
                                                    header.getContext()
                                                )}
                                        </TableHead>
                                    )
                                })}
                            </TableRow>
                        ))}
                    </TableHeader>
                    <TableBody>
                        {table.getRowModel().rows?.length ? (
                            table.getRowModel().rows.map((row) => (
                                <TableRow
                                    key={row.id}
                                    data-state={row.getIsSelected() && "selected"}
                                >
                                    {row.getVisibleCells().map((cell) => (
                                        <TableCell key={cell.id}>
                                            {flexRender(
                                                cell.column.columnDef.cell,
                                                cell.getContext()
                                            )}
                                        </TableCell>
                                    ))}
                                </TableRow>
                            ))
                        ) : (
                            <TableRow>
                                <TableCell
                                    colSpan={columns.length}
                                    className="h-24 text-center"
                                >
                                    No results.
                                </TableCell>
                            </TableRow>
                        )}
                    </TableBody>
                </Table>
            </div>
            <div className="flex items-center justify-end space-x-2 py-4">
                <div className="flex-1 text-sm text-muted-foreground">
                    {table.getFilteredSelectedRowModel().rows.length} of{" "}
                    {table.getFilteredRowModel().rows.length} row(s) selected.
                </div>
                <div className="space-x-2">
                    <Button
                        variant="outline"
                        size="sm"
                        onClick={() => table.previousPage()}
                        disabled={!table.getCanPreviousPage()}
                    >
                        Previous
                    </Button>
                    <Button
                        variant="outline"
                        size="sm"
                        onClick={() => table.nextPage()}
                        disabled={!table.getCanNextPage()}
                    >
                        Next
                    </Button>
                </div>
            </div>
        </div>
    )
})
