# Cap Alpha — Closed Beta Plan

**Issue:** #506  
**Milestone:** M-LAUNCH: Bulletproof for First Signup  
**Status:** Draft — owner must fill in names, create feedback form, and configure Clerk

---

## Overview

A structured 2-week closed beta with 15–20 trusted users before public launch. The beta surfaces UX problems, broken flows, and trust gaps that internal testing cannot find. It also generates the first real testimonials and seeds a cohort of advocates.

---

## 1. Invite Criteria

Target **15–20 people** across three categories (~5–7 per category).

### Category A: NFL-Knowledgeable Fans / Fantasy Players
People who follow NFL transactions closely, consume sports media daily, and will notice when a pundit is wrong. They test credibility of predictions and resolution accuracy.

| # | Name | Email | Status |
|---|------|-------|--------|
| 1 | [TBD — owner to fill in] | | |
| 2 | [TBD — owner to fill in] | | |
| 3 | [TBD — owner to fill in] | | |
| 4 | [TBD — owner to fill in] | | |
| 5 | [TBD — owner to fill in] | | |

### Category B: Sports Journalists / Media Insiders
People who cover the NFL professionally or have worked in sports media. They will stress-test source accuracy, know which pundits are credible vs. noise, and can identify reputational risks in the product.

| # | Name | Email | Status |
|---|------|-------|--------|
| 1 | [TBD — owner to fill in] | | |
| 2 | [TBD — owner to fill in] | | |
| 3 | [TBD — owner to fill in] | | |
| 4 | [TBD — owner to fill in] | | |
| 5 | [TBD — owner to fill in] | | |

### Category C: Technical / Product Users
Engineers, product managers, or data-savvy users who will find edge cases, broken flows, and performance issues. They may also evangelize within tech communities.

| # | Name | Email | Status |
|---|------|-------|--------|
| 1 | [TBD — owner to fill in] | | |
| 2 | [TBD — owner to fill in] | | |
| 3 | [TBD — owner to fill in] | | |
| 4 | [TBD — owner to fill in] | | |
| 5 | [TBD — owner to fill in] | | |

---

## 2. Access Mechanism (Clerk)

Cap Alpha uses **Clerk** for authentication at https://cap-alpha.co.

### Recommended approach: Allowlist mode

