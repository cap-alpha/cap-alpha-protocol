"use client";

import React, { useState } from 'react';
import { User } from 'lucide-react';

interface ImageWithFallbackProps {
    src: string;
    alt: string;
    className?: string;
    fallbackText?: string;
}

export function ImageWithFallback({ src, alt, className = "", fallbackText }: ImageWithFallbackProps) {
    const [error, setError] = useState(false);

    if (error || !src) {
        return (
            <div className={`flex flex-col items-center justify-center bg-zinc-900 border border-zinc-800 ${className}`}>
                <User className="w-12 h-12 text-zinc-700 mb-2" />
                <span className="text-zinc-600 font-bold tracking-widest uppercase text-xs">
                    {fallbackText || "NO IMAGE"}
                </span>
            </div>
        );
    }

    /* eslint-disable-next-line @next/next/no-img-element */
    return (
        <img
            src={src}
            alt={alt}
            className={className}
            onError={() => setError(true)}
            loading="lazy"
        />
    );
}
