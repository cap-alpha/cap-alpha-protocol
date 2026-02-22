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

## Sprint 4 Adversarial UAT (The Red Team)

## UI: Export Player Card
**Title**: [UI] Add "Export Card" button for Twitter/X sharing
**Labels**: ui, product, viral-loop
**Body**:
> **Context**:
> The Armchair GM persona wants to share "Toxic Assets" to dunk on rival teams.
>
> **Critique**:
> "I want to share the player cards. I need a 'Download Image' button on the PlayerDetailView so I can dunk on Twitter when a team overpays a running back."
>
> **Action Items**:
> - [ ] Add a "Share/Export" button to `PlayerDetailView`.
> - [ ] Implement logic to capture the player card and charts as a high-quality image.

## Feature: Restructure Logic
**Title**: [Feature] Implement "Restructure" logic alongside "Cut Calculator"
**Labels**: feature, product, agent-persona
**Body**:
> **Context**:
> The Agent persona found the "Efficiency Gap" brutal and requested a restructure option.
>
> **Critique**:
> "The 'Risk Score' logic is brutal to my clients... We need a 'Restructure' toggle to see if we can convert base salary to signing bonus to save him."
>
> **Action Items**:
> - [ ] Add "Restructure" calculation mode next to the "Cut Calculator".
> - [ ] Model converting base salary to signing bonus to lower immediate Cap Hit.

## Data: Toxic Sort Order
**Title**: [Data] Sort Roster Grid by Surplus Value ascending by default in "Toxic" view
**Labels**: ux, data-viz
**Body**:
> **Context**:
> The Front Office (Suit) persona wants immediate visibility into the worst contracts.
>
> **Critique**:
> "We need a way to filter the Roster Grid specifically by 'Negative Surplus Value' to instantly find these bleeders."
>
> **Action Items**:
> - [ ] Add a quick filter/sort toggle or update default sorting logic to highlight negative Surplus Value.

## Feature: Tank Mode in Trade Machine
**Title**: [Feature] Add "Tank Mode" in the Trade Machine
**Labels**: feature, strategy
**Body**:
> **Context**:
> The NFL GM persona wants an option to prioritize future cap health over immediate cap savings.
>
> **Critique**:
> "Dead Money is sunk cost... The Trade Machine needs a 'Tank Mode' toggle where we explicitly prioritize clearing future years over this year's cap space."
>
> **Action Items**:
> - [ ] Add "Tank Mode" toggle to `TradeMachine`.
> - [ ] Adjust evaluation logic to heavily weight clearing future cap/guarantees, accepting massive Year 1 Dead Cap.

## Bug: Root Routing 404
**Title**: [Bug] Root `/` returns 404 Not Found in Headless Environments
**Labels**: bug, routing, high-priority
**Body**:
> **Context**:
> Headless browser testing hit an immediate 404 on `localhost:3000/`. Even though curl works, this indicates potential middleware or isolated sandbox issues affecting the root route.
>
> **Action Items**:
> - [ ] Investigate Next.js routing / caching that could serve a 404 in isolated headless contexts.

## Bug: Middleware Redirect Loop
**Title**: [Bug] Middleware redirect loop on `/sign-in` and `/scenarios`
**Labels**: bug, authentication, high-priority
**Body**:
> **Context**:
> Navigating to protected routes in a fresh headless browser resulted in jarring redirects or blank white pages related to Clerk middleware and CSP configurations.
>
> **Action Items**:
> - [ ] Debug `middleware.ts` Clerk protection logic.
> - [ ] Resolve CSP violations on `@clerk/clerk-js` workers.

## Bug: Missing Asset Markers
**Title**: [Bug] Missing asset markers (Favicon 404)
**Labels**: bug, polish
**Body**:
> **Context**:
> Console logs from the UAT highlighted 404s for the Favicon.
>
> **Action Items**:
> - [ ] Ensure `favicon.ico` is properly placed and synced in the `public` directory.

## UI: Executive Suite Dashboard Refactor
**Title**: [UI] De-clutter Executive Suite Homepage (Data-Ink Ratio)
**Labels**: ui, ux, design, polish
**Body**:
> **Context**:
> The homepage currently suffers from cognitive overload and "Chartjunk". Let's execute the Product Architect & Tufte audit.
>
> **Critique**:
> Review noted redundant interactive elements in the header, heavy borders on KPI cards blocking data, and a massive "Toxic Assets" CTA box competing with the primary data visualizations.
>
> **Action Items**:
> - [ ] Demote "MARKET: OPEN" and "League Year" badges to subtle text.
> - [ ] Remove heavy card borders from the KPI metrics row.
> - [ ] Subdue or remove the heavy background from the "Are you holding Toxic Assets?" block in the carousel.

## [QA] Verify 'Hardcore Harry' Use Case (Power Analyst)
**Title**: [QA] Verify 'Hardcore Harry' Use Case (Power Analyst)
**Labels**: bug
**Body**:
> Persona: Cap Analyst looking for efficiency.\n\n**Flow**:\n1. Data Grid -> Multi-Column Sort.\n2. Analyze 'Risk Score' vs 'Cap Hit'.\n3. Check 'Position Benchmark' for outliers.\n\n**Success Criteria**:\n- Filtering is responsive.\n- Distribution bucket logic is correct.

