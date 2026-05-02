# Pro Tier Value Prop Audit — Gate 1

**Audit date:** 2026-05-01  
**Issue:** #502  
**Scope:** `web/` route handlers and `pipeline/api/` endpoints — what is behind the Pro paywall, where in code, and is the gate correctly enforced?

---

## Pro tier value proposition (plain language)

A **$15/mo Pro subscriber** gets:

| Feature | Free | Pro |
|---|---|---|
| Pundit roster | Top 10–25 only | Full roster (all tracked pundits) |
| Historical data | Current season | Full history across all seasons |
| API access | None | REST API with 100K req/mo + 60 req/min |
| API keys | 0 | Up to 3 keys |
| Data exports | No | Yes |
| Usage dashboard | No | Yes (with metering breakdown) |
| Persona modes | Fan only | Bettor + Agent personas |
| Rate limit | — | 1,000 req/min on web API |

Source: `strategy/MONETIZATION.md` + code inspection.

---

## Gated features — code locations and enforcement status

### 1. API key creation — tier cap

| Item | Detail |
|---|---|
| File | `web/app/api/api-keys/route.ts:48–56`, `web/lib/api-keys/tiers.ts:16–22`, `web/lib/api-keys/repository.ts:88–96` |
| What it does | Limits key count per tier (free: 1, pro: 3, api_starter: 10, api_growth: 20, enterprise: 25) |
| Gate enforced? | **YES** — 403 returned at creation time if over cap; Clerk auth required |

### 2. Stripe checkout / subscription purchase

| Item | Detail |
|---|---|
| File | `web/app/api/billing/checkout/route.ts:11–50` |
| What it does | Creates Stripe Checkout session; maps plan → price ID via env vars |
| Gate enforced? | **YES** — Clerk auth required; unknown price IDs handled defensively |

### 3. Subscription lifecycle sync

| Item | Detail |
|---|---|
| File | `web/app/api/webhooks/stripe/route.ts:1–342` |
| What it does | Handles checkout.session.completed, subscription.updated/deleted, invoice events; syncs `isPro`, `tier`, subscription fields to Postgres + Clerk metadata + BigQuery audit log |
| Gate enforced? | **YES** — Stripe signature verification required; unknown price IDs default to free |

### 4. Web API key authentication + rate limiting

| Item | Detail |
|---|---|
| Files | `web/lib/api-key-auth.ts:52–96`, `web/lib/rate-limit.ts:26–131` |
| What it does | Bearer token extracted → verified against BigQuery → tier resolved from Clerk metadata → sliding-window rate limit checked via Upstash |
| Gate enforced? | **YES** — Full auth + tier + rate-limit per request; 429 returned on excess |

### 5. Per-tier rate limits (web)

| Tier | Req/min | Req/day | Req/mo |
|---|---|---|---|
| free | 100 | 10,000 | 10,000 |
| pro | 1,000 | 100,000 | 100,000 |
| api_starter | 10,000 | 1,000,000 | 1,000,000 |
| api_growth | 100,000 | 10,000,000 | 10,000,000 |

Source: `web/lib/rate-limit.ts:26–32`, `web/app/api/dashboard/usage/route.ts:72–88`

### 6. Usage dashboard

| Item | Detail |
|---|---|
| File | `web/app/api/dashboard/usage/route.ts:91–259` |
| What it does | Returns tier config, rate limits, per-endpoint usage breakdown |
| Gate enforced? | **PARTIAL** — Clerk auth required; tier resolved correctly; but `monetization.api_requests` table may not exist in production → fallback returns zero counts. Renewal date is a TODO (line 219). |

### 7. IP-based rate limiting for public routes

| Item | Detail |
|---|---|
| Files | `web/middleware.ts:15–76`, `web/lib/rate-limit.ts:142–171` |
| What it does | 100 req/min per IP on `/api/ledger/`, `/api/draft/`, `/api/search-index`, `/api/misses`, `/api/predictions`, `/api/personalization` |
| Gate enforced? | **YES** — Returns 429 with Retry-After header |

### 8. Persona switcher (Bettor / Agent)

