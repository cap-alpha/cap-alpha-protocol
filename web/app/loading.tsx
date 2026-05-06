export default function Loading() {
    return (
        <div className="flex min-h-[60vh] items-center justify-center">
            <div className="flex flex-col items-center gap-4">
                <div className="h-10 w-10 rounded-full border-2 border-emerald-500/30 border-t-emerald-500 animate-spin" />
                <p className="text-zinc-400 text-sm">Loading…</p>
            </div>
        </div>
    );
}