## [QA] Verify 'Podcaster Pete' Use Case (Content Creator)
**Title**: [QA] Verify 'Podcaster Pete' Use Case (Content Creator)
**Labels**: bug
**Body**:
> Persona: YouTuber needing visual aids.\n\n**Flow**:\n1. Navigate to Player Detail.\n2. Screenshot 'Value Trajectory' Chart.\n3. Screenshot 'Position Distribution' Chart.\n\n**Success Criteria**:\n- Charts are high-contrast.\n- Text is readable.\n- Tooltips don't clip.

## [QA] Verify 'Casual Carl' Use Case (Armchair GM)
**Title**: [QA] Verify 'Casual Carl' Use Case (Armchair GM)
**Labels**: bug
**Body**:
> Persona: Casual Fan wanting to fix their team. \n\n**Flow**:\n1. Landing Page -> Sort by 'Cap Hit'\n2. Click 'Overpaid Player' (e.g. Dak/Russ)\n3. Use 'Cut Calculator' to see Savings.\n4. Toggle 'Post-June 1' to see logic change.\n\n**Success Criteria**:\n- Math is accurate.\n- UX is intuitive (Red/Green indicators).

## [Feat] Save Cut Scenarios
**Title**: [Feat] Save Cut Scenarios
**Labels**: feature
**Body**:
> Allow users to save calculator results. Criteria: Create API route, Save scenarios table, UI integration.

## [Feat] Sync Clerk Webhooks
**Title**: [Feat] Sync Clerk Webhooks
**Labels**: backend
**Body**:
> Mirror Clerk user data to Postgres. Criteria: Create webhook endpoint, Validate signature, Handle user.created.

## [Infra] Install Drizzle ORM
**Title**: [Infra] Install Drizzle ORM
**Labels**: infrastructure
**Body**:
> To interact with Postgres safely. Criteria: Install drizzle-orm, Create schema.ts, Run migration.

## [Infra] Provision Vercel Postgres
**Title**: [Infra] Provision Vercel Postgres
**Labels**: infrastructure
**Body**:
> We need a persistent storage layer for User Data. Acceptance Criteria: Create DB, Link to project, Verify POSTGRES_URL.

