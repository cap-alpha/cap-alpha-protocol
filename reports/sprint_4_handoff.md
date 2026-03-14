# Sprint 4 Execute & Handoff Plan
*Project Nexus / NFL Dead Money Protocol*

## Executive Summary
This document serves as the formal handoff and execution alignment for **Sprint 4: Product UX Overhaul**. Based on the Sprint 2 retrospective, we are pivoting the platform from a "Generic Sandbox" into a directed "Persona-First" experience. 

## The Core Deliverables

### 1. Global State Architecture (Real vs. Fantasy)
*   **The Problem:** Users are confused by the generic "Dashboard" without context.
*   **The Fix:** We must implement an App-wide `ModeContext`. 
*   **Handoff Dependency:** The Next.js layout must wrap all pages in this provider so that the top Navigation bar can toggle between `[ TRACKING DALLAS COWBOYS ]` and `[ MANAGING FANTASY ROSTER ]`.

### 2. The Health & Sentiment Integration
*   **The Problem:** We acquired unstructured injury logs and media embeddings, but they had nowhere to live on the UI.
*   **The Fix:** I have implemented a modular `Tabs` interface on the `PlayerDetailView` separating historical ledgers from the new `IntelligenceFeed`. I also added a `report_status` persistent badge to the top-level player identifier.
*   **Handoff Dependency:** The `actions.ts` mock generators have been updated to support these schema fields. When the MotherDuck `fact_player_efficiency` table is rebuilt, it must `LEFT JOIN` on the most recent `bronze_layer.nflverse_injuries` record.

### 3. Rapid Roster Add (The Fantasy Loop)
*   **The Problem:** The Fantasy workflow is too slow for "Armchair GMs."
*   **The Fix:** Build a `cmdk` (Command Palette) component.
*   **Handoff Dependency:** Needs a fuzzy-search implementation connecting to a flat list of all active NFL players.

### 4. Synced Multi-Metric Sparklines
*   **The Problem:** Player valuation charts lack supporting statistical context (Yards, TDs).
*   **The Fix:** Recharts syncId linking over sequential timeseries data.
*   **Handoff Dependency:** *BLOCKED.* We cannot build this until the MotherDuck pipeline pushes weekly granularity to the Next.js backend. Current DB schema is Year-over-Year only.

## Actionable Next Steps

### Web Sprint Track (Frontend Team)
1.  **Global Toggle:** Proceed with building the `ModeContext` global switcher in the header.
2.  **Command Palette:** Mock the `cmdk` rapid-add feature for the Fantasy experience layout.
3.  **UI Verification:** Validate the new `PlayerDetailView` layout structure on mobile viewports.

### Backend Sprint Track (Data Engineering & Python Team)
1.  **Weekly Grain Aggregation:** Prioritize writing the MotherDuck view execution to aggregate weekly statistics, unblocking the Web Team's Sparkline deliverable.
2.  **Projection Extension:** Extend the Python backtesting baseline to project FMV capabilities through March 2026.
3.  **Schema Consolidation:** Ensure `report_status` and sentiment embeddings are structurally joined into the main `fact_player_efficiency` table for O(1) reads.