1. In the [Clerk Dashboard](https://dashboard.clerk.com), navigate to **User & Authentication → Restrictions**.
2. Enable **Allowlist** mode: only email addresses on the allowlist can sign up.
3. Add each beta invitee's email address to the allowlist before sending their invite.

### How to add a beta user

```
Clerk Dashboard → User & Authentication → Allowlist → Add email
```

### How to remove a beta user after launch

1. Remove their email from the Allowlist.
2. Optionally revoke their active sessions: **Users → [name] → Sessions → Revoke all**.

### Invite-only alternative (if Allowlist is insufficient)

Clerk also supports **invite-only** mode with single-use invite links:

```
Clerk Dashboard → User & Authentication → Invitations → Send invitation
```

This is stricter: each person gets a unique link and cannot share it. Use this if controlling invitation throughput matters more than ease of onboarding.

### Switching back to open registration

When the beta ends and public launch is declared:
1. **Clerk Dashboard → Restrictions → disable Allowlist / invite-only**.
2. Confirm sign-up flow works end-to-end at https://cap-alpha.co/sign-up.

---

## 3. Feedback Form

**Owner action required:** Create the form in Google Forms (or TypeForm) using the questions below. Paste the form URL into this doc and into issue #506 once created.

**Form title:** Cap Alpha Beta — Your Feedback

### Section 1: About You
1. Which category best describes you?
   - NFL fan / fantasy player
   - Sports journalist / media professional
   - Engineer / technical user
   - Other (please specify)

### Section 2: What Worked
2. Which features did you actually use? (checkboxes: pundit profile, prediction ledger, search, accuracy scores, other)
3. What was the most useful thing you found?
4. Did the product feel trustworthy? Why or why not?

### Section 3: What Broke
5. Did you encounter any errors or broken screens? Describe what happened and what you were doing.
6. Was there anything confusing about the navigation or layout?
7. Were there pundits missing that you expected to find?

### Section 4: Trust & Credibility
8. Do you trust the prediction accuracy scores shown? (1–5 scale, 1 = not at all, 5 = completely)
9. Did the resolution logic make sense (i.e., was the verdict on a prediction correct)?
10. Would you cite this product in an argument about a pundit being wrong? (yes/no/maybe)

### Section 5: NPS
11. How likely are you to recommend Cap Alpha to an NFL-following friend? (0–10 NPS scale)
12. What would make you more likely to recommend it?

### Section 6: Open-Ended
13. What is the one thing you'd change if you were in charge?
14. Anything else we should know?

---

## 4. Bug Tracking Workflow

### Reporting
Beta testers can report bugs in two ways:
- **Preferred:** Fill out the feedback form (see Section 3 above).
- **For technical testers:** Open a GitHub issue with label `beta-feedback` at https://github.com/andrewsmithvt/nfl-dead-money/issues/new and include: steps to reproduce, expected behavior, actual behavior, screenshot if applicable.

### Triage SLA

| Severity | Definition | SLA |
|----------|-----------|-----|
| **P0 — Critical** | Sign-up broken, login broken, data completely wrong (wrong pundit, reversed verdict), security issue | Fix same day |
| **P1 — High** | Core flow broken (can't view a pundit profile, search returns nothing), major display error | Fix within 3 days |
| **P2 — Medium** | Minor display bug, cosmetic issue, slow load | Fix before public launch |
| **P3 — Low** | Nice-to-have improvement, content gap | Backlog for post-launch |

### Triage steps
1. Owner reviews all `beta-feedback` issues daily during beta window.
2. Assign P0/P1 label and assign to an engineer immediately.
3. Leave a comment on the GitHub issue or reply to the form submitter within 24 hours.
4. Close issue with a note on the fix once resolved.

---

## 5. Timeline

| Day | Activity |
|-----|----------|
| Day 0 | Configure Clerk allowlist; finalize invite list; create feedback form |
| Day 1–3 | Send invites with onboarding note and feedback form link; allow 3 days to activate |
| Day 4–14 | Active beta window — 10 days of usage |
| Day 13 | Send reminder to anyone who hasn't activated |
| Day 14 | Send thank-you note with debrief request; prompt stragglers to submit feedback form |
| Day 15 | Owner reviews all feedback; triage remaining issues; assess sign-off criteria |

Total: ~2 weeks before public launch.

---

## 6. Sign-Off Criteria

The beta is complete and public launch is unblocked when **all three** conditions are met:

- [ ] **Zero P0 bugs open** — no critical issues in the `beta-feedback` label backlog
- [ ] **≥ 10 of 20 invitees have used the product** — verify via Clerk Dashboard → Users → filter by sign-up date during beta window, or via session logs (Dashboard → Users → [name] → Sessions)
- [ ] **At least 3 pundits tracked end-to-end with correct resolution** — verify in the ledger that 3 distinct pundits have predictions that have been extracted, shown on their profile, and resolved with correct verdicts

If the beta runs 2 weeks and sign-off criteria are not met, extend by 1 week and re-assess.

---

## 7. Post-Beta Debrief

After the beta closes:

1. Owner writes a summary of major findings, NPS aggregate, and top 3 changes made.
2. Save summary as `docs/beta-learnings.md` (per issue #506).
3. Link `docs/beta-learnings.md` from this issue and from the launch PR.
4. Declare launch readiness on issue #506.

---

## 8. Beta Participant Gratitude

All beta participants who submit feedback receive:

- **Option A:** A discount code for a free first month of the Pro tier at launch.
- **Option B:** Lifetime Pro tier access (at owner's discretion for highest-value participants).

Owner to decide which cohort gets which reward and provision codes via Stripe/Lemon Squeezy before the thank-you email goes out on Day 14.

---

## Owner Action Checklist

- [ ] Fill in invite list names and emails in Section 1 tables
- [ ] Create Google Form using Section 3 questions; paste URL here: `[FORM URL — TBD]`
- [ ] Configure Clerk to allowlist/invite-only mode (Section 2)
- [ ] Add all beta invitee emails to Clerk allowlist
- [ ] Send invites on Day 1 with form link and brief onboarding note
- [ ] Monitor `beta-feedback` GitHub issues daily
- [ ] Assess sign-off criteria on Day 15
- [ ] Write `docs/beta-learnings.md` after close