## Issues after initial random forest -> production decision maker grade tool
**Title**: Issues after initial random forest -> production decision maker grade tool
**Labels**: 
**Body**:
> # Epic: Cap Risk Frontier — Decision-Grade Contract Risk System
>
> ## Goal
> Build a decision-support system that predicts **expected cap regret** (not just decline)
> and demonstrates **measurable reduction in dead cap disasters** via backtesting.
>
> ---
>
> ## ISSUE 1: Project Skeleton & Reproducibility
> **Type:** Infrastructure  
> **Owner:** TBD  
> **Why it matters:** Credibility starts with structure and reproducibility.
>
> ### Sub-issues
> - [ ] 1.1 Create repo structure (/data_raw, /data_processed, /src, /features, /models, /eval, /viz, /reports)
>   - Acceptance: clean imports, no notebooks required to run pipeline
> - [ ] 1.2 Add config system (YAML) for seasons, thresholds, scenarios
>   - Acceptance: changing thresholds requires no code changes
> - [ ] 1.3 Add reproducibility controls (pinned deps, seeds, artifact hashes)
>   - Acceptance: same inputs → byte-identical outputs
>
> ---
>
> ## ISSUE 2: Data Ingestion & Canonical Player Timeline
> **Type:** Data Engineering  
> **Why it matters:** Most “great models” fail because of bad joins and timeline leakage.
>
> ### Sub-issues
> - [ ] 2.1 Ingest player-season performance data
>   - Acceptance: one row per player-season, strictly historical
> - [ ] 2.2 Ingest contract & cap structure data (yearly cap hits, guarantees, outs)
>   - Acceptance: reconstructable contract timeline by season
> - [ ] 2.3 Ingest league salary cap by year
>   - Acceptance: cap % computable for any season
> - [ ] 2.4 Build canonical `player_id`
>   - Acceptance: no duplicate careers, no split histories
> - [ ] 2.5 Build season timeline table (“what was known when”)
>   - Acceptance: hard guardrails preventing future info leakage
>
> ---
>
> ## ISSUE 3: Outcome Definitions (Decision Targets)
> **Type:** Modeling / Product  
> **Why it matters:** Executives care about *financial regret*, not labels.
>
> ### Sub-issues
> - [ ] 3.1 Implement configurable binary “Cap Trap” label
>   - Acceptance: thresholds adjustable via config
> - [ ] 3.2 Implement Expected Dead Cap Exposure (EDCE) for 1/2/3 years
>   - Acceptance: outputs dollars, not scores
> - [ ] 3.3 Implement Value Efficiency Delta metric
>   - Acceptance: decline relative to cost + replacement, not raw drop
>
> ---
>
> ## ISSUE 4: Decline Risk Feature Layer
> **Type:** Feature Engineering  
> **Why it matters:** Decline ≠ age; decline is age + usage + volatility.
>
> ### Sub-issues
> - [ ] 4.1 True age + position-adjusted aging curves
> - [ ] 4.2 Injury burden & recurrence features
> - [ ] 4.3 Career workload metrics (position-specific)
> - [ ] 4.4 Efficiency trend (2yr/3yr slope) + volatility
> - [ ] 4.5 Role stability proxies (snap share, usage share)
> - [ ] 4.6 Replacement cost context by position
>   - Acceptance: no single “replacement level” constant
>
> ---
>
> ## ISSUE 5: Contract Fragility Feature Layer
> **Type:** Feature Engineering  
> **Why it matters:** Contracts fail structurally before players fail athletically.
>
> ### Sub-issues
> - [ ] 5.1 Cap % by year, guarantees remaining, guarantee ratio
> - [ ] 5.2 Escape hatch features (outs, dead cap if cut, post-June)
> - [ ] 5.3 Flexibility score (exit cost under thresholds)
> - [ ] 5.4 Value Compression Index (VCI)
> - [ ] 5.5 Cap growth scenario features (low/base/high)
>   - Acceptance: fragility changes under macro assumptions
>
> ---
>
> ## ISSUE 6: Two-Stage Modeling System
> **Type:** Modeling  
> **Why it matters:** One model cannot responsibly do both biology and economics.
>
> ### Sub-issues
> - [ ] 6.1 Model A — Decline Risk Model
>   - Output: probability distribution of performance drop
> - [ ] 6.2 Position-aware modeling strategy
>   - Acceptance: RB/QB/EDGE behavior clearly distinct
> - [ ] 6.3 Model B — Contract Regret Simulator
>   - Acceptance: maps decline distributions → EDCE via simulation
> - [ ] 6.4 Model calibration & uncertainty checks
>   - Acceptance: probabilities are meaningfully calibrated
>
> ---
>
> ## ISSUE 7: Evaluation & Credibility Tests
> **Type:** Evaluation  
> **Why it matters:** Directors will assume leakage until proven otherwise.
>
> ### Sub-issues
> - [ ] 7.1 Rolling-origin temporal validation
> - [ ] 7.2 Metrics beyond ROC AUC (PR AUC, precision@K, calibration)
> - [ ] 7.3 Leakage detection & feature ablation tests
> - [ ] 7.4 Error analysis (“miss gallery”)
>   - Acceptance: documented false positives/negatives with explanations
>
> ---
>
> ## ISSUE 8: MONEY SLIDE Backtest (Executive Proof)
> **Type:** Product / Evaluation  
> **Why it matters:** This is the slide that gets remembered.
>
> ### Sub-issues
> - [ ] 8.1 Define baseline decision policy (league-typical behavior)
> - [ ] 8.2 Define model-informed policy (avoid/restructure top X% EDCE)
> - [ ] 8.3 Simulate outcomes across historical seasons
>   - Track: dead cap $, # disasters, cap flexibility retained
> - [ ] 8.4 Aggregate results & sensitivity analysis
> - [ ] 8.5 Produce headline metric:
>   - “Reduces severe dead cap events by X%”
>   - Acceptance: defensible under scrutiny
>
> ---
>
> ## ISSUE 9: Interpretability & Trust Layer
> **Type:** Explainability  
> **Why it matters:** Models must justify themselves to humans.
>
> ### Sub-issues
> - [ ] 9.1 Global feature importance by position
> - [ ] 9.2 Local player explanations (SHAP / rule paths)
> - [ ] 9.3 “Why flagged?” narrative template
>   - Acceptance: readable by non-technical decision-makers
>
> ---
>
> ## ISSUE 10: Product Outputs (Meeting-Ready Artifacts)
> **Type:** Visualization / UX  
> **Why it matters:** If it can’t be shown in a meeting, it won’t be used.
>
> ### Sub-issues
> - [ ] 10.1 One-page player risk card
> - [ ] 10.2 Risk frontier visualization (cap burden vs regret)
> - [ ] 10.3 GM-ranked Top 25 risk list
> - [ ] 10.4 Contract structure “what-if” tool
>   - Acceptance: clearly shows impact of guarantees/out years
>
> ---
>
> ## ISSUE 11: Narrative & Executive Packaging
> **Type:** Documentation  
> **Why it matters:** Framing determines whether this is “interesting” or “important.”
>
> ### Sub-issues
> - [ ] 11.1 Rewrite README around outcomes, not accuracy
> - [ ] 11.2 Explicit limits & failure modes section
> - [ ] 11.3 Short methodology appendix (defensible, not flashy)
>   - Acceptance: no “93% accuracy” headline
>
> ---
>
> ## ISSUE 12: Pipeline & Hygiene (Optional but Director Candy)
> **Type:** Infra / Ops  
> **Why it matters:** Signals production thinking.
>
> ### Sub-issues
> - [ ] 12.1 End-to-end automated pipeline
> - [ ] 12.2 Model registry & data snapshot versioning
> - [ ] 12.3 Unit tests for joins, labels, EDCE calc
