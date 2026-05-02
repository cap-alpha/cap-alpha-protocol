"use client";

import { useEffect, useRef, useState } from "react";
import {
    useMotionValue,
    useSpring,
    useTransform,
    useReducedMotion,
    motion,
} from "framer-motion";

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
 * Respects `prefers-reduced-motion` — renders the final value immediately when
 * the user has opted in to reduced motion.
 *
 * Only animates `opacity` and the numeric text value (no layout-triggering
 * properties). Spring physics are tuned to complete within `duration` ms at 60fps.
 */
export function AnimatedCounter({
    value,
    decimals = 0,
    suffix = "",
    prefix = "",
    duration = 1000,
    className,
}: AnimatedCounterProps) {
    const shouldReduceMotion = useReducedMotion();
    const motionVal = useMotionValue(0);

    // Stiffness/damping tuned so spring settles near `duration` ms.
    // Higher stiffness → faster; higher damping → less overshoot.
    const stiffness = Math.round(100 * (1000 / duration));
    const spring = useSpring(motionVal, { stiffness, damping: 30, mass: 1 });

    const display = useTransform(spring, (latest) => {
        const formatted = latest.toFixed(decimals);
        return `${prefix}${formatted}${suffix}`;
    });

    // Track string value for SSR / non-motion path
    const [displayStr, setDisplayStr] = useState(
        `${prefix}${value.toFixed(decimals)}${suffix}`
    );

    const inViewRef = useRef(false);
    const containerRef = useRef<HTMLSpanElement | null>(null);

    useEffect(() => {
        if (shouldReduceMotion) {
            setDisplayStr(`${prefix}${value.toFixed(decimals)}${suffix}`);
            return;
        }

        const unsubscribe = display.on("change", (v) => setDisplayStr(v));

        // Trigger when in view via IntersectionObserver
        const el = containerRef.current;
        if (!el) return () => unsubscribe();

        const observer = new IntersectionObserver(
            (entries) => {
                if (entries[0].isIntersecting && !inViewRef.current) {
                    inViewRef.current = true;
                    motionVal.set(0);
                    spring.set(0);
                    motionVal.set(value);
                }
            },
            { threshold: 0.2 }
        );
        observer.observe(el);

        return () => {
            observer.disconnect();
            unsubscribe();
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [value, shouldReduceMotion, decimals, prefix, suffix]);

    // When value changes after initial mount, animate to new value
    useEffect(() => {
        if (shouldReduceMotion) {
            setDisplayStr(`${prefix}${value.toFixed(decimals)}${suffix}`);
            return;
        }
        if (inViewRef.current) {
            motionVal.set(value);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [value]);

    return (
        <motion.span
            ref={containerRef}
            className={className}
            // Fade in when the counter starts (opacity only — no layout recalc)
            initial={{ opacity: 0.5 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.3 }}
        >
            {displayStr}
        </motion.span>
    );
}
