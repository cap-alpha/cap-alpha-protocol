"use client";

import { useEffect, useRef, useState } from "react";

export type AnimatedCounterProps = {
    value: number;
    decimals?: number;
    suffix?: string;
    prefix?: string;
    duration?: number;
    className?: string;
};

/**
 * AnimatedCounter
 *
 * Counts up from 0 (or a previous value) to `value` on mount / value change.
 * Respects `prefers-reduced-motion` — renders the final value immediately.
 *
 * Pure RAF/easing implementation — no framer-motion dependency.
 * Only animates the numeric text value (no layout-triggering properties).
 */
export function AnimatedCounter({
    value,
    decimals = 0,
    suffix = "",
    prefix = "",
    duration = 1000,
    className,
}: AnimatedCounterProps) {
    const [displayStr, setDisplayStr] = useState(
        `${prefix}${value.toFixed(decimals)}${suffix}`
    );
    const [opacity, setOpacity] = useState(0.5);

    const inViewRef = useRef(false);
    const containerRef = useRef<HTMLSpanElement | null>(null);
    const rafRef = useRef<number | null>(null);
    const prefersReducedMotion = useRef(false);

    // Detect reduced-motion preference (client-side only)
    useEffect(() => {
        const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
        prefersReducedMotion.current = mq.matches;
    }, []);

    function runAnimation(toValue: number) {
        if (prefersReducedMotion.current) {
            setDisplayStr(`${prefix}${toValue.toFixed(decimals)}${suffix}`);
            setOpacity(1);
            return;
        }

        const startTime = performance.now();

        function tick(now: number) {
            const elapsed = now - startTime;
            const progress = Math.min(elapsed / duration, 1);
            // ease-out cubic
            const eased = 1 - Math.pow(1 - progress, 3);
            const current = toValue * eased;
            setDisplayStr(`${prefix}${current.toFixed(decimals)}${suffix}`);
            setOpacity(0.5 + 0.5 * eased);

            if (progress < 1) {
                rafRef.current = requestAnimationFrame(tick);
            }
        }

        if (rafRef.current) cancelAnimationFrame(rafRef.current);
        rafRef.current = requestAnimationFrame(tick);
    }

    useEffect(() => {
        // Show final value immediately for SSR / non-visible state
        setDisplayStr(`${prefix}${value.toFixed(decimals)}${suffix}`);

        if (typeof window === "undefined") return;

        const el = containerRef.current;
        if (!el) return;

        const observer = new IntersectionObserver(
            (entries) => {
                if (entries[0].isIntersecting && !inViewRef.current) {
                    inViewRef.current = true;
                    runAnimation(value);
                }
            },
            { threshold: 0.2 }
        );
        observer.observe(el);

        return () => {
            observer.disconnect();
            if (rafRef.current) cancelAnimationFrame(rafRef.current);
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [value, decimals, prefix, suffix]);

    // When value changes after initial mount, animate to new value
    useEffect(() => {
        if (inViewRef.current) {
            runAnimation(value);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [value]);

    return (
        <span
            ref={containerRef}
            className={className}
            style={{ opacity, transition: "opacity 0.3s" }}
        >
            {displayStr}
        </span>
    );
}
