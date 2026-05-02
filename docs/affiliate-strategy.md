# Affiliate Link Placement Strategy & AB Test Plan

_Last updated: 2026-05-01 · Issue #500_

---

## Affiliate Programs

| ID | Platform | Category | Tag |
|----|----------|----------|-----|
| #492 | DraftKings Sportsbook | Sportsbook | `draftkings` |
| #494 | FanDuel Sportsbook | Sportsbook | `fanduel` |
| #496 | PrizePicks | DFS | `prizepicks` |
| #498 | Underdog Fantasy | DFS | `underdog` |

Tracking links are set via env vars so they can be swapped without code changes:

```
NEXT_PUBLIC_AFF_DRAFTKINGS=<your-draftkings-affiliate-url>
NEXT_PUBLIC_AFF_FANDUEL=<your-fanduel-affiliate-url>
NEXT_PUBLIC_AFF_PRIZEPICKS=<your-prizepicks-affiliate-url>
NEXT_PUBLIC_AFF_UNDERDOG=<your-underdog-affiliate-url>
```

---

## Placement Strategy

### Placement 1 — Pundit Scorecard (`/ledger/[pundit_id]`)

**Context:** User has just read a pundit's accuracy card. They know whether to trust this pundit's picks.

**CTA copy:**
- High-accuracy pundit (≥60%): _"[Pundit] is on a run. Back their calls on DraftKings."_
- Low-accuracy pundit (<50%): _"Fade [Pundit]. Bet against them on FanDuel."_
- Default: _"See where the smart money goes. Join DraftKings."_

**Placement:** After the stat row, before the Category Breakdown section.

**AB Variant:** Variant A = DraftKings, Variant B = FanDuel.

**FTC disclosure:** `AffiliateDisclosure` component rendered immediately below CTA.

**Umami event:** `affiliate_click` with properties `{ platform, placement: "pundit_scorecard", pundit_id, variant }`.

---

### Placement 2 — Homepage Hero (`/`)

**Context:** First-time visitor; intent is broad sports-prediction curiosity.

**CTA copy:** _"Turn pundit accountability into profit — join DraftKings/PrizePicks."_

**Placement:** Below the leaderboard preview section.

**AB Variant:** Variant A = DraftKings (sportsbook), Variant B = PrizePicks (DFS / lower-friction for new users).

**FTC disclosure:** `AffiliateDisclosure` component below CTA.

**Umami event:** `affiliate_click` with properties `{ platform, placement: "homepage_hero", variant }`.

---

### Placement 3 — Ledger Listing Footer (`/ledger`)

**Context:** User browsed the full pundit list; likely engaged but not yet committed to a specific pundit.

**CTA copy:** _"Ready to act on the data? Sign up at Underdog Fantasy."_

**Placement:** In the `ledger/layout.tsx` footer, between the nav links and copyright.

**AB Variant:** Variant A = Underdog Fantasy, Variant B = PrizePicks.

**FTC disclosure:** Inline text linked to `/legal/disclosure`.

**Umami event:** `affiliate_click` with properties `{ platform, placement: "ledger_footer", variant }`.

---

## AB Test Plan

### Assignment

- Variant is assigned once per browser via `localStorage.getItem("aff_variant")`.
- If absent, `Math.random() < 0.5` → `"A"` else `"B"`. Written to localStorage immediately.
- Assignment is stable across page loads; cleared on logout (optional).

### Duration

- Minimum run: **14 days** (enough for ~2 NFL news cycles and weekend traffic peaks).
- Target: ≥200 click events per variant per placement before calling a winner.

### Conversion Metric

Primary: **affiliate click-through rate** = `affiliate_click` events ÷ page views (tracked in Umami).

Secondary (when affiliate dashboard data is available): **sign-up conversion rate** per platform.

### Decision rule

- If CTR(A) / CTR(B) > 1.15 (15% relative lift) with ≥200 samples per arm → declare winner.
- If no significant difference after 28 days → keep the lower-friction / lower-vig option (DFS > sportsbook for acquisition).

### Tracking checklist

- [ ] Umami `affiliate_click` events appear in dashboard under "Custom Events"
- [ ] Vercel Analytics referral paths show `/legal/disclosure` in-flow (indicates pre-click disclosure)
- [ ] Affiliate platform dashboards (DraftKings, FanDuel, PrizePicks, Underdog) show incoming clicks within 48 h of going live

---

## FTC Compliance

Every placed link uses the `<AffiliateLink>` component, which:
1. Renders the link with `rel="noopener noreferrer sponsored"`.
2. Renders `<AffiliateDisclosure>` immediately after the link.
3. Fires the Umami `affiliate_click` event on click.

Full disclosure page: `/legal/disclosure`.
