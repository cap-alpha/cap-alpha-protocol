# NFL Dead Money Prediction - Master Sprint Plan

**Date**: March 29, 2026
**Status**: Active Execution - Phase 1 (Data Independence)

This document contains the canonical Sprint Plan for the NFL Dead Money project, strictly structured under our core Strategic Pivot: **Data Independence First, API Second, UI Third.** 

## Milestones Achieved (Sprints 1-10)
*For a detailed history of the ML modeling and backend hydration, see the respective architecture documents.*
- [x] Sprint 3-4: Repository Assessment & Web App Status Checks
- [x] Sprint 5: Automated ML Flywheel (Milestone 1)
- [x] Sprint 7: "Alpha" Frontend & Media Lag ROI Initial Proof of Concept
- [x] Sprint 8: Master UI/UX Global Navigation Audit
- [x] Sprint 9: Persona-Driven Architecture Overhaul
- [x] Sprint 10: Auth Routing, RBAC, and Consensus Engine

---

## Milestone 1: Data Independence, Reliability, Quality & Freshness
**Goal:** The pipeline must be unconditionally reliable, fresh, and historically accurate. The web UI is deferred until Andrew signs off on the statistical parity of the data. 

### Sprint 18: Official Data Vendor Integration (Data Independence)
**Goal:** Sever reliance on scraped/competitor data by integrating official, deterministic data feeds (e.g., Sportradar, official NFL API, or premium vendor) to ensure we own our pipeline.
- [x] SP18-1: Select and procure an official data vendor API for real-time and historical NFL player/contract data (e.g., Sportradar API, Stats Perform). (Blocked on User Procurement) (GH-#60)
  - 💬 **1 comment(s)** on GitHub. See https://github.com/ucalegon206/cap-alpha-protocol/issues/60
- [ ] SP18-2: Build a robust Python ingestion client to hydrate the BigQuery Bronze layer directly from the official authenticated API. (GH-#61)
- [ ] SP18-3: Validate the new official feed against our internal predictions and backtests, ensuring schema compatibility and resolving any data discrepancies. (GH-#62)
- [ ] SP18-4: Deprecate legacy web scraper pipelines and reroute all downstream Silver/Gold transformations to rely exclusively on the new official Bronze data. (GH-#63)

### Sprint 18.5: High-Frequency Silver Data Model Redesign
**Goal:** Refactor the Silver data model architecture to natively ingest, merge, and temporalize high-frequency updates (hourly/daily deltas) replacing legacy nightly-batch assumptions.
- [ ] SP18.5-1: Audit all Silver layer tables and document necessary schema updates (e.g., adding distinct `valid_from` / `valid_until` timestamps for SCD Type 2 tracking). (GH-#64)
- [ ] SP18.5-2: Architect an event-driven or micro-batch ETL trigger pipeline to process state changes as they stream from the official provider. (GH-#65)
- [ ] SP18.5-3: Rewrite Downstream Gold/Fact aggregations to gracefully consume and deduplicate high-frequency Silver deltas without re-running the entire history. (GH-#66)

### Sprint 27: Historical Data Hydration & Rigorous Asset Validation
**Goal:** Verify the BigQuery migration, purge DuckDB remnants, and perform a rigorous integrity check for specific high-value assets (Joe Flacco) against major historical events.
- [{9fb98ecc-450d-4df0-8ab4-ae49321f4a80}] (TTL: 2026-03-30T17:00:00Z) SP27-1: Verify that the pipeline backfill configuration to BigQuery Bronze layer (back to 2011) has completed successfully.
- [{9fb98ecc-450d-4df0-8ab4-ae49321f4a80}] (TTL: 2026-03-30T17:00:00Z) SP27-2: Identify and permanently purge all remaining DuckDB/MotherDuck artifacts from the repository.
- [{9fb98ecc-450d-4df0-8ab4-ae49321f4a80}] (TTL: 2026-03-30T17:00:00Z) SP27-3: Query and extract the value of every single column natively stored in the database representing Joe Flacco.
- [{9fb98ecc-450d-4df0-8ab4-ae49321f4a80}] (TTL: 2026-03-30T17:00:00Z) SP27-4: Perform targeted web lookups to fundamentally verify the real-world accuracy of Joe Flacco's historical numbers against the database values.
- [{9fb98ecc-450d-4df0-8ab4-ae49321f4a80}] (TTL: 2026-03-30T17:00:00Z) SP27-5: Generate a definitive list of active TODOs to remediate any anomalies or missing values identified during the evaluation.

### Sprint 29: Schema Integrity & Output Guardrails (NEW)
**Goal:** Enforce unyielding data contracts so that bad data never propagates into the Gold layer or user-facing APIs.
- [ ] SP29-1: Enforce strict BigQuery `NOT NULL` constraints and foreign key mappings across all core identity tables (Players, Teams, Contracts). (GH-#106)
- [ ] SP29-2: Implement automated dbt/Great Expectations data quality checks that run post-ingestion, instantly alerting on standard deviation outliers or missing cap figures. (GH-#107)

### Sprint 22: Media Accountability & Prediction Tracking (Data Layer)
**Goal:** Track public assertions made by major sports personalities across X and mainstream media, mapping their narrative influence against empirical "sharp" line movements.
- [ ] SP22-1: **Data Ingestion (Media Pipes)** - Integrate APIs/Scrapers (e.g., X, YouTube transcripts via Whisper, Action Network) to chronologically log public predictions. (GH-#78)
- [ ] SP22-2: **NLP Assertion Extraction** - Build an LLM-based parsing pipeline to convert unstructured media quotes into structured prediction vectors. (GH-#79)
- [ ] SP22-3: **Reverse Line Movement Integration** - Ingest live Vegas line movements and Ticket vs. Money percentages to track where "Sharp" money is flowing. (GH-#80)
- [ ] SP22-4: **Contrary Syndicate Detection** - Flag instances where a personality pushes a narrative but sharp money aggressively moves the opposite direction. (GH-#81)

### Sprint 23: Adversarial Sentiment & Prediction Defense
**Goal:** Harden the Alpha Flywheel and Intelligence Pipeline against coordinated bad actors attempting to skew Media Sentiment via manufactured narratives.
- [ ] SP23-1: **Bot & Astroturfing Detection:** Filter out synthetic articles and highly repetitive NLP phrasing that signals a coordinated attack. (GH-#83)
- [ ] SP23-2: **Source Reputation Weighting:** Enforce a heuristic decay on unverified domains or publishers whose historical accuracy metric drops below an acceptable baseline. (GH-#84)
- [ ] SP23-3: **Anomaly Flagging (Suspicious Volume Spike):** If a player receives an atypical surge of negative sentiment divergence, quarantine the signals for manual review. (GH-#85)

### Sprint 19: Immutable Auditability (Cryptographic Ledger)
**Goal:** Prove absolute honesty in Fair Market Value predictions by eliminating hindsight bias. Implement a verifiable cryptographic ledger.
- [x] SP19-3: Architect a "Regulatory-Grade" data tier strictly enforcing append-only writes for prediction artifacts. (GH-#69)

---

## Milestone 2: API Generation & Monetization Architecture
**Goal:** The platform must vend the validated data via a reliable and fast API layer, completely decoupled from the NextJS UI render cycle.

### Sprint 30: API Standardization & Keys (NEW)
**Goal:** We must be able to securely vend, rate-limit, and explicitly monetize our core intelligent artifacts via an API to massive third-party B2B consumers.
- [ ] SP30-1: Stand up a dedicated `/v1/cap/` Python REST or GraphQL API backend securely authenticating via B2B API keys. (GH-#108)
- [ ] SP30-2: Document the full API schema via OpenAPI/Swagger, clearly identifying the "Pundit Index", "FMV Trajectory", and "Injury Lag" vendor payloads. (GH-#109)

### Sprint 20: Sub-Second Latency & Backend Performance
**Goal:** Ensure backend data is served immediately, ready to be cached by edge consumers or UI platforms.
- [x] SP20-1: (Claimed by Agent) Architect backend caching layers leveraging Redis or Edge logic to prevent BigQuery cost-overruns on read-heavy routes. (GH-#70)
- [x] SP20-2: Optimize BigQuery/MotherDuck query execution paths (e.g., materialized views) for complex models and aggregations before they hit the API. (GH-#71) (PR #220)

### Sprint 24: Cloud Expenditure & Compute Optimization
**Goal:** Offload all heavy stat calculations to the pipeline architecture, protecting the API layer.
- [ ] SP24-3: **Asset Pre-computation:** Shift any heavy client-side statistical aggregations entirely into the Python `medallion_pipeline.py` to offload compute costs to the ingestion nodes. (GH-#88)

---

## Milestone 3: The Presentation Layer (Web/UI)
**Goal:** The "Showcase" bringing the fully verified API to life. *Work here is suspended until M1 and M2 are stable.*

### Sprint 11: Production Hardening & E2E Integration
- [ ] SP11-1: Establish a strict "No Mock" policy for the React Frontend UI. Ensure 100% data integrity with the M2 API layer. (GH-#25)

### Sprint 16: Player Visual Timeline Experience 
- [ ] SP16-1: Build a single unified chronological view of all events affecting a player's market value in the UI. (GH-#49)

### Sprint 21: Front Page Strategic Redesign & Identity
- [ ] SP21-1: Complete user flow and concept set for the front page, establishing the product identity ("Bloomberg Terminal" for Sports). (GH-#74)

### Sprint 22.5: The Pundit Ledger UI
- [ ] SP22-5: Create a public accountability dashboard ranking personalities by their Brier Score vs. Market Consensus. (GH-#82)

### Sprint 25: Growth, Monetization UX & Agentic ROI
- [/] SP25-3: auto-generate the 'Personality Magnet' visual infographic component to attract analysts/creators. (GH-#93)

### Sprint 28: UI Hardening & Visual Test Coverage (Team Logos)
- [ ] SP28-1: Investigate and fix the missing team logos on the Team Changer UI. (GH-#103)
- [ ] SP28-2: Implement Playwright visual regression tests specifically for the Team Changer grid. (GH-#104)
- [ ] SP28-3: Audit existing `e2e` Playwright test suite to identify gaps in coverage. (GH-#105)
