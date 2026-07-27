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

export { PageHeading }
