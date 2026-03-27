'use client'

import { AlertTriangle, Home, RefreshCcw } from "lucide-react";
import Link from 'next/link';
import Image from 'next/image';

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  return (
    <div className="flex min-h-[80vh] flex-col items-center justify-center p-4 text-center">
        <div className="relative mb-8 mt-10 w-full max-w-[500px] aspect-video mx-auto">
            <div className="absolute inset-0 bg-rose-500/20 blur-2xl rounded-full"></div>
            <Image 
               src="/butt_fumble.png" 
               alt="The Infamous Butt Fumble" 
               fill 
               className="object-cover rounded-xl border border-white/10 shadow-2xl relative z-10"
               priority
            />
        </div>
        <h1 className="text-4xl md:text-5xl font-black uppercase tracking-tighter text-white mb-4">
            Total System Butt Fumble
        </h1>
        <p className="text-zinc-400 max-w-md mb-8 text-lg mx-auto">
            Our data pipelines just ran face-first into the offensive line. We're picking up the ball and trying to salvage the drive. 
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
