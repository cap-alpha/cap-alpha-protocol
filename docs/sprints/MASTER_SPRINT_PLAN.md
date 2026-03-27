# NFL Dead Money Prediction - Master Sprint Plan

**Date**: March 16, 2026
**Status**: Active Execution

This document contains the canonical Sprint Plan for the NFL Dead Money project, codifying the tasks required to bring the system from local prototyping to full production, including actual data hydration and UI democking.

## Milestones Achieved (Sprints 1-10)
*For a detailed history of the ML modeling and backend hydration, see the respective architecture documents.*
- [x] Sprint 3-4: Repository Assessment & Web App Status Checks
- [x] Sprint 5: Automated ML Flywheel (Milestone 1)
- [x] Sprint 7: "Alpha" Frontend & Media Lag ROI Initial Proof of Concept
- [x] Sprint 8: Master UI/UX Global Navigation Audit
- [x] Sprint 9: Persona-Driven Architecture Overhaul
- [x] Sprint 10: Auth Routing, RBAC, and Consensus Engine

---

## Active & Upcoming Sprints

### Sprint 11: Production Hardening & E2E Integration Suite (Rigor Audit)
**Goal:** Establish a strict "No Mock" policy for the React Frontend UI. Ensure 100% data integrity with MotherDuck and finalize a containerized deployment test suite.
- [x] SP11-1: Establish Strict "No Mock" Policy. Remove all hardcoded mock fallbacks in UI components (Intelligence Feed, Timeline, Dashboards).
- [x] SP11-2: Plumb actual DB queries for `IntelligenceFeed` and handle true empty states gracefully (Zero State UX).
- [x] SP11-3: Guarantee `PlayerTimeline` query execution in MotherDuck and render authentic DB events.
- [x] SP11-4: Update Data Visualization charts (`ComposedChart`) to render robust empty states when historical data is absent.
- [x] SP11-5: Build `tests/e2e/integration.spec.ts` as the singular, high-signal integration suite for deployment pipelines.
- [x] SP11-6: Execute integration suite exclusively inside the `e2e` Docker container to guarantee environment parity and bypass macOS EPERM.

### Sprint 12: Real-Time Live Data Hydration (News & Rumors) - ACTIVE
**Goal:** Satisfy stakeholder requirement to view *live, up-to-date market information, trade rumors, and injury news* populated dynamically into `media_lag_metrics`.
- [x] SP12-1: Build a Python hydration script (`scripts/hydrate_live_news.py`) utilizing an external News API or web scraper.
- [x] SP12-2: Connect the unstructured news data to the existing Gemini LLM summarization prompt to extract precise "Intelligence Sentences".
- [x] SP12-3: Inject the processed intelligence sentences into the MotherDuck `media_lag_metrics` table.
- [x] SP12-4: Establish a cron schedule or Airflow DAG to run the hydration pipeline.
- [x] SP12-5: Execute `media_lag_analyzer.py` to replace mocked market reality data with grounded Gemini search consensus and integrate into Airflow DAG.

### Sprint 13: Legacy Data Parity (Spotrac/PFR Feature Match)
**Goal:** Ensure the platform natively supports all core salary cap and historical context features natively offered by legacy competitor sites.
- [x] SP13-1: Extract and display deep salary cap breakdowns (Base, Prorated Bonus, Roster Bonus, Guaranteed Salary) per player.
- [x] SP13-2: Visualize team-level positional spending alongside league averages for immediate roster architecture critique.
- [x] SP13-3: Migrate historical game logs or essential box score statistics for context beside the advanced machine learning intelligence.

### Sprint 14: Pipeline Automation & Broad Sentiment Tracking
**Goal:** Optimize scale and unit economics on LLM hydration via Franchise-Level batching, achieving 100% total active roster verifiability.
- [x] SP14-1: Migrate the manual `docker-compose` pipeline executions into a scheduled Git Action or Airflow DAG running on a set cadence.
- [x] SP14-2: Architect and implement Franchise-Level News Batching in `hydrate_live_news.py` to achieve 100% total active roster verifiability using Gemini Ultra context.
- [x] SP14-3: Generate automated alert telemetry for when sentiment severely disconnects from contract value (identifying accelerating trajectories).
- [x] SP14-4: Refactor `hydrate_live_news.py` to search for news by franchise/team rather than individual player.
- [x] SP14-5: Cross-reference team news against active rosters to record a definitive "news" or "no news" status for every player, enabling comprehensive point-in-time analysis.
- [x] SP14-6: Optimize the pipeline to safely execute hourly (idempotency, rate limit handling).
- [x] SP14-7: Implement filtering capabilities to elevate the most critical updates for media use cases while retaining full player-level history.

