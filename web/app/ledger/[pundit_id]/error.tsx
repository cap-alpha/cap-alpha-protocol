"use client";

import { AlertTriangle, ArrowLeft } from "lucide-react";
import Link from "next/link";

export default function PunditError({
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
                Couldn&apos;t load pundit
            </h2>
            <p className="text-zinc-400 max-w-sm">
                We couldn&apos;t fetch this pundit&apos;s prediction record. Try again or browse
                the full ledger.
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
                    href="/ledger"
                    className="px-4 py-2 border border-white/10 bg-white/5 text-white font-bold uppercase text-sm tracking-wider rounded-lg hover:bg-white/10 transition-colors flex items-center gap-1.5"
                >
                    <ArrowLeft className="h-4 w-4" /> Back to Ledger
                </Link>
            </div>
        </div>
    );
}
