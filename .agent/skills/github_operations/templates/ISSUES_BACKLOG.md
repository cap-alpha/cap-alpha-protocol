# GitHub Issues Backlog

Use this file to populate your Kanban board (Project/Issues) on GitHub.

## Infra: Database Setup (Vercel Postgres)
**Title**: [Infra] Provision Vercel Postgres and Integrate with Next.js
**Labels**: infrastructure, backend, critical-path
**Body**:
> **Context**:
> We need a persistent storage layer for User Data (Scenarios, Saved Teams). DuckDB is transient in serverless environments.
>
> **Acceptance Criteria**:
> - [ ] Create a Vercel Postgres Database (Neon) via Vercel Dashboard.
> - [ ] Link the project to the database (`vercel link`).
> - [ ] Verify connection string `POSTGRES_URL` is available in Vercel Environment variables.
> - [ ] Update `next.config.js` if necessary for edge runtime compatibility.

## Infra: ORM Integration (Drizzle)
**Title**: [Infra] Install and Configure Drizzle ORM
**Labels**: infrastructure, backend, developer-experience
**Body**:
> **Context**:
> To interact with Postgres safely and with full TypeScript support, we will use Drizzle ORM.
>
> **Acceptance Criteria**:
> - [ ] Install `drizzle-orm` and `drizzle-kit`.
> - [ ] Create `drizzle.config.ts`.
> - [ ] Create initial `schema.ts` defining the `users` and `user_scenarios` tables.
> - [ ] Run initial migration (`drizzle-kit push` or `generate`).
> - [ ] Create a `db/index.ts` utility for easy imports.

## Feat: User Data Sync
**Title**: [Feat] Sync Clerk User/Organization Events to Postgres
**Labels**: feature, authentication, backend
**Body**:
> **Context**:
> We need to mirror Clerk user data in our database for relational integrity (User -> Scenarios).
>
> **Acceptance Criteria**:
> - [ ] Create API Route `/api/webhooks/clerk`.
> - [ ] Validate Clerk Webhook Signature (Security).
> - [ ] Handle `user.created` event: Insert row into `users` table.
> - [ ] Handle `user.updated` and `user.deleted` events.

## Feat: Save Scenarios
**Title**: [Feat] Save "Cut Scenarios" to User Profile
**Labels**: feature, product, monetization
**Body**:
> **Context**:
> Allows users to save their "Cut Calculator" results for later review. "Armchair GMs" want to build a portfolio of decisions.
>
> **Acceptance Criteria**:
> - [ ] Create API Route `POST /api/scenarios`.
> - [ ] Create Server Action `saveScenario(playerId, cutType, savings)`.
> - [ ] UI: "Save Scenario" button on Cut Calculator (mocked currently, needs implementation).
> - [ ] UI: "My Scenarios" Dashboard page.

## UAT Feedback (Sprint 2)

### UX: Onboarding Friction
**Title**: [UX] Dynamic Onboarding Interstitial (New vs Returning User)
**Labels**: ux, onboarding, friction
**Body**:
> **Context**:
> User feedback indicates the landing page is not "sold" yet.
>
> **Critique**:
> "I think it should more quickly determine if they're a new or already logged in user... if we detect the user has logged in recently, immediately show the login interstitial, but if not, let them look around... and then after a certain period of time, show them the interstitial."
>
> **Action Items**:
> - [ ] Implement "Last Seen" cookie/local storage.
> - [ ] If `last_seen < 7 days` && `!session`, auto-trigger Login Modal on load.
> - [ ] If new user, set "Free Roam" timer (e.g., 60s) before soft-triggering the "Join the Front Office" modal.

### UX: Navigation
**Title**: [UX] Global Search Bar on Homepage
**Labels**: ux, navigation, critical
**Body**:
> **Context**:
> User felt "stuck" on the homepage with a "useless" list.
>
> **Critique**:
> "I do not see a search bar at all. So I'm stuck... I just see a fairly useless list of players."
>
> **Action Items**:
> - [ ] Port the `Search` component from Data Grid to the Homepage Hero section.
> - [ ] Ensure it supports fuzzy matching for Player Name.

### Data: Freshness
**Title**: [Data] Update Dataset to 2025/2026 Season
**Labels**: data, ingestion, critical
**Body**:
> **Context**:
> User saw "2024" for Dak Prescott.
>
> **Critique**:
> "I see 2024, as if he didn't play in 2025?... Are these hard coded to only show up to 2024?"
>
> **Action Items**:
> - [ ] Update DuckDB ingestion pipeline to pull 2025/2026 Spotrac/OTC data.
> - [ ] Update `player-detail-view.tsx` to handle current league year dynamically.

### Visual: Risk Score Confidence
**Title**: [Visual] Refine Risk Score Presentation & Explainability
**Labels**: ui, data-viz, trust
**Body**:
> **Context**:
> "100.0/100" feels fake and overconfident.
>
> **Critique**:
> 1. "We shouldn't be mixing decimals with whole numbers."
> 2. "I don't see the REASONS why... Needs to say 'Expected Performance'."
> 3. "I'd also like to see the breakdown of the reasons from the SHAP breakdown."
>
> **Action Items**:
> - [ ] Format Score as integer (e.g., "99/100").
> - [ ] Rename "Risk" label to "Efficiency Gap" or similar.
> - [ ] Add "Explainability" section: Factor contributions (Age, position premium, injury history).

### Visual: Distribution Chart Layout
**Title**: [Visual] Fix Distribution Chart Layout & Labels
**Labels**: ui, bug, polish
**Body**:
> **Context**:
> Chart is misplaced and unlabeled.
>
> **Critique**:
> "Why is this way, WAY down below the copyright?"
> "No labels... should say 'QB Contract Count'... y-axis should be 'salary bucket'."
>
> **Action Items**:
> - [ ] Fix CSS Flexbox/Grid issue causing the chart to push below the footer.
> - [ ] Add X/Y Axis Labels to Recharts component.
> - [ ] Add Title: "{Position} Contract Distribution".

### Strategy: Content Value
**Title**: [Strategy] Paywall Value Proposition
**Labels**: product, monetization, strategy
**Body**:
> **Context**:
> User hit paywall but bounced.
>
> **Critique**:
> "I went thorugh the steps and have hit the paywall. I'm not sure at this point we have shown enough value for them to even do so."
>
> **Action Items**:
> - [ ] Design "Teaser" content for Post-June 1 logic (show the *potential* savings blurred out?).
> - [ ] Add "Social Proof" or "Badges" to the Paywall overlay.
