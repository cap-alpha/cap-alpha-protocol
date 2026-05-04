export default function LedgerLoading() {
    return (
        <div className="max-w-6xl mx-auto px-4 py-8 space-y-6 animate-pulse">
            {/* Header skeleton */}
            <div className="h-8 w-48 bg-zinc-800 rounded-lg" />
            <div className="h-4 w-72 bg-zinc-800/60 rounded" />

            {/* Search bar skeleton */}
            <div className="h-11 w-full max-w-xl bg-zinc-800 rounded-xl" />

            {/* Card grid skeleton */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 mt-6">
                {Array.from({ length: 9 }).map((_, i) => (
                    <div key={i} className="rounded-xl border border-zinc-800 bg-zinc-900 p-5 space-y-3">
                        <div className="flex items-center gap-3">
                            <div className="h-10 w-10 rounded-full bg-zinc-700" />
                            <div className="space-y-1.5 flex-1">
                                <div className="h-4 w-32 bg-zinc-700 rounded" />
                                <div className="h-3 w-20 bg-zinc-800 rounded" />
                            </div>
                        </div>
                        <div className="h-3 w-full bg-zinc-800 rounded" />
                        <div className="h-3 w-3/4 bg-zinc-800 rounded" />
                        <div className="flex gap-2 pt-1">
                            <div className="h-6 w-16 bg-zinc-800 rounded-full" />
                            <div className="h-6 w-16 bg-zinc-800 rounded-full" />
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}
