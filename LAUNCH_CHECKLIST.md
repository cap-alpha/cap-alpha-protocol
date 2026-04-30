# Launch Checklist — First $1 Revenue Gate

**No public-launch communications until every P0 item is checked.**

This document is the single source of truth for launch readiness. Update it as each gate closes (one PR per update is fine).

---

## P0 — Blocking (must all be ✅ before launch)

- [ ] [#479] EIN obtained and recorded in 1Password — _Status: open_
- [ ] [#481] Business checking account open under sole prop + EIN — _Status: open_
- [ ] [#483] Stripe verified: accepts sole prop + EIN, test charge succeeded — _Status: open_
- [ ] [#485] FTC affiliate disclosure live on all pages — _Status: open_
- [ ] [#488] Sports law consult complete, written sign-off in hand — _Status: open_
- [ ] [#490] Responsible gambling messaging live site-wide (1-800-GAMBLER) — _Status: open_
- [x] [#141] Legal pages (ToS, Privacy, AUP) live — _Status: closed — verify still current_
- [ ] Stripe live-mode end-to-end test (real charge succeeds)
- [ ] Error tracking live (Sentry or equivalent)
- [ ] Affiliate programs approved: DraftKings, FanDuel, PrizePicks, Underdog
- [ ] Affiliate links live on prod with click tracking confirmed
- [ ] Welcome email lands in Gmail inbox (not spam)
- [ ] Pro tier gating verified in code

---

## P1 — Important, not blocking

- [ ] [#507] This checklist merged to main and kept up to date

---

## Notes

- Reference: #287 (closed — Launch checklist for cap-alpha.co infra, not revenue)
- Owner: whoever is driving the pre-revenue sprint
- Update this file as each issue closes; one PR per checklist update is sufficient
