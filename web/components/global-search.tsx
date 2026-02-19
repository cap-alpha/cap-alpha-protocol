"use client"

import * as React from "react"
import { Search } from "lucide-react"
import { useRouter } from "next/navigation"

import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"

export function GlobalSearch() {
    const [open, setOpen] = React.useState(false)
    const [query, setQuery] = React.useState("")
    const router = useRouter()

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

    const handleSearch = (e: React.FormEvent) => {
        e.preventDefault()
        if (query) {
            // Simple redirect to a search page or just roster?
            // For now, let's just go to the player page if exact match, or grid with filter
            router.push(`/?search=${encodeURIComponent(query)}`) // We need to wire this up in Page.tsx
            setOpen(false)
        }
    }

    return (
        <>
            <Button
                variant="outline"
                className="relative h-9 w-9 p-0 xl:h-10 xl:w-60 xl:justify-start xl:px-3 xl:py-2 text-muted-foreground bg-background/50 border-emerald-500/30 hover:border-emerald-500/50 hover:bg-emerald-500/10 transition-colors"
                onClick={() => setOpen(true)}
            >
                <Search className="h-4 w-4 xl:mr-2" />
                <span className="hidden xl:inline-flex">Search players...</span>
                <kbd className="pointer-events-none absolute right-1.5 top-1.5 hidden h-6 select-none items-center gap-1 rounded border bg-muted px-1.5 font-mono text-[10px] font-medium opacity-100 xl:flex">
                    <span className="text-xs">⌘</span>K
                </kbd>
            </Button>
            <Dialog open={open} onOpenChange={setOpen}>
                <DialogContent className="sm:max-w-[550px] bg-slate-950 border-slate-800">
                    <DialogHeader>
                        <DialogTitle className="text-slate-400 font-mono uppercase text-xs">Global Asset Search</DialogTitle>
                    </DialogHeader>
                    <form onSubmit={handleSearch} className="flex gap-2">
                        <Input
                            placeholder="Search by name, team, or position..."
                            className="bg-slate-900 border-slate-800 text-white focus-visible:ring-emerald-500"
                            value={query}
                            onChange={(e) => setQuery(e.target.value)}
                            autoFocus
                        />
                        <Button type="submit" className="bg-emerald-600 hover:bg-emerald-700 text-white">Go</Button>
                    </form>
                    <div className="py-4">
                        <p className="text-xs text-slate-500">
                            Tip: Press <kbd className="font-mono bg-slate-800 px-1 rounded">Enter</kbd> to search.
                        </p>
                    </div>
                </DialogContent>
            </Dialog>
        </>
    )
}
