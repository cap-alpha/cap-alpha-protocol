# Login Rate Limiting & Account Enumeration Protections

> Issue: #497
> Last updated: 2026-05-04

## Summary

Cap Alpha uses **Clerk** as its identity provider. Clerk handles all sign-in,
sign-up, password reset, and OAuth flows — there are **no custom auth routes**
in this codebase that accept passwords or create sessions. All brute-force and
account enumeration protections on the login critical path are therefore
delegated to Clerk's built-in Attack Protection.

Custom API routes (public data, email actions, billing) have their own
IP-based rate limits via Upstash Redis, documented below.

---

## 1. Clerk Attack Protection (login path)

Clerk's Attack Protection guards sign-in and sign-up against:

- **Credential stuffing** — bot-driven login attempts using leaked credential
  lists.
- **Brute force** — repeated wrong-password attempts on a single account.
- **Account enumeration** — probing which email addresses are registered.

### Default lockout behavior

| Condition | Clerk default |
|---|---|
| Failed password attempts per user | 100 per hour before lockout |
| Sign-up spam / bot detection | Intelligent bot scoring (CAPTCHA fallback) |
| Account enumeration | Clerk normalizes responses — same UX for valid and invalid email |

### How to verify Attack Protection is active

1. Go to [Clerk Dashboard](https://dashboard.clerk.com/) → select your
   application.
2. Navigate to **Configure → Attack Protection**.
3. Verify "Bot Protection" and "Brute Force Protection" are enabled.
4. Check that the application's "Email address" identifier setting is set to
   **"Email address" (not username)** so enumeration normalization applies.

### Clerk sign-in / sign-up routes

Clerk uses its own hosted pages or `<SignIn>` / `<SignUp>` components which
proxy through `accounts.clerk.com` — they are **not** Next.js API routes and
are therefore not governed by `middleware.ts`. Rate limiting on these paths is
100% Clerk's responsibility.

---

## 2. Custom API rate limits

Rate limiting is implemented in `web/lib/rate-limit.ts` using Upstash Redis
sliding-window counters. Applied in two places:

### 2a. `web/middleware.ts` — public data routes

All routes under these prefixes are rate-limited at **100 req/min per source IP**:

```
/api/ledger/
/api/draft/
/api/search-index
/api/misses
/api/predictions
/api/personalization
```

This prevents aggressive scraping of public prediction/ledger data.

### 2b. `/api/emails/unsubscribe` — email action route

Rate limit: **100 req/min per source IP** (shared with the anonymous IP limiter
from `checkIpRateLimit`).

**Why this route needs its own rate limit:** The unsubscribe endpoint validates
an HMAC token passed in the URL. An attacker without a valid token always gets
`403`. An attacker who crafts a valid token for a real email address gets `200`.
Without rate limiting, an attacker who already knows an email address could
brute-force token variants or rapidly submit many unsubscribe requests against
different email addresses. The IP rate limit caps this at 100 attempts/min.

**Why the route does not enumerate accounts:** The DB update is a no-op for
unknown emails (`WHERE email = ?` with no matching row). The route always
returns `200` after a successful token check regardless of whether the email
exists in the database — an attacker cannot use the `200`/`403` distinction to
enumerate valid emails because `403` fires before the DB is consulted (token
check happens first, and the same `403` fires for any token mismatch whether
or not the email exists).

---

## 3. No custom auth routes bypassing Clerk

Audit of all routes in `web/app/api/`:

| Route | Auth mechanism | Notes |
|---|---|---|
| `/api/billing/checkout` | `auth()` from Clerk | Requires valid Clerk session |
| `/api/billing/portal` | `auth()` from Clerk | Requires valid Clerk session |
| `/api/billing/cancel` | `auth()` from Clerk | Requires valid Clerk session |
| `/api/emails/unsubscribe` | HMAC token | Public route; IP rate-limited |
| `/api/webhooks/stripe` | Stripe signature | Server-to-server only |
| `/api/webhooks/clerk` | Svix signature | Server-to-server only |
| `/api/ledger/*` | Public | IP rate-limited via middleware |
| `/api/draft/*` | Public | IP rate-limited via middleware |
| `/api/search-index` | Public | IP rate-limited via middleware |
| `/api/misses` | Public | IP rate-limited via middleware |
| `/api/predictions` | Public | IP rate-limited via middleware |
| `/api/personalization` | Public | IP rate-limited via middleware |
| `/api/api-keys/*` | `auth()` from Clerk | Requires valid Clerk session |
| `/api/dashboard/*` | `auth()` from Clerk | Requires valid Clerk session |

No route accepts passwords or issues sessions — all session management is
handled by Clerk.

---

## 4. Infrastructure notes

- **Upstash Redis** provides the rate limit counters. If `UPSTASH_REDIS_REST_URL`
  or `UPSTASH_REDIS_REST_TOKEN` are absent, all rate limits fail-open (requests
  are allowed). This is intentional for local dev and pre-provisioned
  environments.
- Rate limit response headers (`X-RateLimit-Limit`, `X-RateLimit-Remaining`,
  `X-RateLimit-Reset`, `Retry-After`) are forwarded on both allowed and blocked
  responses so clients can self-throttle.
- The IP extraction logic reads `x-real-ip` (Vercel) then falls back to
  `x-forwarded-for` first element.
