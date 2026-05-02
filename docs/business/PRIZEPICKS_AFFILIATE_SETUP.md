# PrizePicks Affiliate Program Setup

**Gate**: 1 — First $1 P1 (closes #496)
**Dependencies**: EIN (#479), Business banking (#481), RG messaging (#490), FTC disclosure (#485)
**File simultaneously with**: DraftKings (#492), FanDuel (#494)

## Status: Pending human action

This task requires manual submission by the account owner. No code changes are required
for the application itself — this document tracks the checklist only.

## Why PrizePicks first among DFS

PrizePicks is a daily fantasy sports (DFS) platform — not a sportsbook — which means:
- Legal in more US states than regulated sports betting
- 18+ age requirement in most states (not 21+ like sportsbooks)
- Typically faster affiliate approval than regulated sportsbooks
- Strong audience fit: analytics-minded fans who track prediction accuracy are a natural DFS audience

## Application checklist

- [ ] Application submitted to PrizePicks affiliate program via Impact.com or direct portal
- [ ] EIN provided (dependency: #479)
- [ ] Business bank account info provided (dependency: #481)
- [ ] cap-alpha.co URL and audience description submitted
- [ ] Approval email received
- [ ] Unique tracking link obtained
- [ ] Tracking link stored in 1Password under "Affiliate Links — PrizePicks"
- [ ] Test click confirms attribution

## Application steps

1. Navigate to the PrizePicks affiliate portal:
   - Direct: `https://affiliate.prizepicks.com`
   - Or via Impact.com (search "PrizePicks" in the Impact publisher marketplace)

2. Create a publisher account if you don't already have one on Impact.com
   - Use `king.hrothgar@gmail.com` or a dedicated `affiliates@cap-alpha.co` address

3. Submit the application with:
   - **Website URL**: `https://cap-alpha.co`
   - **Audience description**: "Sports analytics fans who track pundit accuracy; 18+ DFS audience"
   - **Traffic sources**: Organic search, social media, newsletter
   - **EIN**: from 1Password / issue #479
   - **Bank account**: routing + account number from 1Password / issue #481

4. Await approval (typically 2–5 business days for DFS vs. 7–14 for sportsbooks)

5. Upon approval, copy the unique tracking link from the Impact dashboard

6. Store tracking link in 1Password under "Affiliate Links — PrizePicks"

7. Place a test click and verify attribution registers in the Impact dashboard within 24h

## Audience description (copy/paste)

> Sports analytics fans who track NFL and NBA pundit prediction accuracy using the
> Pundit Prediction Ledger at cap-alpha.co. 18+ audience interested in daily fantasy sports.
> Users are highly engaged with prediction data and accountability content.

## After approval

- Tracking link goes into the affiliate link strategy implementation (#500)
- Ensure FTC disclosure (#485) is live on cap-alpha.co before any public placement
- Ensure RG (responsible gaming) messaging (#490) is visible on any page with affiliate links
- Update this checklist and close issue #496

## Notes

- PrizePicks is DFS, not sports betting; age copy should say "18+" not "21+" for most states
- If applying via Impact.com, DraftKings and FanDuel may also be available in the same dashboard
  (see #492 and #494 — apply to all three simultaneously)
- Rakuten Advertising is an alternative network if Impact.com approval is slow (see #492 notes)
