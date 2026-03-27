## Phase 8: Structural Fixes & Board Audit Execution
- [x] Implement `ROW_NUMBER() OVER PARTITION` BigQuery query to resolve temporal data disparity.
- [x] Inject `timeoutMs` connection hardening for Next.js caching timeouts.
- [x] Build `global-error.tsx` to automatically intercept and hard-refresh Next.js chunk-loading timeouts (idle crash).

## Phase 9: Graceful Error UX & Sanitization
- [x] Deploy premium `error.tsx` component to safely fall back from database 500 crashes.
- [x] Audit UI for dead elements and strip `SaveScenario` API loops.
- [x] Draft 100-Point Master Execution Roadmap.
- [x] Execute `npm run build` structural check (0 Type Errors).

## Phase 9.5: Analytical UI Data Validation
- [x] Fix `CutCalculator` to empirically derive pre-June 1 Net Cap Savings when `savings_pre_june1` is null/0.
- [x] Add rendering boundaries to hide `Cap Hit Composition` visualization when base salaries and bonuses are unpopulated ($0M) due to Spotrac fallback scrapes.
## Phase 10: Sprint 0 (Production Safety)
- [ ] Configure Vercel Edge Feature Flags.
- [ ] Inject PostHog Telemetry funnel capture.
- [ ] Enable CI/CD deployment gating.
