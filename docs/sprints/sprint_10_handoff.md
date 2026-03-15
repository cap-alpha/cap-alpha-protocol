# Sprint 10 Handoff: Authentication & Monetization Architecture

**Epic:** PLG (Product-Led Growth), Freemium Routing, & Time-Delayed Alpha
**Status:** Planning / Pending Approval
**Primary Personas:** UX Architect, Chief Financial Officer (CFO)

---

## 1. Executive Summary & Strategy

The application is transitioning to a Persona-Led Growth model. The objective of Sprint 10 is to implement the access control matrices (RBAC) that govern these personas. 

Crucially, we must monetize the platform **smoothly and gently**, avoiding a "casino token" or "pay-per-click" feel. We are selling **Exclusive Lead Time** and **Simulation Leverage**, not data access.

### The Monetization Philosophy: "Proprietary Consensus Engine"
We are pivoting from simply "selling data" to building an **Information Arbitrage Flywheel**. This involves turning our Top-of-Funnel users (The Fans) into our most valuable proprietary dataset.
1. **The Hook (Gamified Engagement)**: Free users (Fans) log in to vote on subjective outcomes—"Is this contract an Overpay?", "Will this player be traded?", "Rate this Draft Pick." We build leaderboards determining which fans have the most predictive accuracy over time (Wisdom of the Crowds).
2. **The Proprietary Signal**: We ingest these thousands of user votes into our Data Lake (MotherDuck) to create a real-time "Public Consensus Metric." This gives us a massive edge because we no longer have to guess what the public thinks; they are telling us.
3. **The Paywall (The Arbitrage)**: The Pro Personas (GMs, Sharps, Agents) pay premium subscriptions to access the **Delta** between our ruthless algorithmic ML model (`Cap Alpha`) and the deeply emotional `Public Consensus Metric`. When the algorithm strongly disagrees with the crowd, we trigger an "Alpha Alert" for our paying executives.
4. **Platform Expansion**: Because math scales, this exact same Voting + ML Arbitrage infrastructure can be cloned for the NBA (Cap Space), NHL, and MLS with minimal code changes.

We will bifurcate the application into two enforced zones using Clerk Middleware.

### Zone A: The Top-of-Funnel (Public / Freemium)
Designed for viral growth, Reddit/Twitter screenshots, and SEO.
- **Allowed Personas**: The Armchair GM (Fan)
- **Accessible Routes**: 
  - `/` (Root Persona Selection)
  - `/dashboard/fan` (High-level grades and team rankings)
  - `/player/[id]` (Player profiles - Note: Advanced predictive metrics may feature delayed blurring)
  - `/teams/[id]` (Team profiles)
- **Friction**: Zero. No login required to browse.

### Zone B: The Alpha Console (Pro / Protected)
Designed for NFL Executives, Agents, and Sharps seeking actionable market edge.
- **Allowed Personas**: The Front Office (GM), The Agent, The Sharp (Bettor)
- **Accessible Routes**:
  - `/dashboard/gm` (Total Liability & War Room)
  - `/dashboard/agent` (Cap Targeting & Surplus Value)
  - `/dashboard/bettor` (Lead Time Arbitrage)
  - `/scenarios` (Trade Engines, Cut Calculators)
- **Friction**: Hard Clerk Middleware Paywall. Attempting to access these URLs or selecting these Personas from the root menu while unauthenticated triggers the `<SignInButton mode="modal">`.

---

## 3. Technical Implementation Plan

1. **Clerk Middleware Hardening**:
   - Update `middleware.ts` to strictly protect `/dashboard/gm`, `/dashboard/agent`, `/dashboard/bettor`, and `/scenarios`.
   - Ensure `/dashboard/fan` mathematically bypasses the `isProtectedRoute` matcher.

2. **UX Frictionless Persona Switching**:
   - Update `<PersonaSwitcher />` (and `<PersonaShowcase />`) to dynamically assess `<SignedIn>` state.
   - If a paying user is authenticated, they can hot-swap between GM, Agent, and Bettor dynamically without reloading or re-authenticating.
   - If a free user attempts to toggle a Pro persona, they intercept a clean login overlay.

3. **Verifiable Testing (SP10-3)**:
   - Create `web/tests/verify_sprint10_auth.sh`.
   - Script performs unauthenticated `curl` requests to `/dashboard/gm` (asserting `307 Redirect` to Clerk) and `/dashboard/fan` (asserting `200 OK`).

## 4. Adversarial Testing & Product Walkthrough (/webtest)

The final deliverable of this sprint relies on achieving "Production Grade" stability. This mandate is fulfilled via the `/webtest` workflow.

0. **Pre-Flight UI/UX Review**:
   - The UX Architect and UI Design personas will review the proposed testing strategy and combinatorial vectors to ensure aesthetic and user journey alignment before generation.
1. **Combinatorial Fuzzing (10,000+ Permutations)**: 
   - We will write a Playwright script (`web/tests/e2e/fuzz_generator.ts`) executing combinatorial brute force across all URLs, Persona JWT mocks, and component interactables to guarantee 0 unhandled `500` errors resulting from bad state.
2. **Manual Security Validation**:
   - The AI will produce a `manual_adversarial_verification.sh` script containing aggressive `curl` commands. The User must be able to execute these locally to prove the routing matrix cannot leak pro-level alpha.
3. **The "Typical User Flow" Walkthrough**: 
   - A final `typical_user_flow.md` document will map the exact golden paths (e.g., A Free Fan voting vs. A GM triggering a trade scenario). The AI and User will co-pilot these specific clicks natively to iron out pure UI/UX Layout friction.
4. **Post-Flight UI/UX Audit**:
   - After the tests are green, the `/ui_ux_audit` workflow will be executed to guarantee that security/stability fixes did not compromise the "Premium Executive" look and feel (e.g., ugly error boundaries).

---

## 5. Sign-Off & Approvals
*This sprint is ready for execution upon User (Product Owner) approval of the "Time-Delayed Alpha" monetization premise and the /webtest exit criteria.*
