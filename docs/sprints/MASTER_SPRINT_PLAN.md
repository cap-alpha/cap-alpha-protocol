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
- [ ] SP11-5: Build `tests/e2e/integration.spec.ts` as the singular, high-signal integration suite for deployment pipelines.
- [ ] SP11-6: Execute integration suite exclusively inside the `e2e` Docker container to guarantee environment parity and bypass macOS EPERM.

### Sprint 12: Real-Time Live Data Hydration (News & Rumors) - ACTIVE
**Goal:** Satisfy stakeholder requirement to view *live, up-to-date market information, trade rumors, and injury news* populated dynamically into `media_lag_metrics`.
- [x] SP12-1: Build a Python hydration script (`scripts/hydrate_live_news.py`) utilizing an external News API or web scraper.
- [x] SP12-2: Connect the unstructured news data to the existing Gemini LLM summarization prompt to extract precise "Intelligence Sentences".
- [x] SP12-3: Inject the processed intelligence sentences into the MotherDuck `media_lag_metrics` table.
- [x] SP12-4: Establish a cron schedule or Airflow DAG to run the hydration pipeline.

### Sprint 13: Legacy Data Parity (Spotrac/PFR Feature Match)
**Goal:** Ensure the platform natively supports all core salary cap and historical context features natively offered by legacy competitor sites.
- [ ] SP13-1: Extract and display deep salary cap breakdowns (Base, Prorated Bonus, Roster Bonus, Guaranteed Salary) per player.
- [ ] SP13-2: Visualize team-level positional spending alongside league averages for immediate roster architecture critique.
- [ ] SP13-3: Migrate historical game logs or essential box score statistics for context beside the advanced machine learning intelligence.

### Sprint 14: Pipeline Automation & Broad Sentiment Tracking
**Goal:** Optimize scale and unit economics on LLM hydration via Franchise-Level batching, achieving 100% total active roster verifiability.
- [ ] SP14-1: Migrate the manual `docker-compose` pipeline executions into a scheduled Git Action or Airflow DAG running on a set cadence.
- [ ] SP14-2: Architect and implement Franchise-Level News Batching in `hydrate_live_news.py` to achieve 100% total active roster verifiability using Gemini Ultra context.
- [ ] SP14-3: Generate automated alert telemetry for when sentiment severely disconnects from contract value (identifying accelerating trajectories).
- [ ] SP14-4: Refactor `hydrate_live_news.py` to search for news by franchise/team rather than individual player.
- [ ] SP14-5: Cross-reference team news against active rosters to record a definitive "news" or "no news" status for every player, enabling comprehensive point-in-time analysis.
- [ ] SP14-6: Optimize the pipeline to safely execute hourly (idempotency, rate limit handling).
- [ ] SP14-7: Implement filtering capabilities to elevate the most critical updates for media use cases while retaining full player-level history.

### Sprint 15: Walk-Forward Validation & Model Audit
**Goal:** Solidify confidence in the prediction engine against historical point-in-time facts (Out-of-sample backtesting).
- [ ] SP15-1: Build out out-of-sample temporal backtesting capabilities to validate the prediction engine against historical point-in-time facts.
- [ ] SP15-2: Perform a post-mortem on severe model misses (e.g., highly rated players who busted, low rated players who popped).
- [ ] SP15-3: Create an explicit architectural roadmap for algorithmic improvements to address identified weaknesses.

### Sprint 16: Player Visual Timeline Experience 
**Goal:** Empower users with a single unified chronological view of all events affecting a player's market value.
- [ ] SP16-1: Unify heterogeneous events (News Intel, Contract Restructures, Trades, Injuries, Cap hits) into a singular `player_timeline_events` view.
- [ ] SP16-2: Build a horizontal `<VisualTimeline />` React component on the player profile page (`/player/[id]`).
- [ ] SP16-3: Implement data fetching and rendering of dynamic events with custom icons per event type (e.g. 📄 for contracts, 🚨 for rumors).

### Sprint 17: Vercel Production Deployment
**Goal:** Expose the web application securely to the public internet for continuous stakeholder review.
- [ ] SP17-1: Connect the repository to Vercel and configure the `MOTHERDUCK_TOKEN` and Auth Environment variables.
- [ ] SP17-2: Validate that GitHub Actions executes the `docker-compose run e2e` integration tests prior to approving the build.
- [ ] SP17-3: Conduct User Acceptance Testing (UAT) on the deployed site across mobile and web interfaces.

### Sprint 18: Immutable Auditability (Cryptographic Ledger)
**Goal:** Prove absolute honesty in historical Fair Market Value predictions by eliminating hindsight bias. Implement a verifiable cryptographic ledger.
- [ ] SP18-1: Hash nightly predictions and intelligence signals into a Merkle tree or public ledger interface.
- [ ] SP18-2: Build `<VerifiableAudit />` component to render the cryptographic signature for any historical player event.
- [ ] SP18-3: Architect a "Regulatory-Grade" data tier strictly enforcing append-only writes for prediction artifacts.

### Sprint 19: Sub-Second Latency & Performance Optimization
**Goal:** Ensure every page load across the entire web application resolves in under 1.0s to deliver an elite, lightning-fast executive UX.
- [ ] SP19-1: Implement edge caching strategies and static site generation (SSG) for static assets, team directories, and global search index.
- [ ] SP19-2: Optimize MotherDuck query execution paths (e.g., query caching, materialized views) for complex models and aggregations.
- [ ] SP19-3: Audit React rendering loops to eliminate unnecessary re-renders in heavy visualization components (`<ComposedChart />`, `<RosterGrid />`).
- [ ] SP19-4: Enforce an automated performance budget in CI/CD pipeline (Lighthouse scores > 95 for Performance, Accessibility, and SEO).

### Sprint 20: Front Page Strategic Redesign & Identity
**Goal:** Reconvene key stakeholders to brainstorm, define, and agree upon a comprehensive user flow and concept set for the front page, firmly establishing the product identity as an "intelligence aggregator and prediction market on sports."
- [ ] SP20-1: Schedule and conduct a stakeholder roundtable (Product Council, Design, Execution) to discuss front page flow and concepts.
- [ ] SP20-2: Draft a "Front Page Vision & Identity" document clarifying the "intelligence aggregator and prediction market" positioning.
- [ ] SP20-3: Develop low-fidelity wireframes or concepts for the new front page flow based on stakeholder consensus.
- [ ] SP20-4: Review and approve the new front page concepts before technical implementation begins.
