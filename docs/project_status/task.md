# Trade Engine Refinement & Verification

- [ ] Inspect Russell Wilson contract data to ensure data integrity [/]
- [ ] Run `pipeline/tests/test_find_buyer.py` to baseline current logic [/]
- [x] Locate correct virtual environment (`integration_venv` patched with `pandas`)
- [ ] Refine `TradePartnerFinder` logic based on test results and data inspection
- [ ] **NEW**: Investigate/Setup Playwright for E2E Persona Testing [x] (Configured, but runtime blocked by local perms)
- [ ] **NEW**: Create "Persona Test Plan" for GM, Fan, and Agent workflows [x]
- [x] **UI Fix**: Formatting "Market Efficiency" Chart X-Axis (remove decimals)
- [x] **UI Fix**: Formatting "Market Efficiency" Chart Y-Axis (fix overlap/scale)
- [x] **UI Fix**: Right-justify numeric columns in Data Grid
- [x] **Verification**: Create comprehensive E2E suite (Desktop + Mobile)
- [x] **UI Fix**: Branding "Cap Alpha Protocol" in top-left
- [x] **UI Fix**: Hide "0 Teams" metric (Optics)
- [x] **UI Fix**: Add Tooltips to Data Grid headers (Cap Hit, Risk, Surplus)
- [ ] **UI Fix**: Rename "Surplus" column to "Value"
- [x] **UI Fix**: Rename "Surplus" column to "Value"
- [x] **Verification**: Generate detailed "Walkthrough" with mobile screenshots
- [ ] **E2E Testing**: Design comprehensive Playwright Test Plan (Desktop/Mobile/Auth) [x]
- [x] **Auth**: Implement Clerk "My Team" Onboarding Flow
- [x] **Ingestion**: Run data pipeline for 2025 season.
- [x] **Verification**: Confirm 2025 data is present in `nfl_dead_money.duckdb` (Verified in UI).
## 3. Core Utility: The "Cut Calculator"
- [x] **Simulation**: Create `pipeline/src/simulate_history.py` (Filtered existing Walk-Forward Data to 2022-2024).
- [x] **Data**: Overwrite `historical_predictions.json` with simulation results.
- [ ] **UI**: Validate `PlayerDetailView` reflects this new "Honest History".
- [ ] **UI**: Implement Sparkline Component in Data Grid
- [ ] **UI**: Build Player Detail View (Error Analysis & Trajectory)
- [x] **UI**: Build Player Detail View (Error Analysis & Trajectory)
- [x] **Feature**: Implement "Cut Calculator" Logic (Pre/Post June 1) - **Essential Product Bridge & Monetization Engine**.
    - [x] Logic: Calculate `dead_cap_pre_june_1`, `savings_pre_june_1`, etc. (Python Backend).
    - [x] UI: "The Guillotine" Toggle (Keep vs Cut).
    - [x] UI: Visual Delta (Savings/Hit) - Conversion Hook for "Armchair GM".
- [x] **Assets**: Add Team Logos to Onboarding Modal (Quality Requirement)

## 4. Finalization (The "Hour Sprint" Close)
- [x] **Git**: Commit and Push all changes to remote.
- [x] **Audit**: Conduct Skills/Persona Audit (Usage vs Gap Analysis).

## 5. Post-Launch: User Data Infrastructure (Vercel Stack)
- [ ] **Database**: Provision **Vercel Postgres** (managed by Neon) for user data.
- [ ] **ORM**: Install **Drizzle ORM** (lightweight, edge-compatible) to manage schema.
- [ ] **Sync**: Implement Clerk Webhook to sync `user.created` events to Postgres.
- [ ] **Feature**: Save "Cut Scenarios" to `user_scenarios` table.
