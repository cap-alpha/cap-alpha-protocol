export default function DraftLoading() {
    return (
        <div className="max-w-5xl mx-auto px-4 py-8 space-y-6 animate-pulse">
            {/* Title */}
            <div className="h-8 w-56 bg-zinc-800 rounded-lg" />

            {/* Year selector */}
            <div className="flex gap-2">
                {Array.from({ length: 4 }).map((_, i) => (
                    <div key={i} className="h-8 w-16 bg-zinc-800 rounded-full" />
                ))}
            </div>

            {/* Draft board rows */}
            <div className="space-y-2 mt-4">
                {Array.from({ length: 12 }).map((_, i) => (
                    <div key={i} className="flex items-center gap-4 rounded-lg border border-zinc-800 bg-zinc-900 px-4 py-3">
                        <div className="h-6 w-8 bg-zinc-700 rounded text-right" />
                        <div className="h-9 w-9 rounded-full bg-zinc-700 shrink-0" />
                        <div className="flex-1 space-y-1.5">
                            <div className="h-4 w-36 bg-zinc-700 rounded" />
                            <div className="h-3 w-24 bg-zinc-800 rounded" />
                        </div>
                        <div className="h-5 w-12 bg-zinc-800 rounded-full" />
                    </div>
                ))}
            </div>
        </div>
    );
}
