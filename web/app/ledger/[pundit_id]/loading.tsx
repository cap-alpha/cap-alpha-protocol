export default function PunditLoading() {
    return (
        <div className="max-w-4xl mx-auto px-4 py-8 space-y-8 animate-pulse">
            {/* Pundit header */}
            <div className="flex items-start gap-5">
                <div className="h-20 w-20 rounded-full bg-zinc-800 shrink-0" />
                <div className="space-y-3 flex-1">
                    <div className="h-7 w-52 bg-zinc-800 rounded-lg" />
                    <div className="h-4 w-36 bg-zinc-800/60 rounded" />
                    <div className="flex gap-3">
                        <div className="h-8 w-24 bg-zinc-800 rounded-full" />
                        <div className="h-8 w-24 bg-zinc-800 rounded-full" />
                    </div>
                </div>
            </div>

            {/* Stats row */}
            <div className="grid grid-cols-3 gap-4">
                {Array.from({ length: 3 }).map((_, i) => (
                    <div key={i} className="rounded-xl border border-zinc-800 bg-zinc-900 p-4 space-y-2">
                        <div className="h-8 w-16 bg-zinc-700 rounded-lg" />
                        <div className="h-3 w-24 bg-zinc-800 rounded" />
                    </div>
                ))}
            </div>

            {/* Prediction list */}
            <div className="space-y-3">
                {Array.from({ length: 5 }).map((_, i) => (
                    <div key={i} className="rounded-xl border border-zinc-800 bg-zinc-900 p-4 space-y-2">
                        <div className="h-4 w-full bg-zinc-800 rounded" />
                        <div className="h-4 w-4/5 bg-zinc-800/60 rounded" />
                        <div className="flex gap-2 pt-1">
                            <div className="h-5 w-20 bg-zinc-800 rounded-full" />
                            <div className="h-5 w-16 bg-zinc-800 rounded-full" />
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}
