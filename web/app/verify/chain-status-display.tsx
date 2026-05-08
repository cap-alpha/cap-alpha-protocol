"use client";

import { useState } from "react";
import { Check, Copy } from "lucide-react";

interface ChainStatusDisplayProps {
    hash: string | null;
}

export function ChainStatusDisplay({ hash }: ChainStatusDisplayProps) {
    const [copied, setCopied] = useState(false);

    const truncated = hash
        ? `${hash.slice(0, 16)}...${hash.slice(-8)}`
        : "—";

    const handleCopy = async () => {
        if (!hash) return;
        try {
            await navigator.clipboard.writeText(hash);
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        } catch {
            // Clipboard API unavailable (e.g., non-HTTPS dev)
        }
    };

    return (
        <div className="flex items-center gap-2 min-w-0">
            <span className="text-sm font-mono text-zinc-300 truncate flex-1">
                {truncated}
            </span>
            {hash && (
                <button
                    onClick={handleCopy}
                    aria-label="Copy full hash"
                    className="shrink-0 text-zinc-600 hover:text-emerald-400 transition-colors"
                >
                    {copied ? (
                        <Check className="w-3.5 h-3.5 text-emerald-400" />
                    ) : (
                        <Copy className="w-3.5 h-3.5" />
                    )}
                </button>
            )}
        </div>
    );
}
