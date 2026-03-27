'use client'

import { AlertTriangle, Home, RefreshCcw } from "lucide-react";
import Link from 'next/link';

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  return (
    <div className="flex min-h-[80vh] flex-col items-center justify-center p-4 text-center">
        <div className="relative mb-8 mt-10">
            <div className="absolute inset-0 bg-rose-500/20 blur-2xl rounded-full"></div>
            <AlertTriangle className="relative h-24 w-24 text-rose-500/80" />
        </div>
        <h1 className="text-4xl md:text-5xl font-black uppercase tracking-tighter text-white mb-4">
            System Unavailable
        </h1>
        <p className="text-zinc-400 max-w-md mb-8 text-lg">
            We are currently executing pipeline maintenance or experiencing unprecedented load. The data bridges are actively attempting stabilization.
        </p>
        
        {/* Hidden debug string for devs */}
        <p className="hidden" aria-hidden="true">{error.message}</p>

        <div className="flex flex-col sm:flex-row gap-4">
            <button
                className="px-6 py-3 bg-white text-black font-bold uppercase tracking-wider rounded-lg hover:bg-zinc-200 transition-colors flex items-center justify-center gap-2 shadow-lg shadow-white/5"
                onClick={() => reset()}
            >
                <RefreshCcw className="h-4 w-4" /> Retry Connection
            </button>
            <Link 
                href="/" 
                className="px-6 py-3 border border-white/10 bg-white/5 text-white font-bold uppercase tracking-wider rounded-lg hover:bg-white/10 transition-colors flex items-center justify-center gap-2"
            >
                <Home className="h-4 w-4" /> Return Home
            </Link>
        </div>
    </div>
  )
}
