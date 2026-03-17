"use client"

import * as React from "react"
import { Search, User, Shield, ChevronRight } from "lucide-react"
import { useRouter } from "next/navigation"

import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { getSearchIndex, SearchIndexItem } from "@/app/actions"

export function GlobalSearch() {
    const [open, setOpen] = React.useState(false)
    const [query, setQuery] = React.useState("")
    const [index, setIndex] = React.useState<SearchIndexItem[]>([])
    const router = useRouter()

    // Keyboard shortcut to open search
    React.useEffect(() => {
        const down = (e: KeyboardEvent) => {
            if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
                e.preventDefault()
                setOpen((open) => !open)
            }
        }
        document.addEventListener("keydown", down)
        return () => document.removeEventListener("keydown", down)
    }, [])

    // Fetch index lightweight representation when opened for first time
    React.useEffect(() => {
        if (open && index.length === 0) {
            getSearchIndex().then(setIndex).catch(console.error)
        }
    }, [open, index.length])

    const handleSelect = (url: string) => {
        setOpen(false)
        setQuery("") // Reset query on selection
        router.push(url)
    }

    // Filter logic
    const filteredResults = query.length > 0 
        ? index.filter(i => 
            i.label.toLowerCase().includes(query.toLowerCase()) || 
            i.sub.toLowerCase().includes(query.toLowerCase())
          ).slice(0, 6) // Max 6 results for clean UI
        : [];

    return (
        <>
            <Button
                variant="outline"
                className="relative h-9 w-9 p-0 xl:h-10 xl:w-60 xl:justify-start xl:px-3 xl:py-2 text-muted-foreground bg-background/50 border-emerald-500/30 hover:border-emerald-500/50 hover:bg-emerald-500/10 transition-colors"
                onClick={() => setOpen(true)}
            >
                <Search className="h-4 w-4 xl:mr-2" />
                <span className="hidden xl:inline-flex">Search players or teams...</span>
                <kbd className="pointer-events-none absolute right-1.5 top-1.5 hidden h-6 select-none items-center gap-1 rounded border bg-muted px-1.5 font-mono text-[10px] font-medium opacity-100 xl:flex">
                    <span className="text-xs">⌘</span>K
                </kbd>
            </Button>
            <Dialog open={open} onOpenChange={setOpen}>
                <DialogContent className="sm:max-w-[550px] bg-slate-950 border-slate-800 p-0 gap-0 overflow-hidden">
                    <div className="p-4 border-b border-slate-800 flex items-center gap-3">
                        <Search className="h-5 w-5 text-slate-400" />
                        <Input
                            placeholder="Type a player name (e.g., 'Dak') or team..."
                            className="bg-transparent border-none text-white focus-visible:ring-0 px-0 shadow-none text-lg placeholder:text-slate-600"
                            value={query}
                            onChange={(e) => setQuery(e.target.value)}
                            autoFocus
                        />
                    </div>
                    
                    <div className="max-h-[300px] overflow-y-auto">
                        {query.length === 0 && (
                            <div className="py-8 text-center text-slate-500 text-sm">
                                Start typing to search the Alpha Protocol database...
                            </div>
                        )}

                        {query.length > 0 && filteredResults.length === 0 && (
                            <div className="py-8 text-center text-slate-500 text-sm">
                                No assets or franchises found matching <span className="text-slate-300">"{query}"</span>.
                            </div>
                        )}

                        {filteredResults.length > 0 && (
                            <div className="py-2">
                                {filteredResults.map((item, idx) => (
                                    <button
                                        key={idx}
                                        onClick={() => handleSelect(item.url)}
                                        className="w-full flex items-center justify-between px-4 py-3 hover:bg-slate-900 transition-colors text-left group"
                                    >
                                        <div className="flex items-center gap-3">
                                            <div className="p-2 bg-slate-800 rounded group-hover:bg-emerald-500/20 group-hover:text-emerald-400 transition-colors text-slate-400">
                                                {item.type === 'player' ? <User className="h-4 w-4" /> : <Shield className="h-4 w-4" />}
                                            </div>
                                            <div>
                                                <div className="text-sm font-medium text-slate-200 group-hover:text-emerald-400 transition-colors">
                                                    {item.label}
                                                </div>
                                                <div className="text-xs text-slate-500 font-mono uppercase tracking-wider mt-0.5">
                                                    {item.sub}
                                                </div>
                                            </div>
                                        </div>
                                        <ChevronRight className="h-4 w-4 text-slate-700 group-hover:text-emerald-500 transition-colors" />
                                    </button>
                                ))}
                            </div>
                        )}
                    </div>
                    <div className="bg-slate-900/50 p-2 px-4 border-t border-slate-800 text-[10px] text-slate-500 font-mono uppercase flex justify-between">
                        <span>Search Engine: Cap Alpha Protocol</span>
                        <span><kbd className="bg-slate-800 px-1 rounded">ESC</kbd> to close</span>
                    </div>
                </DialogContent>
            </Dialog>
        </>
    )
}
