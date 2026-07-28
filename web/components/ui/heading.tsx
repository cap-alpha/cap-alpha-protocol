import * as React from "react"

import { cn } from "@/lib/utils"

/**
 * Standardized page-level <h1> for long-form content pages (legal, policy,
 * docs-style pages). Establishes one canonical size/weight/tracking
 * combination instead of each page re-inventing text-3xl/text-4xl with
 * font-bold/font-extrabold/font-black ad hoc.
 *
 * This is the treatment 5 of 6 `app/legal/*` pages already agreed on
 * independently (`font-display text-3xl font-extrabold tracking-tight`) —
 * see web/DESIGN_AUDIT.md §2.3. Override via `className` for one-off needs;
 * `cn()` (tailwind-merge) resolves conflicting utilities correctly.
 */
const PageHeading = React.forwardRef<
    HTMLHeadingElement,
    React.HTMLAttributes<HTMLHeadingElement>
>(({ className, ...props }, ref) => (
    <h1
        ref={ref}
        className={cn(
            "font-display text-3xl font-extrabold tracking-tight",
            className
        )}
        {...props}
    />
))
PageHeading.displayName = "PageHeading"

// ---------------------------------------------------------------------------
// DisplayHeading / SectionHeading — #1070 Phase 2 (web/DESIGN_AUDIT.md §2.1,
// §2.2). The `fontSize` scale in tailwind.config.ts (`display-*`/`heading-*`)
// had zero consumers; 24 page-level <h1>s each hand-rolled their own
// text-Nxl/font-black/tracking combo. These two components are the "size"
// half of the token scale, mirroring PageHeading above:
//
//   - DisplayHeading — hero / marketing / trust-building pages (home,
//     pricing, verify, methodology, docs). Uses `display-*`.
//   - SectionHeading — internal app / dashboard page titles (quality,
//     status, entity, team, fantasy, scenarios, admin, dashboard/*). Uses
//     `heading-*`.
//
// `size` sets the base (mobile-first) tier. For a responsive step-up, pass
// e.g. className="sm:text-display-lg" — plain Tailwind breakpoint utilities
// compose correctly on top of the base class (same pattern as any other
// Tailwind responsive size stack). Font-family and color are intentionally
// NOT set here — Phase 2 is typography-scale only; callers keep their own
// font-family/color/case/margin via className.
// ---------------------------------------------------------------------------

type DisplaySize = "xl" | "lg" | "md"

const DISPLAY_SIZE_CLASS: Record<DisplaySize, string> = {
    xl: "text-display-xl",
    lg: "text-display-lg",
    md: "text-display-md",
}

const DisplayHeading = React.forwardRef<
    HTMLHeadingElement,
    React.HTMLAttributes<HTMLHeadingElement> & { size?: DisplaySize }
>(({ className, size = "lg", ...props }, ref) => (
    <h1
        ref={ref}
        className={cn(DISPLAY_SIZE_CLASS[size], className)}
        {...props}
    />
))
DisplayHeading.displayName = "DisplayHeading"

type SectionSize = "xl" | "lg" | "md"

const SECTION_SIZE_CLASS: Record<SectionSize, string> = {
    xl: "text-heading-xl",
    lg: "text-heading-lg",
    md: "text-heading-md",
}

const SectionHeading = React.forwardRef<
    HTMLHeadingElement,
    React.HTMLAttributes<HTMLHeadingElement> & { size?: SectionSize }
>(({ className, size = "xl", ...props }, ref) => (
    <h1
        ref={ref}
        className={cn(SECTION_SIZE_CLASS[size], className)}
        {...props}
    />
))
SectionHeading.displayName = "SectionHeading"

export { PageHeading, DisplayHeading, SectionHeading }
