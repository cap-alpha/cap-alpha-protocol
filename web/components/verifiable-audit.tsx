'use client'

import { ShieldCheck, ShieldAlert, Cpu } from "lucide-react";
import { useState } from "react";

interface AuditEntry {
    predictionPayload: string;
    recordedHash: string;
    timestamp: string;
    year?: number;
    playerName?: string;
}

interface AuditProps {
    entries: AuditEntry[];
}

export function VerifiableAudit({ entries }: AuditProps) {
    const [isVerified, setIsVerified] = useState<boolean | null>(null);

    const verifyIntegrity = async () => {
        if (!entries || entries.length === 0) return;
        
        let allValid = true;
        for (const entry of entries) {
            const signatureBase = `${entry.playerName || ''}|${entry.year || ''}|${entry.timestamp}|${entry.predictionPayload}`;
            const msgUint8 = new TextEncoder().encode(signatureBase);
            const hashBuffer = await crypto.subtle.digest('SHA-256', msgUint8);
            const hashArray = Array.from(new Uint8Array(hashBuffer));
            const hashHex = hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
            
            if (hashHex !== entry.recordedHash) {
                allValid = false;
                break;
            }
        }
        
        setIsVerified(allValid);
    };

    return (
        <div className="bg-zinc-950 border border-emerald-500/20 rounded-xl p-4 mt-8">
            <div className="flex items-center gap-2 mb-4">
                <Cpu className="h-5 w-5 text-emerald-500" />
                <h3 className="font-bold text-white tracking-widest uppercase">Cryptographic Ledger</h3>
            </div>
            
            <div className="space-y-4 mb-4 text-xs font-mono text-zinc-400 max-h-64 overflow-y-auto">
                {entries && entries.length > 0 ? entries.map((entry, idx) => (
                    <div key={idx} className="border-l-2 border-emerald-500/30 pl-3">
                        <div className="flex flex-col gap-1 mb-2">
                            <span className="text-zinc-500">Append Timestamp:</span>
                            <span className="text-emerald-400 break-all">{entry.timestamp}</span>
                        </div>
                        <div className="flex flex-col gap-1 mb-2">
                            <span className="text-zinc-500">Prediction Payload:</span>
                            <span className="bg-zinc-900 p-2 rounded break-all">{entry.predictionPayload}</span>
                        </div>
                        <div className="flex flex-col gap-1">
                            <span className="text-zinc-500">Recorded SHA-256 Hash:</span>
                            <span className="text-amber-500 break-all">{entry.recordedHash}</span>
                        </div>
                    </div>
                )) : (
                    <div className="text-zinc-500 italic">No ledger entries found for this asset.</div>
                )}
            </div>

            <button 
                onClick={verifyIntegrity}
                className="w-full bg-emerald-500/10 hover:bg-emerald-500/20 border border-emerald-500/50 text-emerald-500 font-bold uppercase tracking-wider text-sm py-2 px-4 rounded transition-colors flex items-center justify-center gap-2"
            >
                {isVerified === null ? "Verify Cryptographic Integrity" : 
                 isVerified === true ? <><ShieldCheck className="h-4 w-4" /> Integrity Verified</> : 
                 <><ShieldAlert className="h-4 w-4 text-rose-500" /> Audit Failed</>}
            </button>
        </div>
    );
}
