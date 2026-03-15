---
description: Run massive-scale Combinatorial Fuzzing & Adversarial Playwright Testing (10,000+ Permutations)
---

# Webtest: Adversarial UI/UX & Security Testing Workflow

This workflow is designed to break the application. It goes beyond happy-path testing by generating massive combinatorial loads (Personas × URLs × Malformed Inputs × RBAC Overrides) and creating manual verification scripts for the Product Owner.

## Phase 0: Pre-Flight UI/UX Architect Review
1. **Strategy Alignment**: Before generating the 10,000+ tests, the `product_design_architect` and `data_viz_ux` personas must review the combinatorial constraints.
2. **Approval**: The UX Architects must sign off that the tests are asserting the correct "Golden Paths" and that the malicious vectors don't compromise the intended user experience.

## Phase 1: Automated Combinatorial Fuzzing (The "10,000" Tests)
1. **Generate the Fuzzer**: Write a Playwright test generator script (`web/tests/e2e/fuzz_generator.ts`) that programmatically constructs thousands of test cases.
   - **Vectors**: All active URLs (`/`, `/dashboard/gm`, `/teams/x`, `/player/y`).
   - **Personas**: Mocked Clerk JWTs for `SignedOut`, `Fan_Free_Tier`, `GM_Pro_Tier`, `Bettor_Pro_Tier`, `Agent_Pro_Tier`.
   - **Attack Surfaces**: XSS string injections in `GlobalSearch`, forced API mutations without tokens, direct URL forcing bypassing `<PersonaSwitcher>`.
2. **Execute and Fix**: 
   - Run the Playwright suite.
   - For every failure (500s, 401 leaks, DOM hydration errors), the AI must immediately analyze the trace, apply the fix to the source code, and re-run.

## Phase 2: Manual Adversarial Scripting
1. **Generate Developer Script**: Create `web/tests/manual_adversarial_verification.sh`.
   - This script must contain rapid-fire `curl` commands and local instructions for the User to manually attempt to break the server based on the patched vulnerabilities. 
2. **Handoff**: Present this script to the User to run natively.

## Phase 3: The "Typical User Flow" Walkthrough
1. **Document the Golden Paths**: Create a markdown artifact (`typical_user_flow.md`) detailing the exact step-by-step clicks for:
   - A free Fan voting on a player.
   - A paid GM analyzing the Alpha spread and running a trade simulation.
2. **AI Co-Pilot Walkthrough**: The AI must manually walk through these exact flows via Playwright or Local Dev assertions, fixing any layout or UX clunkiness found along the way, while the User follows along.

## Phase 4: Post-Flight UI/UX Design Audit
1. **The Polish Pass**: After the application survives the 10,000+ tests, invoke the `/ui_ux_audit` slash command.
2. **Final Verification**: The designers will review the patched source code and actual DOM renders to ensure the "Security Fixes" didn't destroy the "Executive Suite" aesthetic (e.g., ensuring error boundary fallbacks look premium).
