# Task List

## Optimization & Stabilization (Completed)
- [x] Identify UI components displaying player names.
- [x] Import `next/link` and `slugify` utility.
- [x] Wrap player names in `<Link href={\`/player/\${encodeURIComponent(slugify(player_name))}\`}>`.
- [x] Verify routing integrity across the application.

## Cap Hit Accuracy & 2025 Pipeline
- [x] Fix data parsing in `medallion_pipeline.py` to prevent `total_contract_value_millions` from overwriting `cap_hit_millions`.
- [x] Add explicit daily cron trigger in `.github/workflows/` or equivalent to sync 2025 data to MotherDuck automatically.
- [x] Run full pipeline manually for 2025 (`medallion_pipeline.py --year 2025` and `sync_to_motherduck.py`) to verify data update.

## Timeline Tufte Redesign
- [x] Update layout in `player-detail-view.tsx` to mount `<VisualTimeline>` vertically on the right side of the screen on desktop.
- [x] Refactor `visual-timeline.tsx` enforcing high data-ink ratio (Edward Tufte principles), removing heavy chartjunk, and creating a clean, tight, sparkline-inspired log.
