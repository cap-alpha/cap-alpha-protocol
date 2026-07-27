import * as React from "react"

import { cn } from "@/lib/utils"

const maxWidthBySize = {
    "2xl": "max-w-2xl",
    "3xl": "max-w-3xl",
    "4xl": "max-w-4xl",
    "5xl": "max-w-5xl",
    "6xl": "max-w-6xl",
    "7xl": "max-w-7xl",
} as const

export interface PageContainerProps
    extends React.HTMLAttributes<HTMLDivElement> {
    /**
     * Matches the ad hoc `max-w-{size} mx-auto` wrapper divs already
     * hand-written across app/**\/page.tsx (see web/DESIGN_AUDIT.md §3.1).
     * Pick the size the page already uses — this component removes
     * copy-pasted boilerplate, it does not change any page's layout.
     */
    size?: keyof typeof maxWidthBySize
}

/**
 * Standard page-content wrapper. Every page currently hand-writes
 * `<div className="max-w-Nxl mx-auto ...">` with one of 5 different N
 * values and no shared component — this is that shared component.
 */
const PageContainer = React.forwardRef<HTMLDivElement, PageContainerProps>(
    ({ size = "5xl", className, ...props }, ref) => (
        <div
            ref={ref}
            className={cn(maxWidthBySize[size], "mx-auto", className)}
            {...props}
        />
    )
)
PageContainer.displayName = "PageContainer"

export { PageContainer }
