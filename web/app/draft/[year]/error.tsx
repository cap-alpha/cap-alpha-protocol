"use client";

import { AlertTriangle } from "lucide-react";
import Link from "next/link";

export default function DraftError({
    error,
    reset,
}: {
    error: Error & { digest?: string };
    reset: () => void;
}) {
    return (
        <div className="flex min-h-[60vh] flex-col items-center justify-center p-4 text-center gap-5">
            <AlertTriangle className="h-12 w-12 text-rose-500" />
            <h2 className="text-2xl font-black uppercase tracking-tight text-white">
                Draft data unavailable
            </h2>
            <p className="text-zinc-400 max-w-sm">
                We couldn&apos;t load draft predictions for this year. The data feed may be
                temporarily unavailable.
            </p>
            <p className="hidden" aria-hidden="true">
                {error.message}
            </p>
            <div className="flex gap-3">
                <button
                    onClick={() => reset()}
                    className="px-4 py-2 bg-white text-black font-bold uppercase text-sm tracking-wider rounded-lg hover:bg-zinc-200 transition-colors"
                >
                    Retry
                </button>
                <Link
                    href="/"
                    className="px-4 py-2 border border-white/10 bg-white/5 text-white font-bold uppercase text-sm tracking-wider rounded-lg hover:bg-white/10 transition-colors"
                >
                    Home
                </Link>
            </div>
        </div>
    );
}
