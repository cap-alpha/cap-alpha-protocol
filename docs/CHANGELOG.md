# Changelog

All notable changes to the "Cap Alpha Protocol" project will be documented in this file.

## [Unreleased] - 2026-02-18

### Added
- **Feat(Web)**: Added `CutCalculator` component with Pre/Post June 1 toggle logic.
- **Feat(Web)**: Added `PositionDistributionChart` to visualize player Cap Hit vs Market Peers.
- **Feat(Auth)**: Integrated Clerk Authentication (Middleware configured for local bypass on Port 3004).
- **Docs**: Added `ROADMAP.md` and `CHANGELOG.md` for project tracking.

### Fixed
- **Fix(Web)**: Resolved local development `EPERM` issues by bypassing `.env.local` read in middleware.
- **Fix(UI)**: Corrected `PlayerDetailView` layout grid for responsiveness on mobile.
- **Fix(Data)**: Updated `actions.ts` to handle edge cases where `roster_dump.json` has null/missing values.

### Technical Debt
- **Refactor**: Moved `PlayerEfficiencySchema` to `actions.ts` for better type safety.
- **CI/CD**: Added `docs/project_status/` syncing for persistent state tracking.

## [v0.1.0] - 2026-02-14

### Added
- **Core**: Initial Medallion Architecture Pipeline (`pipeline/dim_player.sql`, `pipeline/fact_contract.sql`).
- **Web**: Next.js 14 baseline with Tailwind CSS and ShadCN UI.
- **Data**: DuckDB local database integration.
