"use client";

import { useState } from "react";
import { Share2, ExternalLink, Check } from "lucide-react";
import { cn } from "@/lib/utils";

export interface PredictionShareButtonProps {
    predictionId: string;
    className?: string;
}

export function PredictionShareButton({
    predictionId,
    className,
}: PredictionShareButtonProps) {
    const [copied, setCopied] = useState(false);

    const appUrl =
        (typeof process !== "undefined" &&
            process.env.NEXT_PUBLIC_APP_URL) ||
        "https://capalphaprotocol.com";

    const shareUrl = `${appUrl}/ledger?prediction=${predictionId}`;
    const ogUrl = `/api/og/prediction/${encodeURIComponent(predictionId)}`;

    const handleCopy = async () => {
        try {
            await navigator.clipboard.writeText(shareUrl);
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        } catch {
            // Clipboard unavailable — graceful degradation
        }
    };

    return (
        <div className={cn("inline-flex items-center gap-1", className)}>
            {/* Copy share URL button */}
            <button
                onClick={handleCopy}
                aria-label={copied ? "Link copied!" : "Copy share link"}
                title={copied ? "Copied!" : "Copy share link"}
                className={cn(
                    "inline-flex items-center gap-1 text-[10px] font-mono transition-colors border rounded px-2 py-0.5",
                    copied
                        ? "text-emerald-400 border-emerald-500/40 bg-emerald-500/10"
                        : "text-zinc-400 border-zinc-800 hover:text-emerald-400 hover:border-emerald-500/40"
                )}
            >
                {copied ? (
                    <>
                        <Check className="w-2.5 h-2.5" />
                        Copied!
                    </>
                ) : (
                    <>
                        <Share2 className="w-2.5 h-2.5" />
                        Share
                    </>
                )}
            </button>

            {/* Open OG card link */}
            <a
                href={ogUrl}
                target="_blank"
                rel="noopener noreferrer"
                aria-label="Open share card"
                title="Open share card image"
                className="inline-flex items-center gap-0.5 text-[10px] font-mono text-zinc-400 hover:text-zinc-400 transition-colors border border-transparent hover:border-zinc-700 rounded px-1 py-0.5"
            >
                Card <ExternalLink className="w-2.5 h-2.5" />
            </a>
        </div>
    );
}
