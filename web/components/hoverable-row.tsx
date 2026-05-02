"use client";

import { useReducedMotion, motion } from "framer-motion";

export type HoverableRowProps = {
    children: React.ReactNode;
    className?: string;
    onClick?: () => void;
};

/**
 * HoverableRow
 *
 * Wraps children in a Framer Motion div that applies a subtle lift on hover:
 *   - translateY(-1px)  — transform only, no layout cost
 *   - box-shadow emergence — visual depth cue
 *   - 150ms ease transition
 *
 * Respects `prefers-reduced-motion` — skips the transform when user prefers
 * reduced motion; box-shadow still fades in softly via opacity-safe approach.
 */
export function HoverableRow({ children, className = "", onClick }: HoverableRowProps) {
    const shouldReduceMotion = useReducedMotion();

    const hoverVariants = shouldReduceMotion
        ? {
              rest: { boxShadow: "0 0 0 0 transparent" },
              hover: {
                  boxShadow: "0 0 0 1px rgba(52, 211, 153, 0.15)",
              },
          }
        : {
              rest: {
                  y: 0,
                  boxShadow: "0 0 0 0 transparent",
              },
              hover: {
                  y: -1,
                  boxShadow:
                      "0 4px 16px -2px rgba(0,0,0,0.45), 0 0 0 1px rgba(52, 211, 153, 0.12)",
              },
          };

    return (
        <motion.div
            className={className}
            initial="rest"
            whileHover="hover"
            animate="rest"
            variants={hoverVariants}
            transition={{ duration: 0.15, ease: "easeOut" }}
            onClick={onClick}
            style={{ willChange: "transform" }}
        >
            {children}
        </motion.div>
    );
}
