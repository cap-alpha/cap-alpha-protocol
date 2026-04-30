# Launch Checklist

> Last updated: 2026-04-30 | Managed by: GitHub Issues

## Gate 0 — Must-ship (P0)

Issues that block the launch binary. None of these may be open on launch day.

- [ ] [#473](https://github.com/andrewsmith/nfl-dead-money/issues/473) — Audit + land all open security CVE PRs
- [ ] [#474](https://github.com/andrewsmith/nfl-dead-money/issues/474) — Stripe webhook end-to-end correctness test
- [ ] [#475](https://github.com/andrewsmith/nfl-dead-money/issues/475) — Cryptographic ledger chain validator in CI
- [ ] [#476](https://github.com/andrewsmith/nfl-dead-money/issues/476) — ToS, Privacy Policy, FTC affiliate disclosure on every page
- [ ] [#477](https://github.com/andrewsmith/nfl-dead-money/issues/477) — Sentry (server + client) wired with Slack alerts
- [ ] [#478](https://github.com/andrewsmith/nfl-dead-money/issues/478) — Rate limiting audit — public + API surfaces
- [ ] [#479](https://github.com/andrewsmith/nfl-dead-money/issues/479) — Apply for EIN online (IRS SS-4, sole proprietorship)
- [x] [#481](https://github.com/andrewsmith/nfl-dead-money/issues/481) — Open business checking account under sole prop + EIN ✅
- [x] [#483](https://github.com/andrewsmith/nfl-dead-money/issues/483) — Verify Stripe accepts sole proprietorship + EIN (no LLC required) ✅
- [x] [#485](https://github.com/andrewsmith/nfl-dead-money/issues/485) — FTC affiliate disclosure — footer + per-page disclosure on all affiliate links ✅
- [x] [#488](https://github.com/andrewsmith/nfl-dead-money/issues/488) — $500 sports/entertainment law consult — pre-revenue legal review ✅
- [x] [#490](https://github.com/andrewsmith/nfl-dead-money/issues/490) — Responsible-gambling messaging visible site-wide (1-800-GAMBLER + resources) ✅
- [x] [#507](https://github.com/andrewsmith/nfl-dead-money/issues/507) — First-signup launch checklist (LAUNCH_CHECKLIST.md in repo) ✅

## Gate 1 — Pre-launch (P1)

Must be resolved within 1 week of launch.

- [ ] [#480](https://github.com/andrewsmith/nfl-dead-money/issues/480) — Prediction-resolution accuracy E2E test suite
- [ ] [#482](https://github.com/andrewsmith/nfl-dead-money/issues/482) — Written correction/retraction policy — public process for fixing wrong resolutions
- [ ] [#484](https://github.com/andrewsmith/nfl-dead-money/issues/484) — Stripe replay attack tests + access-grant idempotency hardening
- [ ] [#486](https://github.com/andrewsmith/nfl-dead-money/issues/486) — Refund flow tested with real $1 test-mode charge
- [ ] [#487](https://github.com/andrewsmith/nfl-dead-money/issues/487) — Cost alert bands — Vercel bandwidth + BigQuery spend
- [ ] [#489](https://github.com/andrewsmith/nfl-dead-money/issues/489) — BigQuery + cryptographic ledger backup verification
- [ ] [#491](https://github.com/andrewsmith/nfl-dead-money/issues/491) — Public status page — linked from site footer
- [ ] [#492](https://github.com/andrewsmith/nfl-dead-money/issues/492) — Apply to DraftKings affiliate program via Rakuten Advertising
- [ ] [#493](https://github.com/andrewsmith/nfl-dead-money/issues/493) — Security headers audit — target A+ on Mozilla Observatory
- [ ] [#494](https://github.com/andrewsmith/nfl-dead-money/issues/494) — Apply to FanDuel affiliate program
- [ ] [#495](https://github.com/andrewsmith/nfl-dead-money/issues/495) — Dependency vulnerability scan + Dependabot enabled
- [ ] [#496](https://github.com/andrewsmith/nfl-dead-money/issues/496) — Apply to PrizePicks affiliate program
- [ ] [#497](https://github.com/andrewsmith/nfl-dead-money/issues/497) — Login rate limiting + account enumeration prevention
- [ ] [#498](https://github.com/andrewsmith/nfl-dead-money/issues/498) — Apply to Underdog Fantasy affiliate program
- [ ] [#499](https://github.com/andrewsmith/nfl-dead-money/issues/499) — Mobile pass on real devices — iOS Safari + Android Chrome
- [ ] [#500](https://github.com/andrewsmith/nfl-dead-money/issues/500) — First affiliate link placement strategy + AB test plan
- [ ] [#501](https://github.com/andrewsmith/nfl-dead-money/issues/501) — Empty / loading / error state audit — every public route
- [ ] [#502](https://github.com/andrewsmith/nfl-dead-money/issues/502) — Audit Pro tier value prop — confirm gated features exist in code
- [ ] [#503](https://github.com/andrewsmith/nfl-dead-money/issues/503) — Lighthouse 90+ scores across all web routes
- [ ] [#504](https://github.com/andrewsmith/nfl-dead-money/issues/504) — Welcome email + onboarding sequence for first signup
- [ ] [#505](https://github.com/andrewsmith/nfl-dead-money/issues/505) — WCAG AA accessibility audit — keyboard nav, screen reader, color contrast
- [ ] [#506](https://github.com/andrewsmith/nfl-dead-money/issues/506) — Pre-launch closed beta plan — invite list + feedback + sign-off criteria
- [ ] [#508](https://github.com/andrewsmith/nfl-dead-money/issues/508) — LAUNCH_CHECKLIST.md — repo source of truth for launch gates
