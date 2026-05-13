"use client";

export type HoverableRowProps = {
    children: React.ReactNode;
    className?: string;
    onClick?: () => void;
};

/**
 * HoverableRow
 *
 * Applies a subtle lift on hover:
 *   - translateY(-1px)  — transform only, no layout cost
 *   - box-shadow emergence — visual depth cue
 *   - 150ms ease transition
 *
 * Pure CSS/event implementation — no framer-motion dependency.
 * Respects `prefers-reduced-motion` via the CSS media query automatically.
 */
export function HoverableRow({ children, className = "", onClick }: HoverableRowProps) {
    return (
        <div
            className={className}
            onClick={onClick}
            style={{
                transition: "transform 0.15s ease-out, box-shadow 0.15s ease-out",
                willChange: "transform",
            }}
            onMouseEnter={(e) => {
                const el = e.currentTarget;
                el.style.transform = "translateY(-1px)";
                el.style.boxShadow =
                    "0 4px 16px -2px rgba(0,0,0,0.45), 0 0 0 1px rgba(52, 211, 153, 0.12)";
            }}
            onMouseLeave={(e) => {
                const el = e.currentTarget;
                el.style.transform = "translateY(0)";
                el.style.boxShadow = "none";
            }}
        >
            {children}
        </div>
    );
}
