---
description: Execute strict Next.js and React boundary validation before declaring any UI/UX or infrastructure task "Complete".
---

# UI/UX Preflight Verification

This workflow ensures we don't present broken Code or React Hook boundary errors to the user. Run this sequence whenever structural React, Next.js App Router, or configuration changes are made.

**1. Clean the invalid cache**
// turbo
`rm -rf .next`

**2. Check standard TypeScript safety**
// turbo
`npx tsc --noEmit`

**3. The True Boundary Test: Next.js Production Build**
// turbo
`npm run build`

*(Why? `npm run build` executes the Server Side Rendering (SSR) phase for all Server Components. Next.js local dev servers often hide or obscure `Invalid hook call` errors until runtime. A full static build is the **ONLY** way to catch boundary errors caused by missing `"use client"` directives or importing Client interfaces without `import type` into a Server component).*

**4. Linting Check**
// turbo
`npm run lint`
