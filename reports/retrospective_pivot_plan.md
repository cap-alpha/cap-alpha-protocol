# Product UX Overhaul Plan (Sprint 2 Retrospective Pivot)

*Based on Stakeholder Feedback Document: 1FBHLZz6TqOt64TxejlUWUTnBAeYI1MbrD_yPtRqNqlI*

## Goal Description
The Sprint 2 Retrospective highlighted a critical disconnect between the technical engineering and the **User Experience (UX)**. The generic "Dashboard" with its "Portfolio", "Data Grid", and "War Room" tabs was deemed confusing and lacking a coherent user story. 

The mandate is clear: We must pivot the UI architecture to explicitly support two distinct "Experiences":
1.  **The Real Team Follower:** A curated dashboard focused entirely on tracking a specific NFL franchise.
2.  **The Fantasy Team Builder:** A seamless, rapid roster-building interface requiring under 5 seconds to add a player.

Furthermore, the individual Player data visualizations must be completely overhauled to include synchronized sparklines, dynamic imagery, and longitudinal FMV projections extending to the present day (March 2026).

---

## Proposed Changes (The UX Architecture)

### 1. Global Navigation & State Management
*   **The Switcher:** Implement a persistent, global toggle in the Next.js header allowing users to instantly switch between `[REAL MODE]` and `[FANTASY MODE]`.
*   **Context Refactor:** Update `web/components/persona-context.tsx` or create a new `mode-context.tsx` to handle this high-level routing redirection.

### 2. The "Real Team Follower" Experience
*   **Target File:** `web/app/dashboard/page.tsx`
*   **Action:** Delete the current multi-tab layout. 
*   **Implementation:** Replace it with the team-selector interstitial (which previously showed team logos). Upon selecting a team (e.g., Dallas Cowboys), the dashboard should rigidly lock to visualizing *only* that roster's cap exposure and active players.

### 3. The "Fantasy Team" Experience
*   **Target File:** `web/app/fantasy/page.tsx` (or new route)
*   **Action:** Build a lightning-fast "Draft/Add" interface.
*   **Implementation:** Focus on keystroke efficiency. A global command palette (cmd+k) style search bar where a user types "Dak", hits Enter, and the player is instantly added to their tracked list without traversing menus.

### 4. The Player Card & Page Redesign
*   **Target Files:** `web/components/roster-card.tsx` & `web/components/player-detail-view.tsx`
*   **Card Updates:** Remove esoteric jargon like "Efficiency Gap." Ensure the card displays: Name, Position, Tenure (Seasons with current team), and Current Cap Hit. Add a "Data Freshness" indicator (e.g., "Updated 2 hrs ago").
*   **Page Visuals:**
    *   **Synced Sparklines:** Directly below the main FMV comparison chart, implement multiple Recharts sparklines (Yards, Touchdowns, EPA) where hovering over the X-Axis on *one* chart displays the tooltip across *all* charts simultaneously.
    *   **Mobile Zoom:** Ensure the charts support responsive pinching/panning to switch between Weekly/Monthly granularity.
    *   **Media Gallery:** Integrate a rotating image carousel of the player in their most recent uniform.
    *   **Future Projections:** The FMV chart must extend into the future with confidence bands plotting expected Cap Hit vs. projected FMV.

---

## Execution Constraints & "The Hard Stop"

> [!CAUTION]
> **Data Availability & The MotherDuck Block**
> The retrospective demands Weekly FMV data, synchronized game statistics (Yards, Points), and Future Projections up to March 2026. 
> 
> **Our current `roster_dump.json` DOES NOT contain this depth of longitudinal, weekly statistical data.** It only contains aggregate yearly cap numbers.
> 
> To fulfill the synced sparklines and the "March 2026" timeline request, we *must* execute the MotherDuck database pivot (Sprint 3) to stream the dense, multi-year feature space from Python to Next.js. We cannot build the Recharts sparklines if the data does not exist in the frontend.

---

## User Review Required

> [!IMPORTANT]
> **Architectural Conflict**
> The Retrospective demands deep, weekly statistical visualizations. However, our frontend is currently hardcoded to a JSON file lacking this data.
> 
> **Decision Required:** 
> Do you want me to build the *UI Shells* for these new features right now using entirely Fake/Generated Mock Data just to get the layout approved, OR do we pause the UX overhaul and execute the data pipeline (MotherDuck) first so we have the real weekly stats to plug into the new sparklines?
