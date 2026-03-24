# Link Every Player Name to Player Page

**Goal**: Ensure that wherever a player's name appears on the site, it is a clickable link pointing to their respective `/player/[id]` profile.

## Proposed Changes

We will inspect and modify the following UI components to wrap the `player_name` (or similar fields) with a Next.js `<Link href={\`/player/\${encodeURIComponent(slugify(playerName))}\`}>` component. We will import `Link` from `next/link` and `slugify` from `@/lib/utils` where missing.

### Components to Update
#### [MODIFY] `web/components/point-in-time-ledger.tsx`
Wrap the `<h3...>{currentReceipt.player_name}</h3>` tag.

#### [MODIFY] `web/components/roster-card.tsx`
Wrap the player name in the card title/header.

#### [MODIFY] `web/components/proof-of-alpha-carousel.tsx`
Wrap the player name in the carousel slides.

#### [MODIFY] `web/components/efficiency-landscape.tsx`
Ensure custom tooltip or selected player details link out to the player page.

#### [MODIFY] `web/components/cut-calculator.tsx`
Link the player name displayed in the title or summary.

### Data Pipeline & Accuracy
*   **Fix Cap Hit Anomaly**: The `pipeline/scripts/medallion_pipeline.py` currently renames `total_contract_value_millions` to `cap_hit_millions` due to a flawed `df.rename` mapping. This will be corrected to use actual `cap_hit` data so Mahomes shows ~$37M instead of $450M.
*   **Ingest 2025 Data**: We will run the pipeline explicitly for 2025 to generate the latest features into MotherDuck so the `MAX(year)` query in UI hits 2025 data.

### Automation
*   **Daily Sync Workflow**: Create or update a GitHub Action (e.g., `.github/workflows/sync_daily.yml`) to automatically run the medallion pipeline for the current year (2025) and sync it to MotherDuck every day on a `cron` schedule (`0 4 * * *`).

### UI Layout & Design
*   **Timeline Layout Reorganization**: Modify `web/components/player-detail-view.tsx` to extract the `VisualTimeline` from the tabs and position it vertically along the right side of the page on desktop (`lg:col-span-3` in a new overarching 12-col grid). On mobile, ensure it shifts to the 2nd or 3rd position below the name and key stats.
*   **Tufte-Inspired Timeline**: Redesign `web/components/visual-timeline.tsx` in a vertical format enforcing maximum data-ink ratio. Remove heavy borders, neon rings, animations, and large empty spaces. Use minimalist text, high-density timestamps, and subtle indicators (sparkline integration if applicable).

#### [MODIFY] `pipeline/scripts/medallion_pipeline.py`
#### [MODIFY] `web/components/player-detail-view.tsx`
#### [MODIFY] `web/components/visual-timeline.tsx`
#### [NEW/MODIFY] `.github/workflows/sync_daily.yml`
#### [MODIFY] `web/components/landing-hero.tsx`
Check for player name usage in the hero feed/events and add links.

#### [MODIFY] `web/components/war-room-dashboard.tsx`
Check for active player selections or tables and add links.

#### [MODIFY] `web/app/dashboard/fan/page.tsx`
#### [MODIFY] `web/app/dashboard/bettor/page.tsx`
#### [MODIFY] `web/app/page.tsx`
Check for hardcoded or statically rendered player names and ensure they are wrapped in links.

*(Note: `web/components/roster-grid.tsx` already implements this pattern correctly, so we'll use it as the template).*

## Verification Plan

### Automated Tests
1. No new automated test is specifically required for this beyond standard type-checking. I will run `npm run build` or rely on `tsc` to verify that there are no type errors after importing `Link` and `slugify` into the various files.

### Manual Verification
1. Open the local dev server (currently running).
2. Browse through the front page, the Point-in-Time Ledger, the Proof of Alpha block, and the various dashboards (Fan, Bettor, War Room).
3. Click on the newly formatted player names.
4. Verify that the routing correctly resolves to the `PlayerDetailView` for that specific player without throwing 404s.
