"use client"

import * as React from "react"
import { Search } from "lucide-react"
import { useRouter } from "next/navigation"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"

export function HeroSearch() {
    const [query, setQuery] = React.useState("")
    const router = useRouter()

    const handleSearch = (e: React.FormEvent) => {
        e.preventDefault()
        if (query) {
            router.push(`/?search=${encodeURIComponent(query)}`)
        }
    }

    return (
        <form onSubmit={handleSearch} className="w-full max-w-2xl mx-auto mb-10 relative group">
            <div className="absolute inset-y-0 left-4 flex items-center pointer-events-none">
                <Search className="h-6 w-6 text-emerald-500/50 group-focus-within:text-emerald-500 transition-colors" />
            </div>
            <Input
                type="text"
                placeholder="Search players, teams, or positions..."
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                className="w-full h-16 pl-14 pr-24 text-lg bg-secondary/50 border-2 border-emerald-500/20 hover:border-emerald-500/40 focus-visible:border-emerald-500 focus-visible:ring-emerald-500/20 rounded-2xl shadow-lg transition-all"
            />
            <div className="absolute inset-y-2 right-2 flex items-center">
                <Button
                    type="submit"
                    size="lg"
                    className="h-full rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-bold tracking-wide shadow-md"
                >
                    ANALYZE
                </Button>
            </div>
        </form>
    )
}
