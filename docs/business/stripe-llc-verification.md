# Stripe Business Entity (LLC) Verification

**Issue**: #140 — Business entity + Stripe account verification
**Gate**: Monetization prerequisite — blocks #115 and all billing work

## Why LLC instead of sole proprietorship

The sole-proprietorship path (see `stripe-sole-prop-verification.md`) exposes the founder
to personal liability for subscription disputes in a betting-adjacent product. An LLC
provides:
- Liability separation for subscription chargebacks
- Cleaner accounting baseline as MRR grows
- Required by some affiliate networks and enterprise customers

## Formation Checklist

- [ ] Choose state of formation (Delaware or home state)
- [ ] File LLC articles of organization (state online portal or Stripe Atlas / Clerky)
- [ ] Obtain EIN from IRS (free, online, instant): https://www.irs.gov/businesses/small-businesses-self-employed/apply-for-an-employer-identification-number-ein-online
- [ ] Open dedicated business bank account under the LLC (Mercury recommended — no fees, API access)
- [ ] Record routing + account number in 1Password under "Cap Alpha — Business Banking"

## Stripe Account Configuration

In Stripe Dashboard → **Settings → Business details**:

| Field | Value |
|---|---|
| Business type | **LLC** |
| Tax ID type | EIN |
| Tax ID | *(9-digit EIN from IRS)* |
| Business name | *(legal LLC name exactly as filed)* |
| Bank account | *(LLC routing + account number for payouts)* |

## Stripe Identity Verification

Stripe requires identity verification for LLC accounts:

1. **Business details** — legal name, address, EIN, business type
2. **Representative** — name, DOB, home address, SSN last-4 of the authorized representative
3. **Business documents** — upload LLC articles of organization if Stripe requests them
4. **Bank account** — link the LLC bank account (instant verification or micro-deposit)

After submission, Stripe typically completes verification within 1 business day.
When approved, the Dashboard shows **Payouts enabled**.

## Stripe Tax

Once payouts are enabled, enable automatic tax collection:
**Stripe Dashboard → Tax → Enable**

Set-and-forget until MRR exceeds $10k, then review nexus rules.

## Vercel Environment Variables (test mode first)

Set these in Vercel Dashboard → Settings → Environment Variables for the **Preview** environment:

| Variable | Value |
|---|---|
| `STRIPE_SECRET_KEY` | `sk_test_...` (test-mode key) |
| `STRIPE_WEBHOOK_SECRET` | `whsec_...` (test webhook endpoint secret) |
| `STRIPE_PRO_PRICE_ID` | `price_...` (from `stripe-setup.ts` output) |
| `STRIPE_API_STARTER_PRICE_ID` | `price_...` |
| `STRIPE_API_GROWTH_PRICE_ID` | `price_...` |

Run `stripe-setup.ts` first to create products and get price IDs:

```bash
cd web
STRIPE_SECRET_KEY=sk_test_... npx tsx --env-file=.env.local scripts/stripe-setup.ts
```

## Test-Mode End-to-End Verification

Run this after setting env vars and creating products:

```bash
cd web
STRIPE_SECRET_KEY=sk_test_... \
STRIPE_PRO_PRICE_ID=price_... \
npx tsx --env-file=.env.local scripts/stripe-e2e-verify.ts
```

Expected output:

```
[1/5] Listing products...               ok (3 active products)
[2/5] Creating test customer...         ok (cus_xxx)
[3/5] Creating checkout session...      ok (cs_test_xxx)
[4/5] Verifying session properties...   ok
[5/5] Constructing webhook event...     ok (signature verified)

All checks passed. Stripe test-mode E2E verified.
```

This confirms AC1 (`stripe products list` returns from the verified account) and AC2
(test-mode charge end-to-end succeeds) from issue #140.

## Live-Mode Cutover

After test-mode passes and the LLC entity is fully verified in Stripe:

1. Switch `STRIPE_SECRET_KEY` to `sk_live_...` in Vercel **Production** environment
2. Update `STRIPE_WEBHOOK_SECRET` to the live-mode webhook secret
3. Re-run `stripe-setup.ts` with the live key to create live price IDs
4. Place a real $0.50 charge via the Pricing page to confirm payouts flow to the bank account
5. Confirm in Stripe Dashboard: charge succeeded, payout scheduled to LLC bank account
