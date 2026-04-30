# Stripe Sole Proprietorship + EIN Verification

## Confirmation

Stripe explicitly supports sole proprietorships with EINs for full payout capability.
No LLC formation is required.

**Source:** https://stripe.com/docs/connect/identity-verification

Key quote from Stripe documentation:
> Stripe supports many business types including sole proprietors. A sole proprietor
> can provide either an SSN or an EIN (Employer Identification Number) to complete
> identity verification and enable payouts.

Additional confirmation:
- https://stripe.com/docs/connect/required-verification-information
- https://support.stripe.com/questions/business-tax-id-number-tin-vs-ein

## Entity Configuration

In the Stripe Dashboard under **Settings → Business details**:

| Field | Value |
|---|---|
| Business type | Individual / Sole proprietor |
| Tax ID type | EIN |
| Tax ID | *(your 9-digit EIN from IRS)* |
| Business name | *(legal business name matching IRS filing)* |
| Bank account | *(routing + account number for payouts)* |

## Verification Checklist

- [ ] Business type set to **Individual / Sole proprietor** in Stripe Dashboard
- [ ] EIN entered under **Business details → Tax details**
- [ ] Business name matches IRS EIN registration exactly
- [ ] Bank account added and verified (micro-deposit or instant verification)
- [ ] Identity document uploaded if Stripe requests additional verification
- [ ] Stripe account status shows **Payouts enabled**

## Test-Mode End-to-End Verification

Run the E2E script to confirm the checkout → webhook → subscription flow works
under your verified Stripe account:

```bash
cd web
STRIPE_SECRET_KEY=sk_test_... \
STRIPE_PRO_PRICE_ID=price_... \
npx tsx --env-file=.env.local scripts/stripe-e2e-verify.ts
```

Expected output:
```
[1/4] Creating test customer...         ok (cus_xxx)
[2/4] Creating checkout session...      ok (cs_test_xxx)
[3/4] Verifying session properties...   ok
[4/4] Constructing webhook event...     ok
All checks passed. Stripe test-mode E2E verified.
```

## Live-Mode Verification

1. Switch `STRIPE_SECRET_KEY` to `sk_live_...` in Vercel
2. Update `STRIPE_WEBHOOK_SECRET` to the live-mode webhook secret
3. Re-run `web/scripts/stripe-setup.ts` with live key to get live price IDs
4. Place a real $0.50 charge via the Pricing page using a real card
5. Confirm in Stripe Dashboard: charge succeeded, payout scheduled

## Vercel Environment Variables

After live-mode verification, update these in Vercel Dashboard → Settings → Environment Variables:

| Variable | Description |
|---|---|
| `STRIPE_SECRET_KEY` | Live key: `sk_live_...` |
| `STRIPE_WEBHOOK_SECRET` | Live webhook secret: `whsec_...` |
| `STRIPE_PRO_PRICE_ID` | Live price ID for Pro tier |
| `STRIPE_API_STARTER_PRICE_ID` | Live price ID for API Starter |
| `STRIPE_API_GROWTH_PRICE_ID` | Live price ID for API Growth |

## Stripe Tax

Once the account is verified and payouts enabled, enable Stripe Tax:
**Stripe Dashboard → Tax → Enable automatic tax collection**

This is set-and-forget until MRR exceeds $10k, at which point review nexus rules.
