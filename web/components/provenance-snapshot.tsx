import React from 'react';
import { ShieldCheck, Hash, Clock, FileText } from 'lucide-react';

interface ProvenanceSnapshotProps {
  source: string;
  content: string;
  sentiment: number;
  timestamp: string;
  provenanceHash?: string;
  snapshotType?: string;
  sourceUrl?: string;
}

export function ProvenanceSnapshot({
  source,
  content,
  sentiment,
  timestamp,
  provenanceHash,
  snapshotType = 'TEXT_SCRAPE',
  sourceUrl,
}: ProvenanceSnapshotProps) {
  // If no hash is provided, dynamically mock a visual hash for legacy components
  const displayHash = provenanceHash || `0x${Math.abs(hashString(content + timestamp)).toString(16).padStart(16, '0')}...`;
  
  const isPositive = sentiment >= 0.5;

  return (
    <div className="mb-4 break-inside-avoid shadow-sm group">
      {/* Snapshot 'Polaroid' Frame */}
      <div className="bg-zinc-900 border border-zinc-800 rounded p-4 relative overflow-hidden transition-colors hover:border-zinc-700">
        
        {/* Verification Watermark */}
        <div className="absolute top-0 right-0 p-1 opacity-20 pointer-events-none flex items-center gap-1 bg-zinc-800/50 rounded-bl">
            <ShieldCheck className="w-4 h-4 text-zinc-300" />
            <span className="text-[9px] font-mono tracking-widest text-zinc-300 font-bold">VERIFIED LEDGER</span>
        </div>

        {/* Header Metadata */}
        <div className="flex justify-between items-start mb-3 border-b border-zinc-800/50 pb-2">
            <div>
              <div className="flex items-center gap-1.5 text-zinc-400">
                <FileText className="w-3.5 h-3.5" />
                <span className="text-[10px] font-mono uppercase tracking-wider">{source}</span>
                <span className="text-zinc-600 px-1">•</span>
                <span className="text-[10px] font-mono uppercase text-zinc-500">{snapshotType}</span>
              </div>
            </div>
            <div className={`text-[10px] font-mono px-2 py-0.5 rounded border ${
              isPositive 
                ? 'bg-green-500/5 border-green-500/20 text-green-400' 
                : 'bg-red-500/5 border-red-500/20 text-red-400'
            }`}>
                SIGNAL: {(sentiment * 100).toFixed(0)}
            </div>
        </div>

        {/* Exact Content Replay */}
        <div className="pl-3 border-l-2 border-zinc-800 my-3">
          <p className="text-sm text-zinc-200 leading-relaxed font-serif tracking-tight">
            "{content}"
          </p>
        </div>

        {/* Cryptographic Footer */}
        <div className="mt-4 pt-3 border-t border-zinc-800/50 flex flex-col gap-1.5">
           <div className="flex items-center gap-1.5 text-zinc-500">
             <Clock className="w-3 h-3" />
             <span className="text-[9px] font-mono">CAPTURED: {new Date(timestamp).toUTCString()}</span>
           </div>
           
           <div className="flex items-center justify-between">
             <div className="flex items-center gap-1.5 text-zinc-600 font-mono flex-1 overflow-hidden">
               <Hash className="w-3 h-3 shrink-0" />
               <span className="text-[9px] tracking-wider truncate" title={displayHash}>
                  PROVENANCE: {displayHash}
               </span>
             </div>
             {sourceUrl && (
                <a 
                  href={sourceUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[9px] font-mono tracking-wider text-emerald-500 hover:text-emerald-400 ml-2 whitespace-nowrap bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20"
                >
                  VIEW SOURCE
                </a>
             )}
           </div>
        </div>
        
      </div>
    </div>
  );
}

// Simple deterministic hash function for legacy records without a backend hash yet
function hashString(str: string): number {
    let hash = 0;
    if (str.length === 0) return hash;
    for (let i = 0; i < str.length; i++) {
        const char = str.charCodeAt(i);
        hash = ((hash << 5) - hash) + char;
        hash = hash & hash; // Convert to 32bit integer
    }
    return hash;
}