| Item | Detail |
|---|---|
| File | `web/components/persona-switcher.tsx:16–18, 33, 49–51` |
| What it does | Bettor and Agent personas flagged `isPro: true`; sign-in modal shown for unauthenticated users |
| Gate enforced? | **NO — CLIENT-SIDE ONLY** ⚠️ A signed-in free user can navigate directly to `/dashboard/bettor` or `/dashboard/agent`. No server-side tier check exists on those routes. |

### 9. FastAPI pundit endpoints — authentication

| Item | Detail |
|---|---|
| File | `pipeline/api/pundit_router.py:55`, `pipeline/api/api_key_auth.py:1–187` |
| What it does | All `/v1/*` routes require `Depends(verify_api_key)` → validates X-API-Key against BigQuery, checks status + tier |
| Gate enforced? | **YES** — Auth enforced; tier field propagated to caller |

### 10. FastAPI pundit endpoints — rate limiting

| Item | Detail |
|---|---|
| File | `pipeline/api/pundit_router.py:44–80` |
| What it does | `TIER_RATE_LIMITS` dict defines limits (free: 10 req/min, pro: 60 req/min, etc.) |
| Gate enforced? | **NO** ⚠️ Limits are defined but never actually checked in endpoint handlers. Free users can make unlimited calls to `/v1/*` if they have a key. |

### 11. Trade engine endpoints

| Item | Detail |
|---|---|
| File | `pipeline/api/main.py:67–125` |
| What it does | `/api/trade/evaluate`, `/api/trade/counter`, `/api/analyze/vegas`, `/api/trade/find_partner` |
| Gate enforced? | **NO — COMPLETELY OPEN** ⚠️ Zero authentication. Anyone can call these endpoints without an API key or tier. |

---

## Summary: what's correct vs. bypassable

### Correctly enforced ✅

1. Stripe webhook signature verification
2. API key HMAC-SHA256 hashing with pepper; production mode enforces non-empty pepper
3. Web-layer rate limiting (sliding window, Upstash) per tier
4. Subscription lifecycle sync across Postgres + Clerk + BigQuery
5. Tier-based API key creation caps
6. Unknown Stripe price IDs default to free tier (with warning log)
7. IP-based public-route rate limiting
8. Clerk auth on billing/usage pages (server-side)

### Bypassable or incomplete ⚠️ — must fix before paid-tier marketing

| # | Issue | Severity | Location | Recommended fix |
|---|---|---|---|---|
| A | Persona routes (bettor/agent) have no server-side tier check | **HIGH** | `web/components/persona-switcher.tsx`, dashboard route layout | Add Clerk auth + tier validation in `web/app/dashboard/layout.tsx` or per-route page.tsx |
| B | Trade engine endpoints have zero auth | **HIGH** | `pipeline/api/main.py:67–125` | Add `Depends(verify_api_key)` to each trade route |
| C | FastAPI rate limits defined but never checked | **MEDIUM** | `pipeline/api/pundit_router.py:44–80` | Implement Redis-backed rate-limit check in `verify_api_key` dependency or add middleware |
| D | `monetization.api_requests` table may not exist; usage metering falls back to zero | **MEDIUM** | `web/app/api/dashboard/usage/route.ts:237–256` | Confirm table exists in production; wire up insert pipeline |
| E | Renewal date in usage endpoint is TODO | **LOW** | `web/app/api/dashboard/usage/route.ts:219` | Pull `stripeCurrentPeriodEnd` from Postgres users table |
| F | `docs/API.md` line 11 says auth "not yet active" — outdated | **LOW** | `docs/API.md:11` | Update docs to reflect current auth enforcement |

---

## Escalation status

Items **A** and **B** (HIGH severity) represent gated features that are either bypassable or completely absent in code. A free user can access persona-gated dashboard views without a Pro subscription, and the trade engine is fully open to the internet.

**Recommendation: do NOT activate Stripe live-mode or run paid-tier marketing until items A and B are resolved.** Items C–F should be addressed before the Pro tier is publicly advertised as "production-grade."

Linked issues for remediation:
- Item A → open new issue for server-side persona-route protection
- Item B → open new issue for trade engine auth
- Item C → referenced in #144 (rate limiting)
- Item D → referenced in #148 (usage dashboard)
