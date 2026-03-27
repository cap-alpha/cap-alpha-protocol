'use client'

import { useEffect } from 'react'

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  useEffect(() => {
    // Automatically catch Webpack HMR dev server timeouts
    if (error.name === 'ChunkLoadError' || error.message.includes('Loading chunk') || error.message.includes('timeout')) {
      console.warn('Handling Next.js dev server chunk timeout automatically via soft reload...');
      window.location.reload();
      return;
    }
  }, [error]);

  return (
    <html>
      <body className="bg-black">
        <div className="flex min-h-screen flex-col items-center justify-center p-4 text-center">
            <div className="relative mb-8 mt-10">
                <div className="absolute inset-0 bg-rose-500/20 blur-2xl rounded-full"></div>
                {/* @ts-ignore */}
                <svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="relative h-24 w-24 text-rose-500/80"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>
            </div>
            <h2 className="text-4xl md:text-5xl font-black uppercase tracking-tighter text-white mb-4">Pipeline Crash</h2>
            <p className="text-zinc-400 max-w-md mb-8 text-lg">
                The global application layout threw a fatal compilation fault. We're actively remounting.
            </p>
            <button
                className="px-6 py-3 bg-white text-black font-bold uppercase tracking-wider rounded-lg hover:bg-zinc-200 transition-colors flex items-center gap-2 shadow-lg shadow-white/5"
                onClick={() => reset()}
            >
                Re-mount Application Array
            </button>
        </div>
      </body>
    </html>
  )
}
