# Typical User Flows - Gamified Consensus Engine & Persona Routing
*(Sprint 10 Co-Pilot Walkthrough)*

This document outlines the intended user paths for the newly refactored Persona-Led Architecture. As part of "Phase 3: AI Co-Pilot Walkthrough" in the `/webtest` Epic, please manually navigate these flows locally. 

**I am currently on standby.** Reply to me with any console errors, UI layout breaks, or UX friction you encounter during this walkthrough, and I will fix them immediately.

---

## Flow 1: The Freemium Landing & Gamified Hook

1. **Navigate to the Fan Dashboard**: Open `http://localhost:3000/dashboard/fan` in an incognito window (Unauthenticated).
2. **Observe the "Armchair GM" Namespace**: Ensure the page renders the `Franchise Power Rankings` and the grade-heavy `Elite Surplus Contracts`.
3. **Engage the Consensus Engine**: 
   - Locate the glowing "The Consensus Engine" section at the top of the dashboard.
   - Click one of the voting options (`Buy/Extend`, `Hold`, or `Short/Cut`) for the featured player.
   - **Expected Result**: A success state replaces the buttons showing "Prediction Logged" and awarding "+50 Alpha Credits." (Check your Next.js terminal to see the mocked `[Consensus Engine] Logged Vote` statement).

## Flow 2: The Paywall Interception

1. **Attempt Vertical Navigation**: While still on `/dashboard/fan` (and still Signed-Out), locate the `PersonaSwitcher` in the top right.
2. **The "Bettor" Persona**: Click the `Bettor` option.
   - **Expected Result**: The Clerk `<SignInButton mode="modal">` should intercept the click, rendering the authentication modal rather than allowing unauthorized client-side rendering.
3. **The "Agent" Persona**: Click the `Agent` option. 
   - **Expected Result**: Same as above; the modal intercepts.

## Flow 3: The Authorized Executive

1. **Authenticate**: Log in using a mock developer account (or sign-up) via the Clerk modal.
2. **Access the "GM" Dashboard**: Navigate to `/dashboard/gm`.
   - **Expected Result**: The routing succeeds safely. The `Trade Machine` and `War Room` components load smoothly without layout shift.
3. **Access the "Bettor" Dashboard**: Navigate to `/dashboard/bettor`.
   - **Expected Result**: Routing succeeds, rendering the Line vs Risk mapping tools.

---

**User Action Required**: Please execute these flows. If any UI elements are misaligned, or if the "Consensus Engine" glow effect breaks your 10-foot design rules, paste the feedback here. I will fix the UI dynamically.
