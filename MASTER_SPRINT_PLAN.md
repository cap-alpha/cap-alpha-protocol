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

### Sprint 12: Real-Time Live Data Hydration (News & Rumors)
**Goal:** Satisfy stakeholder requirement to view *live, up-to-date market information, trade rumors, and injury news* for literally any player currently in the NFL, populated dynamically into `media_lag_metrics`.
- [ ] SP12-1: Build a Python hydration script (`scripts/hydrate_live_news.py`) utilizing an external News API or web scraper.
- [ ] SP12-2: Connect the unstructured news data to the existing Gemini LLM summarization prompt to extract precise "Intelligence Sentences" (Rumors, Warnings, Contract Talks).
- [ ] SP12-3: Inject the processed intelligence sentences into the MotherDuck `media_lag_metrics` table so the `<IntelligenceFeed>` component can render them in real-time.
- [ ] SP12-4: Establish a cron schedule or Airflow DAG to run the hydration pipeline daily for top 500 assets.

### Sprint 13: Vercel Production Deployment
**Goal:** Expose the web application securely to the public internet for continuous stakeholder review.
- [ ] SP13-1: Connect the repository to Vercel and configure the `MOTHERDUCK_TOKEN` and Auth Environment variables.
- [ ] SP13-2: Validate that GitHub Actions executes the `docker-compose run e2e` integration tests prior to approving the build.
- [ ] SP13-3: Conduct User Acceptance Testing (UAT) on the deployed site across mobile and web interfaces.