### Sprint 15: Walk-Forward Validation & Model Audit
**Goal:** Solidify confidence in the prediction engine against historical point-in-time facts (Out-of-sample backtesting).
- [x] SP15-1: Build out out-of-sample temporal backtesting capabilities to validate the prediction engine against historical point-in-time facts.
- [x] SP15-2: Perform a post-mortem on severe model misses (e.g., highly rated players who busted, low rated players who popped).
- [x] SP15-3: (Completed by Agent) Create an explicit architectural roadmap for algorithmic improvements to address identified weaknesses.

### Sprint 16: Player Visual Timeline Experience 
**Goal:** Empower users with a single unified chronological view of all events affecting a player's market value.
- [x] SP16-1: Unify heterogeneous events (News Intel, Contract Restructures, Trades, Injuries, Cap hits) into a singular `player_timeline_events` view.
- [x] SP16-2: Build a horizontal `<VisualTimeline />` React component on the player profile page (`/player/[id]`).
- [x] SP16-3: Implement data fetching and rendering of dynamic events with custom icons per event type (e.g. 📄 for contracts, 🚨 for rumors).

### Sprint 17: Vercel Production Deployment
**Goal:** Expose the web application securely to the public internet for continuous stakeholder review.
- [x] SP17-1: Connect the repository to Vercel and configure the `MOTHERDUCK_TOKEN` and Auth Environment variables.
- [x] SP17-2: Validate that GitHub Actions executes the `docker-compose run e2e` integration tests prior to approving the build.
- [x] SP17-3: Conduct User Acceptance Testing (UAT) on the deployed site across mobile and web interfaces. (Completed: UAT generated Sprint 17.5 blockers).

### Sprint 17.5: Executive UAT Hardening (Board Inspection Blockers)
**Goal:** Resolve all critical UI, technical, and data integrity failures identified during the Executive Board UAT run to meet the "Bloomberg Terminal" / Cap Alpha Protocol standards.
- [x] SP17.5-1: (Claimed by Agent) Enforce global Dark Mode and remove standard marketing images to establish the "Bloomberg Terminal" visualization aesthetic.
- [x] SP17.5-2: Repair the Search Modal (Cmd+K and click bindings) to instantly surface queried assets.
- [x] SP17.5-3: Fix broken navigation links (resolve 500 Error on `/dashboard` and 404 on `/select-team`).
- [x] SP17.5-4: Re-engineer the Cut Calculator to use actual math instead of mocked $0.0M static dead money outputs.
- [x] SP17.5-5: Repair the local image pipeline to halt 404s for player headshots (e.g. `daniel_jones.jpg`).

## Milestone 2: Production Launch & Data Independence
***Goal:*** Launch the production version of the web application to the public internet. Be able to respond to stakeholder requests for changes and updates. Automation fixes, which should have been ironed about by now, must take a back seat to addressing stakeholder requests.

### Sprint 18: Official Data Vendor Integration (Data Independence)
**Goal:** Sever reliance on scraped/competitor data by integrating official, deterministic data feeds (e.g., Sportradar, official NFL API, or premium vendor) to ensure we own our pipeline and can scale without rate-limits or adversarial blocking.
- [b] SP18-1: Select and procure an official data vendor API for real-time and historical NFL player/contract data (e.g., Sportradar API, Stats Perform). (Blocked on User Procurement)
- [b] SP18-2: Build a robust Python ingestion client to hydrate the MotherDuck Bronze layer directly from the official authenticated API.
- [b] SP18-3: Validate the new official feed against our internal predictions and backtests, ensuring schema compatibility and resolving any data discrepancies.
- [b] SP18-4: Deprecate legacy web scraper pipelines and reroute all downstream Silver/Gold transformations to rely exclusively on the new official Bronze data.

### Sprint 19: Immutable Auditability (Cryptographic Ledger)
**Goal:** Prove absolute honesty in historical Fair Market Value predictions by eliminating hindsight bias. Implement a verifiable cryptographic ledger.
- [/] SP19-1: (Claimed by Agent) Hash nightly predictions and intelligence signals into a Merkle tree or public ledger interface.
- [ ] SP19-2: Build `<VerifiableAudit />` component to render the cryptographic signature for any historical player event.
- [ ] SP19-3: Architect a "Regulatory-Grade" data tier strictly enforcing append-only writes for prediction artifacts.

### Sprint 20: Sub-Second Latency & Performance Optimization
**Goal:** Ensure every page load across the entire web application resolves in under 1.0s to deliver an elite, lightning-fast executive UX.
- [/] SP20-1: (Claimed by Agent) Implement edge caching strategies and static site generation (SSG) for static assets, team directories, and global search index.
- [ ] SP20-2: Optimize MotherDuck query execution paths (e.g., query caching, materialized views) for complex models and aggregations.
- [ ] SP20-3: Audit React rendering loops to eliminate unnecessary re-renders in heavy visualization components (`<ComposedChart />`, `<RosterGrid />`).
- [ ] SP20-4: Enforce an automated performance budget in CI/CD pipeline (Lighthouse scores > 95 for Performance, Accessibility, and SEO).

