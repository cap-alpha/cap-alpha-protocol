import React from 'react';
import { ShieldCheck, Fingerprint, Activity, Clock } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { AuditEntry } from "@/app/actions";
import { ScrollArea } from "@/components/ui/scroll-area";

export function VerifiableAudit({ entries }: { entries: AuditEntry[] }) {
    if (!entries || entries.length === 0) {
        return (
            <Card className="bg-zinc-950 border-zinc-800 shadow-sm mt-4">
                <CardContent className="flex flex-col items-center justify-center p-8 text-center opacity-60">
                    <ShieldCheck className="w-8 h-8 text-zinc-600 mb-3" />
                    <h4 className="text-sm font-semibold text-zinc-300">No Cryptographic Signatures</h4>
                    <p className="text-xs text-zinc-500 mt-1 max-w-[250px]">
                        This asset has not yet been processed by the Alpha Ledger hashing engine.
                    </p>
                </CardContent>
            </Card>
        );
    }

    return (
        <Card className="bg-zinc-950 border-zinc-800 shadow-xl overflow-hidden relative mt-4">
            <div className="absolute top-0 right-0 p-4 opacity-5 pointer-events-none">
                <Fingerprint className="w-32 h-32" />
            </div>
            
            <CardHeader className="border-b border-zinc-800/50 pb-4 relative z-10 bg-zinc-900/50 select-none">
                <div className="flex items-center justify-between">
                    <div>
                        <CardTitle className="flex items-center gap-2 text-emerald-400 font-mono tracking-widest text-sm uppercase">
                            <ShieldCheck className="w-5 h-5" /> Immutable Alpha Ledger
                        </CardTitle>
                        <p className="text-xs text-zinc-500 mt-1">Cryptographic proof of a priori prediction generation. Append-only.</p>
                    </div>
                </div>
            </CardHeader>
            <CardContent className="p-0">
                <ScrollArea className="h-[400px]">
                    <div className="divide-y divide-zinc-800/50 relative z-10">
                        {entries.map((entry, idx) => (
                            <div key={idx} className="p-4 hover:bg-zinc-900/30 transition-colors group">
                                <div className="flex flex-col lg:flex-row justify-between lg:items-start gap-4">
                                    {/* Left: Metadata */}
                                    <div className="space-y-1 w-full lg:w-1/3 pt-1">
                                        <div className="flex items-center gap-2">
                                            <span className="font-mono text-sm font-bold text-zinc-300">
                                                {entry.year} WK{entry.week}
                                            </span>
                                            <span className={`text-[9px] px-1.5 py-0.5 rounded font-bold tracking-wider ${entry.payload_type === 'PREDICTION' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-amber-500/20 text-amber-400'}`}>
                                                {entry.payload_type || 'UNKNOWN'}
                                            </span>
                                        </div>
                                        <p className="text-[10px] text-zinc-500 uppercase tracking-widest flex items-center gap-1.5 mt-2">
                                            <Clock className="w-3 h-3 text-zinc-600" /> 
                                            {new Date(entry.created_at).toLocaleString()}
                                        </p>
                                        <p className="text-xs text-zinc-500 font-mono flex items-center gap-1.5 mt-1">
                                            <Activity className="w-3 h-3 text-zinc-600" />
                                            Block: <span className="text-zinc-400">{entry.merkle_root ? entry.merkle_root.substring(0, 16) + "..." : "Pending"}</span>
                                        </p>
                                    </div>

                                    {/* Right: Signature & Payload */}
                                    <div className="w-full lg:w-2/3 space-y-2">
                                        <div className="bg-zinc-950 p-3 rounded border border-zinc-800 font-mono text-xs text-emerald-500/80 break-all select-all flex flex-col gap-1.5 shadow-inner relative group-hover:border-emerald-500/40 transition-colors">
                                            <span className="text-[9px] text-zinc-600 uppercase tracking-widest flex items-center gap-1">
                                                <Fingerprint className="w-3 h-3" /> SHA-256 Signature
                                            </span>
                                            {entry.signature_hash}
                                        </div>
                                        
                                        <details className="text-xs text-zinc-500 group-hover:text-zinc-400 cursor-pointer pt-1 outline-none">
                                            <summary className="outline-none hover:text-emerald-400 transition-colors select-none font-medium">Verify Plaintext Payload</summary>
                                            <div className="mt-2 p-3 bg-zinc-900 rounded border border-zinc-800 text-[10px] sm:text-xs font-mono whitespace-pre-wrap text-zinc-300 overflow-x-auto shadow-inner">
                                                {entry.payload}
                                            </div>
                                        </details>
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                </ScrollArea>
            </CardContent>
        </Card>
    );
}
