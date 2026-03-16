# Sprint 10 / Webtest Retrospective Notes

This living document tracks the vulnerabilities, UX failures, and regressions uncovered by the massive `/webtest` Combinatorial Fuzzing suite (10,000+ permutations).

Crucially, it logs *how* the failure occurred so that we can recommend new protocols for earlier phases in the NEXUS Software Development Lifecycle (SDLC).

## Vulnerabilities & Failures Log
*(To be populated as the Playwright Fuzzer executes)*

### 1. Unauthenticated Horizontal Access to Pro Dashboards
* **Failure**: The Playwright Auth Routing fuzzer (`generated_fuzz_auth_routing.spec.ts`) detected that a `SignedOut` user could force navigation directly to `/dashboard/gm` and render the War Room components, bypassing the Premium Paywall.
* **Fix Applied**: Added `/dashboard/gm(.*)`, `/dashboard/agent(.*)`, and `/dashboard/bettor(.*)` to the strictly enforced `isProtectedRoute` matcher in the Next.js `middleware.ts`.
* **Nexus Process Recommendation**: The SDLC should formally require the CFO/Security Personas to sign-off on the `middleware.ts` matcher array *before* UI components are merged into `main`. Developer focus is typically on the UI, leading to neglected Server-Side security borders.

### 2. Client-Side Context Manipulation (Freemium Bypass)
* **Failure**: Unauthenticated users could still click the 'GM' persona button on the UX layer, erroneously mutating the client-side `PersonaContext` and triggering unauthorized layout shifts without initiating an authentication flow.
* **Fix Applied**: Re-wrote `PersonaSwitcher.tsx` to conditionally wrap Pro-tier buttons inside Clerk's `<SignInButton mode="modal">`.
* **Nexus Process Recommendation**: Implementing Role-Based Views must dictate an immediate integration of the Authentication Provide (Clerk) at the Component Level, rather than relying solely on server action rejections.

## Nexus Protocol Recommendations
*(To be populated after the /webtest epic is complete)*