### Sprint 21: Front Page Strategic Redesign & Identity
**Goal:** Reconvene key stakeholders to brainstorm, define, and agree upon a comprehensive user flow and concept set for the front page, firmly establishing the product identity as an "intelligence aggregator and prediction market on sports."
- [ ] SP21-1: Schedule and conduct a stakeholder roundtable (Product Council, Design, Execution) to discuss front page flow and concepts.
- [x] SP21-2: Draft a "Front Page Vision & Identity" document clarifying the "intelligence aggregator and prediction market" positioning.
- [ ] SP21-3: Develop low-fidelity wireframes or concepts for the new front page flow based on stakeholder consensus.
- [ ] SP21-4: Review and approve the new front page concepts before technical implementation begins.

### Sprint 22: Media Accountability & Prediction Tracking (The Pundit Index)
**Goal:** Track public assertions made by major sports personalities across X and mainstream media, mapping their narrative influence against empirical "sharp" line movements to expose manipulation or toxic advice.
- [ ] SP22-1: **Data Ingestion (Media Pipes)** - Integrate APIs/Scrapers (e.g., X, YouTube transcripts via Whisper, Action Network) to chronologically log public predictions from major sports personalities.
- [ ] SP22-2: **NLP Assertion Extraction** - Build an LLM-based parsing pipeline to convert unstructured media quotes ("I love Mahomes this week") into structured prediction vectors (`{entity: "P. Mahomes", stance: "Bullish", date: "2024-10-12", pundit: "Pat McAfee"}`).
- [ ] SP22-3: **Reverse Line Movement Integration** - Ingest live Vegas line movements and Ticket vs. Money percentages to track where "Sharp" money is flowing.
- [ ] SP22-4: **Contrary Syndicate Detection** - Build the anomaly detection model: Flag instances where a personality pushes a narrative (driving retail ticket %), but the sharp money aggressively moves the opposite direction (indicating the pundit's advice is toxic/manipulative).
- [ ] SP22-5: **The Pundit Ledger UI** - Create a public accountability dashboard ranking personalities by their Brier Score (prediction accuracy) vs. Market Consensus, exposing toxic alpha.

### Sprint 23: Adversarial Sentiment & Prediction Defense
**Goal:** Harden the Alpha Flywheel and Intelligence Pipeline against coordinated bad actors attempting to skew Media Sentiment (e.g. synthetic news/bots) via manufactured narratives.
- [ ] SP23-1: **Bot & Astroturfing Detection:** Filter out synthetic articles and highly repetitive NLP phrasing that signals a coordinated attack on a specific high-value asset.
- [ ] SP23-2: **Source Reputation Weighting:** Enforce a heuristic decay on unverified domains or publishers whose historical accuracy metric drops below an acceptable baseline.
- [ ] SP23-3: **Anomaly Flagging (Suspicious Volume Spike):** If a player receives an atypical surge of negative sentiment divergence outside of standard Game-Days/Trade Windows, automatically quarantine the signals for manual review instead of directly lowering their contract value prediction.

### Sprint 24: Vercel Expenditure & Build Cycle Optimization
**Goal:** Drastically reduce accrued Vercel build time and hosting expenditures by decoupling the Next.js frontend builds from backend/pipeline monorepo commits.
- [x] SP24-1: (Completed by Agent) **Monorepo Build Isolation:** Configure Vercel's `Ignored Build Step` (`git diff --quiet HEAD^ HEAD ./web/`) to ensure non-UI commits (Python pipeline, documentation, GitHub Actions) automatically skip web compilation.
- [x] SP24-2: (Completed by Agent) **Cache Architecture Audit:** Audit the Next.js data hooks to ensure fetches utilize maximum valid `revalidate` periods (ISR) rather than forced SSR on every page hit, saving Serverless Function execution time.
- [ ] SP24-3: **Asset Pre-computation:** Shift any heavy client-side statistical aggregations dynamically calculated in UI edge functions entirely into the Python `medallion_pipeline.py` to offload compute costs to the pipeline runner rather than Vercel.
- [-] SP24-4: (Deferred) **DuckDB Client Upgrade:** Address the version deprecation warning. (N/A: Platform fully migrated to BigQuery).
- [-] SP24-5: (Deferred) **MotherDuck Compute Limit Diagnosis:** Investigate the recent platform warning regarding reaching the daily compute limit. (N/A: Platform fully migrated to BigQuery).

### Sprint 25: Growth, Monetization & Agentic ROI
**Goal:** Implement specific monetization targets while establishing strategic ROI mandates for Antigravity utilization.
- [x] SP25-1: (Claimed by Agent) Establish the Productivity Tracking / ROI Audit Mandate to maximize API quota value.
- [x] SP25-2: (Completed by Agent) Implemented Vercel edge-geolocation and cookie-based routing directly in TeamPage.
- [/] SP25-3: (Claimed by Agent) Auto-generate the 'Personality Magnet' visual infographic component to attract analysts/creators.
