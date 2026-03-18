# UI/UX Persona Audit & Executive Polish (Pre-Vercel Launch)

To ensure this product meets the highest "Executive Suite" aesthetic standards (and absolutely wows your wife), we have conducted a rigorous audit utilizing the **Edward Tufte**, **Product Architect**, and **Data Viz/UX** persona principles.

## The "10-Foot Review" Assessment
Currently, the landing page is functional but falls into the "Uncanny Valley of Design"—it looks like engineering code rather than a premium, proprietary financial product. There is excessive administrative debris (borders, boxes, background grids) competing with the actual data signals.

## User Review Required
Before we write the code to implement these changes, please review the proposed aesthetic direction below. I also have two strategic questions for you:

1. **Information Hierarchy:** Since we are pitching this as an "intelligence aggregator," should we prioritize showcasing the *financial dollar impact* of our prediction (e.g., the large `-$42.5M` text) over the *textual insight* narrative, or vice-versa? What will resonate more with her: the raw math, or the story?
2. **The "Monolithic" Aesthetic:** Are you comfortable with a hyper-minimalist, "dark mode only" aesthetic that heavily relies on sharp typography and empty void space rather than colorful containment boxes and borders?

Please answer these questions so we can dial in the exact feel. 

---

## Proposed Changes (Aesthetic Refactor)

### [MODIFY] `web/components/alpha-feed-hero.tsx`
*   **The Tufte Purge:** Remove the distracting `url('/grid.svg')` background and heavy `bg-gradient-to-[...]` color splashes behind the player cards. The background should be a deep, monolithic void to allow the data to pop.
*   **Border Annihilation:** Remove the rigid `border-rose-500/30` and `border-orange-500/30` containment boxes around the `DISLOCATIONS` grid. We will use generous whitespace and typographic hierarchy to separate the assets instead.
*   **Typography Overhaul:** Enforce extreme contrast. Asset names (`name`) and financial impacts (`metric`) will become bolder and sharper, while the team/context information will drop to a lighter, muted monospace font.

### [MODIFY] `web/components/global-aggregator.tsx`
*   **Reduce Cognitive Load:** The "Tape" feed on the left currently uses `border-slate-800` and `bg-black/40` cards. We will strip the cards entirely, rendering the news as a continuous, elegant feed separated purely by whitespace and subtle `1px` lines (maximizing the Data-Ink Ratio).
*   **Premium Affordances:** The connecting `ArrowRight` icon between the Tape and the Signal feels slightly generic. We will replace it with a more sophisticated data-flow indicator or remove it entirely, relying on the natural left-to-right eye movement to imply causality.
*   **Pundit Index Refinement:** The teaser module looks a bit noisy with the amber blur background. We will sharpen this up to look like a rigorous mathematical ledger rather than a marketing banner.

## Verification Plan
After your approval, I will execute these code changes, verify the layout on mobile/desktop simulations, and immediately push the repository to Vercel via the `/deploy` command so you have a live, pixel-perfect URL to show your wife.

---

# Automated Vercel Canary/Production Tagging

To satisfy your requirement for automated canaries and tag-based production deployments, we need to bypass Vercel's default "deploy `main` to production automatically" behavior and implement a standard **GitOps release flow**.

## Proposed Strategy: Vercel CLI via GitHub Actions

By using GitHub Actions alongside the Vercel CLI, we can restrict production deployments *only* to commits that have been explicitly tagged as releases.

### 1. Vercel Configuration (User Action Required)
*   You must go to Vercel **Settings > Git** and set the **Ignored Build Step** to `exit 0;`. This disables Vercel's automatic Git hook deployments, handing full control over to our GitHub Actions.
*   You must generate a **Vercel Access Token** and copy your **Project ID / Org ID**, placing them into your GitHub Repository Secrets (`VERCEL_TOKEN`, `VERCEL_ORG_ID`, `VERCEL_PROJECT_ID`).

### 2. The Canary Workflow (`.github/workflows/canary.yml`)
*   **Trigger:** Any `push` to the `main` branch.
*   **Action:** Executes `vercel pull` and `vercel build`, then deploys to a **Preview** environment. 
*   **Result:** Every commit to `main` is immediately canaried, generating a unique preview URL without touching production.

### 3. The Production Workflow (`.github/workflows/production.yml`)
*   **Trigger:** Pushing a semantic version tag (e.g., `git tag v1.0.0 && git push origin v1.0.0`).
*   **Action:** Executes `vercel build --prod` and `vercel deploy --prebuilt --prod`.
*   **Result:** Only explicitly tagged and reviewed commits are promoted to the live production domain.

## User Action Required
If you approve this plan, please confirm. You will need to provision the Vercel tokens in GitHub Secrets before I can finalize the GitHub Actions workflows.
