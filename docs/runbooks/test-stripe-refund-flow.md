# Runbook: Test Stripe Subscription + Refund Flow (Test Mode)

> Issue: #486
> Last updated: 2026-05-04

This runbook walks through a real $1 test-mode Stripe charge, verifies access
is granted, tests both the cancel and refund paths, and confirms access is
revoked by the webhook handler.

---

## Prerequisites

- [ ] Stripe CLI installed: `brew install stripe/stripe-cli/stripe`
- [ ] Authenticated: `stripe login` (use the test-mode API key)
- [ ] App running locally with `STRIPE_SECRET_KEY` set to a **test-mode** key
      (starts with `sk_test_...`)
- [ ] `STRIPE_WEBHOOK_SECRET` set to the output of `stripe listen --print-secret`
- [ ] Stripe CLI listening: `stripe listen --forward-to localhost:3000/api/webhooks/stripe`
- [ ] A Clerk test user created and signed in at `http://localhost:3000`
- [ ] Postgres running locally with schema migrated (`make db-migrate`)

---

## Step 1: Verify test mode is active

```bash
stripe customers list --limit 1
# Response should show "livemode": false
```

In the [Stripe Dashboard](https://dashboard.stripe.com/test/dashboard), confirm
"Test mode" toggle is active (orange banner at top).

---

## Step 2: Start the webhook listener

```bash
stripe listen --forward-to localhost:3000/api/webhooks/stripe
# Copy the "Ready! Your webhook signing secret is whsec_..." line.
# Set STRIPE_WEBHOOK_SECRET=whsec_... in .env.local and restart the app.
```

---

## Step 3: Create a test checkout (subscribe a user)

Option A — through the UI:

1. Sign in as a test user at `http://localhost:3000`
2. Navigate to `/pricing` and click **Subscribe**
3. In the Stripe Checkout page use card `4242 4242 4242 4242`, any future
   expiry, any CVC, any ZIP
4. Complete checkout

Option B — trigger via CLI (skips UI, directly fires the webhook):

```bash
# Get the price ID from .env.local (STRIPE_PRO_PRICE_ID)
PRICE_ID=price_xxxx
CUSTOMER_ID=$(stripe customers create --email test@example.com | jq -r '.id')

stripe subscriptions create \
  --customer "$CUSTOMER_ID" \
  --items[0][price]="$PRICE_ID"
```

Then trigger the webhook event manually:

```bash
stripe trigger checkout.session.completed
```

### What to verify after Step 3

- [ ] Webhook handler logs `[Stripe Webhook] checkout completed: <clerkId> → pro`
- [ ] Postgres `users` row: `is_pro = true`, `stripe_subscription_status = active`,
      `stripe_subscription_id` and `stripe_customer_id` are populated
- [ ] Clerk `publicMetadata.tier = "pro"` (check in Clerk Dashboard → Users →
      select user → Metadata tab)
- [ ] User can access pro-gated content at `/dashboard`

```sql
-- Check Postgres state
SELECT clerk_id, is_pro, stripe_subscription_status,
       stripe_subscription_id, stripe_customer_id
FROM users
WHERE email = 'test@example.com';
```

---

## Step 4: Test immediate cancellation via the cancel endpoint

```bash
# Obtain a Clerk session token from the browser (DevTools → Application →
# Cookies → __session, or from /api/auth/session)
SESSION_TOKEN=<your_clerk_session_token>

curl -X POST http://localhost:3000/api/billing/cancel \
  -H "Cookie: __session=$SESSION_TOKEN" \
  -H "Content-Type: application/json"
# Expected: {"canceled":true}
```

### What to verify after Step 4

- [ ] Response is `{"canceled":true}` with HTTP 200
- [ ] Stripe CLI listener logs a `customer.subscription.deleted` event
- [ ] Webhook handler logs `[Stripe Webhook] subscription canceled: <clerkId> → free`
- [ ] Postgres: `is_pro = false`, `stripe_subscription_status = canceled`,
      `stripe_price_id = null`, `stripe_current_period_end = null`
- [ ] Clerk `publicMetadata.tier = "free"`
- [ ] User is redirected/shown free-tier content when they refresh `/dashboard`

---

## Step 5: Test refund via Stripe Dashboard or CLI

A refund does NOT trigger re-cancellation (the subscription is already
canceled). This step verifies the refund does not cause unexpected side effects.

```bash
# Get the latest payment intent for the customer
PAYMENT_INTENT_ID=$(stripe payment_intents list --customer "$CUSTOMER_ID" \
  --limit 1 | jq -r '.data[0].id')

stripe refunds create --payment-intent "$PAYMENT_INTENT_ID"
# Expected output: refund object with status: "succeeded"
```

Or in the Dashboard: **Payments → find the charge → Refund**.

### What to verify after Step 5

- [ ] Stripe fires `charge.refunded` event (visible in CLI listener output)
- [ ] Our webhook handler does **not** crash (we don't handle `charge.refunded`,
      which is correct — it falls through the `default:` case with no error)
- [ ] Postgres state is **unchanged** (still `is_pro=false`, `canceled`) because
      refunds are money events, not subscription lifecycle events
- [ ] User access is still revoked (already was from Step 4)

---

## Step 6: Test the Stripe Customer Portal (cancel at period end)

The portal supports canceling at period end (user keeps access until billing
date rather than immediate revocation). This tests the
`customer.subscription.updated` webhook path.

```bash
curl -X POST http://localhost:3000/api/billing/portal \
  -H "Cookie: __session=$SESSION_TOKEN" \
  -H "Content-Type: application/json"
# Expected: {"url":"https://billing.stripe.com/..."}
# Open the URL, click Cancel, choose "Cancel at period end"
```

### What to verify after Step 6

- [ ] Stripe fires `customer.subscription.updated` with `cancel_at_period_end=true`
- [ ] Webhook handler updates `stripe_subscription_status = active` (still
      active, just scheduled to cancel — Stripe does not change status yet)
- [ ] User still has pro access until `stripe_current_period_end`
- [ ] At period end Stripe fires `customer.subscription.deleted`, which our
      handler converts to `is_pro=false`

---

## Acceptance criteria checklist

- [ ] Checkout creates subscription and grants pro access (Steps 2–3)
- [ ] `POST /api/billing/cancel` revokes access immediately (Step 4)
- [ ] `customer.subscription.deleted` webhook sets `is_pro=false` and `tier=free`
- [ ] Refund event does not crash the webhook handler or change DB state (Step 5)
- [ ] Stripe Customer Portal "cancel at period end" flows through
      `customer.subscription.updated` (Step 6)
- [ ] All webhook events logged to BigQuery `monetization.stripe_events` (best-effort)

---

## Expected database states summary

| State | `is_pro` | `stripe_subscription_status` | `stripe_price_id` | `stripe_current_period_end` |
|---|---|---|---|---|
| Never subscribed | false | null | null | null |
| Active subscription | true | active | price_xxx | future date |
| Past due (retrying) | true | past_due | price_xxx | future date |
| Canceled immediately | false | canceled | null | null |
| Cancel at period end | true | active | price_xxx | future date |
| Expired after cancel | false | canceled | null | null |

---

## Troubleshooting

**Webhook not firing locally**: Check `stripe listen` is running and
`STRIPE_WEBHOOK_SECRET` matches the `whsec_...` printed by the CLI.

**`stripe_subscription_id` null after checkout**: Confirm `client_reference_id`
is being set in the checkout session — it must equal the Clerk user ID. See
`handleCheckoutCompleted` in `/api/webhooks/stripe/route.ts`.

**Cancel returns 404**: The user has no `stripeSubscriptionId` in Postgres.
Either the checkout webhook was not received, or it was received before the
user row existed (race condition — retry after 1s or re-trigger the event with
`stripe events resend <evt_id>`).
