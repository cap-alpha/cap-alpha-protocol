# Business Banking Setup

**Gate**: 0 — $1 P0 prerequisite (closes #481)
**Dependency**: EIN via sole proprietorship (#479)
**Blocks**: Stripe payout account setup (#140)

## Status: Pending human action

This task requires manual setup by the account owner. No code changes are required. This document tracks the checklist.

## Checklist

- [ ] Business checking account open at Mercury, Bluevine, or Chase Business ($0 minimum)
- [ ] Account opened under sole proprietorship name + EIN (not personal SSN)
- [ ] Debit card received and activated
- [ ] Online banking / API access confirmed working
- [ ] Routing + account number recorded in 1Password under "Cap Alpha — Business Banking"

## Recommended: Mercury

Mercury (mercury.com) is the preferred option for this project:
- No monthly fees, no minimums
- Instant ACH transfers
- API access for programmatic balance checks
- Fintech-friendly (common in early-stage SaaS)

## Why this matters

Stripe requires a verified bank account before enabling payouts. Without a dedicated business account:
- Personal and business funds mix (creates accounting and liability risk)
- Stripe payout setup (#140) is blocked
- Affiliate payment receipt is blocked

## After setup

Once the account is open and details are in 1Password, update this checklist and close issue #481.
