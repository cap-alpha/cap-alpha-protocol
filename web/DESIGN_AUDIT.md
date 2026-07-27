# Design Consistency Audit — `web/`

Date: 2026-07-27
Scope: all 32 routes under `web/app/**/page.tsx`, the shared shell (`app/layout.tsx`,
`components/navbar.tsx`, `components/footer.tsx`), the design-system sources
(`tailwind.config.ts`, `app/globals.css`), and the shared UI primitives
(`components/ui/{button,card,badge}.tsx`).

## TL;DR

The design system itself is in reasonable shape — `tailwind.config.ts` defines a
real color-token layer (`canvas`/`ink`/`accent-editorial`/`gold`/`correct`/
`incorrect`/`pending`, "V1 Data Editorial") and a real typographic scale
(`display-xl` → `label`). The problem is **adoption**, not design: the token
scale is barely used, only 2 of 32 pages consume the editorial color palette,
and every page re-implements its own container width, heading style, and badge
chrome by hand. This is a site caught mid-migration — `app/globals.css` and
`tailwind.config.ts` both contain comments referencing an in-flight "full sweep"
(issue #1070) to repoint the whole app at the editorial tokens — but only
`/` (home) and `/ledger` have actually made the jump.

Quantified headline findings:

| Finding | Magnitude |
|---|---|
| Pages using the editorial token palette (`bg-canvas`/`text-ink`/`accent-editorial`) | **2 of 32** (`/`, `/ledger`) |
| Pages using the legacy ad hoc dark palette (`bg-black`, `text-white`, `zinc-9xx`, `emerald-500`, `slate-8xx`) | **27 of 32** |
| Adoption of the custom fontSize scale (`display-*`, `heading-*`, `body-*`, `label`, `mono-*`) anywhere in `app/` or `components/` | **0 usages** — fully dead config |
| Distinct `<h1>` size/weight/tracking/casing combinations across 24 page-level `<h1>`s | **~14 distinct combos**, no two pages share an identical style |
| Distinct top-level page container max-widths in use | **5** (`max-w-3xl`/`4xl`/`5xl`/`6xl`/`7xl`), no shared wrapper component |
| Arbitrary `text-[Npx]` micro-typography values (not in the token scale, not default Tailwind sizes) | **71 occurrences**, 4 distinct values (9/10/11/12px), concentrated in `app/ledger/page.tsx` (40) |
| Ad hoc "eyebrow" pill-badge re-implementations (`rounded-full border px-3 py-1 text-xs uppercase tracking-widest`) instead of the shared `<Badge>` | **9 occurrences across 5 pages**, 3 different color schemes |
| Page-level `<Button>` usage across all 32 `page.tsx` files | **1** (the shared `Button`/`Card`/`Badge` primitives *are* used inside `components/`, just rarely at page-composition level) |
| Shared `Navbar`/`Footer` (rendered on literally every page via `app/layout.tsx`) use their own hardcoded palette (`slate-*`, `emerald-*`, `amber-*`, `text-white`) | Independent of *both* the editorial tokens and the legacy dark tokens — a third, unreconciled palette |

---

## 1. Color

| # | File:Line | Mismatch | Severity |
|---|---|---|---|
| 1.1 | `app/globals.css:41-53`, `app/tailwind.config.ts:78-113` vs. **27/32 pages** | Editorial palette (`--canvas #FAF8F5`, `--ink #1A1A1A`, `--accent-editorial #1A2744`, `--gold #B8860B`, `--correct/--incorrect/--pending`) is defined and used by only `/` and `/ledger`. Every other page (`dashboard/*`, `entity/*`, `legal/*`, `docs`, `methodology`, `quality`, `verify`, `pricing`, `status`, `team/[id]`, `fantasy`, `scenarios`, …) is still on the pre-existing dark theme: `bg-black`/`bg-zinc-950` + `text-white` + raw Tailwind palette accents (`emerald-500`, `rose-500`, `amber-*`, `slate-8xx`). Two co-existing design languages, not one. | **Systemic / highest visibility** |
| 1.2 | `components/navbar.tsx` (colors: `bg-emerald-400/500`, `text-slate-300`, `text-white`, `bg-white`/`text-black`) and `components/footer.tsx` (`bg-slate-950`, `bg-amber-950`, `text-amber-100..500`, `text-emerald-400/500`, `text-slate-300/400`) | The shared shell rendered on **every single page** (via `app/layout.tsx`) uses a third palette that matches neither the editorial tokens nor the legacy dark tokens consistently — e.g. on `/` and `/ledger` the nav/footer chrome is visibly a different "dark app" look sitting above/below light editorial page content. | **Systemic / highest visibility** — but out of scope for this PR (see Deferred). |
| 1.3 | `app/search/page.tsx:30-50` | Defines a full **duplicate hex palette** as scoped inline CSS custom properties (`--search-bg: #F7F4EF`, `--search-navy: #1A2744`, `--search-gold: #B8860B`, `--search-pos: #1A7A4A`, …) instead of consuming the canonical `--canvas`/`--accent-editorial`/`--gold`/`--correct` tokens from `globals.css`. Of the 15 values, **8 are byte-identical** to an existing token (`card`, `navy`, `navy-lt`, `gold`, `gold-lt`, `pos`, `neg`, `warn`); the remaining 7 (`bg`, `raised`, `text`, `md`, `lt`, `border`, `blt`) are near-duplicates that have quietly drifted from `--canvas`/`--ink`/`--ink-2`/`--ink-3`/`--border-editorial` by a few HSL points each — close enough to look intentional, different enough that this page's text/border contrast is not actually the same as the rest of the editorial surface. Consumed by 66 call sites across 5 components (`components/search/*.tsx`). | High — one file, but a textbook "hardcoded hex instead of token" case. **Partially fixed in Phase 2** (the 8 exact matches). |
| 1.4 | `app/page.tsx:63` uses `border-navy/30 bg-navy/10 text-navy` (legacy alias tokens); `app/quality/page.tsx:524`, `app/methodology/page.tsx:116,227`, `app/verify/page.tsx:69` use `border-emerald-500/30 bg-emerald-500/10 text-emerald-400` (raw Tailwind palette); `app/verify/page.tsx:109,181,209,236` use `border-zinc-700 bg-zinc-900 text-zinc-400` | Same semantic role ("eyebrow" label chip) rendered with 3 unrelated color sources on different pages — legacy alias token, raw Tailwind `emerald-500`, raw Tailwind `zinc-700/900`. | Medium |
| 1.5 | `app/dashboard/bettor/page.tsx:44` `bg-rose-500/10 border-rose-500/30`; `app/share/player/[slug]/page.tsx:84` `bg-amber-950/40 border-amber-900/30`; various | Semantic "warning/negative" surfaces use raw palette colors (`rose-500`, `amber-950`) instead of the `--incorrect`/`--pending`/`--warn` tokens that already exist for exactly this purpose. | Medium |

## 2. Typography

| # | File:Line | Mismatch | Severity |
|---|---|---|---|
| 2.1 | `tailwind.config.ts:30-43` vs. all of `app/`+`components/` | The custom `fontSize` scale (`display-xl/lg/md`, `heading-xl/lg/md`, `body-lg/md/sm`, `label`, `mono-lg/sm`) has **zero consumers**. It was designed to be the canonical heading/body scale but no page or component uses `text-display-*`, `text-heading-*`, `text-body-*`, or `text-label`. | **Systemic / highest leverage** |
| 2.2 | 24 page-level `<h1>` elements (full list: `app/page.tsx:71`, `ledger/page.tsx:1053`, `quality/page.tsx:528`, `verify/page.tsx:73`, `entity/[entity_type]/page.tsx:57`, `entity/[entity_type]/[entity_id]/page.tsx:556`, `methodology/page.tsx:231`, `admin/quality/runs/page.tsx:113`, `status/page.tsx:195`, `docs/page.tsx:143`, `dashboard/usage/page.tsx:31`, `dashboard/bettor/page.tsx:48`, `dashboard/billing/page.tsx:25`, `team/[id]/page.tsx:79`, `scenarios/page.tsx:26,36` (two `<h1>`s on one page — see 2.4), `legal/*` ×6, `pricing/page.tsx:13`, `fantasy/page.tsx:20`) | Sizes range `text-2xl` → `text-4xl`/`sm:text-5xl`; weights split across `font-bold`/`font-extrabold`/`font-black`; tracking `tracking-tight` vs. unset; casing plain vs. `uppercase`; color `text-white`/`text-foreground`/`text-ink`/`text-emerald-500`/unset. No two pages share an identical combination. | **Systemic / highest visibility** |
| 2.3 | `app/legal/*/page.tsx` (6 files) | Smaller, self-contained instance of 2.2: 5 of 6 legal pages already agree on `text-3xl font-extrabold tracking-tight`, but only `disclosure` adds `font-display` and `acceptable-use` is the outlier at `text-4xl font-black`. **Fixed in Phase 2** (cheap, contained, unambiguous win). | Low blast-radius, high signal |
| 2.4 | `app/scenarios/page.tsx:26` and `:36` | Two `<h1>` elements on one page ("CAP ALPHA PROTOCOL // EXECUTIVE SUITE" and "My Dashboard") — an accessibility/semantic issue, not just a style one. | Medium (semantic, not visual — flagged for follow-up, not a design-consistency fix) |
| 2.5 | 71 occurrences of arbitrary `text-[Npx]` across `app/ledger/page.tsx` (40), `app/entity/[entity_type]/[entity_id]/page.tsx` (25), `app/team/[id]/page.tsx` (3), `app/page.tsx`, `app/methodology/page.tsx`, `app/dashboard/bettor/page.tsx`, `app/entity/[entity_type]/page.tsx` (1 each) | Values are 9px ×9, 10px ×46, 11px ×16, 12px ×1. None of these are in the fontSize token scale; the smallest token (`label`) is 12px. The single `text-[12px]` (`app/entity/[entity_type]/[entity_id]/page.tsx:845`) is redundant with Tailwind's built-in `text-xs` (0.75rem = 12px). **Fixed in Phase 2.** | Medium — high count, low per-instance visual stakes (micro-text in dense tables) |
| 2.6 | `font-display`/`font-body`/`font-sans`/`font-serif` usage: `font-display` 8×, `font-sans` 6×, `font-serif` 1×, vs. `font-mono` 212× | Not itself a problem (most pages correctly inherit `font-body` from `<body>` in `app/layout.tsx`), but the handful of pages that *do* set an explicit heading font (`font-display`) do so inconsistently — e.g. within the legal cluster only 1 of 6 (see 2.3). | Low |

## 3. Spacing & Layout

| # | File:Line | Mismatch | Severity |
|---|---|---|---|
| 3.1 | Container max-widths across pages: `max-w-3xl` (legal ×6, verify sections, status inner), `max-w-4xl` (dashboard/usage ×2), `max-w-5xl` (`quality`, `methodology`, `docs`, `pricing`), `max-w-6xl` (`ledger` ×4, `scenarios`, `entity/*` ×3, `admin/quality/runs` ×2), `max-w-7xl` (`fantasy`, `team/[id]`) | No shared container component; every page hand-writes `<div className="max-w-Nxl mx-auto [px-N] [py-N]">`. Widths are inconsistent even for structurally similar pages (e.g. `dashboard/usage` at `4xl` vs `fantasy`/`team/[id]` at `7xl`, both single-column dashboard-style pages). `tailwind.config.ts:13-19` already defines a `container` theme (`center: true, padding: "2rem", "2xl": "1400px"`) that is used correctly nowhere and misused once (`scenarios/page.tsx:34`: `container mx-auto px-4 py-4 max-w-6xl` — combining Tailwind's responsive `container` class with a manual `max-w-6xl` override is redundant/contradictory). | **Systemic** |
| 3.2 | `app/dashboard/usage/page.tsx:24,42` vs. `app/fantasy/page.tsx:14` vs. `app/team/[id]/page.tsx:66` | `fantasy` and `team/[id]` use byte-identical wrapper markup (`<main className="min-h-[100dvh] bg-background text-foreground p-8"><div className="max-w-7xl mx-auto space-y-8">`) copy-pasted across two files instead of a shared layout component. | Medium (DRY, not visual) |
| 3.3 | Card/panel padding: `p-6` (shadcn `CardContent`/`CardHeader` default), `p-5` (`verify/page.tsx:159`), `p-6 sm:p-8` (`methodology/page.tsx:142`), `px-3 py-2` (`ledger/page.tsx:399` and others) | No consistent card-padding scale; same visual "card" concept gets 4+ different padding values depending on which page wrote it by hand instead of using `<Card>`/`<CardContent>`. | Medium |

## 4. Components

| # | File:Line | Mismatch | Severity |
|---|---|---|---|
| 4.1 | `app/page.tsx:63`, `app/quality/page.tsx:524`, `app/methodology/page.tsx:116,227`, `app/verify/page.tsx:69,109,181,209,236` | 9 hand-rolled "eyebrow" pill badges (`inline-flex items-center gap-2 px-3 py-1 rounded-full border ... text-xs font-mono font-medium uppercase tracking-widest`) across 5 pages, 3 different color schemes, none going through the shared `<Badge>` (`components/ui/badge.tsx`) which is imported in only 1 `page.tsx` file site-wide. **Fixed in Phase 2** via a new `eyebrow` badge variant. | High — clean, mechanical, high-signal fix |
| 4.2 | `app/quality/page.tsx:234-246` (`TrendBadge`, local) vs. `app/methodology/page.tsx:103-121` (`SectionHeader`, local, different prop API than `app/quality/page.tsx:151`'s `SectionHeader` which takes an `icon` prop instead of `label`) | Multiple pages independently define local helper components with the same name and overlapping purpose but incompatible APIs. Not fixed in this PR (page-specific component consolidation, out of scope — see Deferred). | Medium |
| 4.3 | `app/team/[id]/page.tsx:69`, `app/fantasy/page.tsx:16` | Identical hand-written back-button styling (`className="p-2 hover:bg-slate-800 rounded-full transition-colors text-slate-400"`) duplicated verbatim across 2 files instead of a shared `IconButton`/`BackButton`. | Low (small, but a real duplicate) |
| 4.4 | Page-level `<Button>` adoption: 1 of 32 `page.tsx` files | The shared `Button` primitive is used inside `components/` (14 of 78 component files) but pages themselves overwhelmingly hand-roll interactive elements (raw `<Link>`/`<button>` with ad hoc `rounded ... px-N py-N` classes — 17 occurrences of button-shaped ad hoc markup found in `page.tsx` files alone). Not fixed in this PR — each is a page-specific judgment call about which `Button` variant applies. | Medium (documented, deferred) |

---

## What was fixed in this PR (Phase 2 — systemic only)

1. **New `components/ui/heading.tsx`** — `PageHeading` component (`font-display text-3xl font-extrabold tracking-tight`), the canonical h1 treatment already used by 5 of 6 legal pages. Applied to all 6 `app/legal/*/page.tsx` files, which also fixes the `acceptable-use` outlier (was `text-4xl font-black`).
2. **New `components/ui/page-container.tsx`** — `PageContainer` component with a `size` prop (`2xl`…`7xl`) that maps 1:1 onto the max-widths already in use, removing hand-written `max-w-Nxl mx-auto` boilerplate. Applied to `app/pricing/page.tsx`, `app/dashboard/usage/page.tsx` (×2), `app/status/page.tsx`, `app/fantasy/page.tsx`, and `app/team/[id]/page.tsx` — chosen because each has a single, unambiguous top-level wrapper (zero visual diff; same literal width value carried over).
3. **`components/ui/badge.tsx`** — added an `eyebrow` variant capturing the shape/spacing/typography shared by all 9 ad hoc pill badges (§4.1). Applied to `app/page.tsx`, `app/quality/page.tsx`, `app/methodology/page.tsx` (×2), `app/verify/page.tsx` (×5); each call site keeps its own existing border/bg/text color via `className` (color choice intentionally untouched — see Deferred).
4. **`app/search/page.tsx`** — the 8 values in the scoped `pageStyle` block that are byte-identical to a canonical token (`card`, `navy`, `navy-lt`, `gold`, `gold-lt`, `pos`, `neg`, `warn`, §1.3) now alias `hsl(var(--surface))`/`hsl(var(--accent-editorial))`/etc. instead of repeating the hex literal — zero visual diff, and the page now tracks any future palette change automatically. The 7 near-but-not-exact values (`bg`, `raised`, `text`, `md`, `lt`, `border`, `blt`) were deliberately left as their current literal hex — forcing them onto the closest token would visibly lighten this page's secondary text/border contrast, which needs a screenshot diff, not a mechanical PR (see Deferred). Zero changes needed in the 5 consuming `components/search/*.tsx` files since they still reference the same `var(--search-*)` custom-property names — only the *source* of the 8 aliased values changed.
5. **`app/entity/[entity_type]/[entity_id]/page.tsx:385`** — `text-[12px]` → `text-xs` (redundant arbitrary value; Tailwind's default `text-xs` is already 0.75rem/12px).

All five are zero- or near-zero visual-diff, mechanical, and reviewable in isolation.

## Deferred — follow-up checklist (page-specific / higher-risk, not in this PR)

- [ ] **#1070** (already tracked in code comments, `globals.css`/`tailwind.config.ts`) — full sweep repointing the legacy dark-theme pages (27 of 32) onto the editorial token palette. This is the single biggest lever but needs visual QA per page and a product decision on whether the "NFL dashboard" surface (`fantasy`, `team/[id]`, `scenarios`, `dashboard/*`) adopts editorial or stays on its own dark theme intentionally.
- [ ] `components/navbar.tsx` / `components/footer.tsx` — repoint off ad hoc `slate-*`/`emerald-*`/`amber-*` onto tokens once #1070's direction is decided. Rendered on every page; highest-visibility fix in the whole audit, but also the highest blast radius — needs owner sign-off before touching.
- [ ] Roll the `display-*`/`heading-*`/`body-*` fontSize scale out beyond the 6 legal pages fixed here — the other 18 `<h1>`s in §2.2, plus the 14 distinct `<h2>` styles observed, are candidates once there's a decision on which token maps to which page "tier" (marketing/hero vs. dashboard vs. long-form content).
- [ ] Consolidate the 71 arbitrary `text-[9px]/[10px]/[11px]` micro-type values (§2.5) into 1-2 named tokens (e.g. `micro`/`micro-sm`) — concentrated in `app/ledger/page.tsx` (40) and `app/entity/[entity_type]/[entity_id]/page.tsx` (25); deferred because consolidating 3 close-but-different pixel values into fewer tokens is a genuine (if subtle) visual change to dense data tables and deserves a screenshot diff, not just a mechanical token swap.
- [ ] `app/search/page.tsx` — alias the remaining 7 near-duplicate values (`bg`, `raised`, `text`, `md`, `lt`, `border`, `blt`, §1.3) onto their closest canonical token once someone can screenshot-diff the page; `md`/`lt` in particular would visibly lighten (ink-2/ink-3 are meaningfully lighter than the current `#444`/`#6B6B6B`).
- [ ] Fix the double-`<h1>` on `app/scenarios/page.tsx` (§2.4) — accessibility fix, separate concern from visual consistency, should be its own PR.
- [ ] Consolidate the duplicate local `SectionHeader`/`TrendBadge`-style helpers (§4.2) into shared components.
- [ ] Extract the duplicated back-button markup (§4.3, `team/[id]` + `fantasy`) into a shared `IconButton`.
- [ ] Broaden page-level `Button` adoption (§4.4) — page-by-page judgment call on which of the 17 ad hoc button-shaped elements found map to which `Button` variant.
- [ ] Standardize card/panel padding (§3.3) once a canonical card-padding scale is agreed.
