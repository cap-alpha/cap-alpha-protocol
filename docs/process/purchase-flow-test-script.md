# Pre-Launch Purchase Flow Test Script

**Issue:** #150  
**Goal:** A real person who is not the founder completes the full "stranger → paying customer" flow unassisted in under 5 minutes.

---

## Before you start

- Use a device and browser you have not used to visit cap-alpha.co before (incognito mode, or a phone that hasn't visited).
- Use a **real Stripe credit card** (e.g. Visa/MC). Stripe test cards will not work in live mode.
- Have a stopwatch ready.
- Capture screenshots at each numbered step and attach them to issue #150.

---

## The script

### Step 1 — Cold landing (start the stopwatch now)

1. Go to `https://cap-alpha.co` with no prior context.
2. Read the page for 30 seconds without help from the founder.
3. Answer: _What does this product do?_ (write it down — check for friction)
4. Find the link or button to view pricing **without being told where it is**.
   - **Pass:** You find it within 60 seconds.
   - **Friction log:** Note anything confusing about the navigation.

---

### Step 2 — Pricing page

5. Navigate to the pricing page.
6. Identify which plan is right for you as a developer who wants API access.
   - **Pass:** You can identify the correct plan unaided within 60 seconds.
7. Note: does the annual/monthly toggle work? Are the prices clear?

---

### Step 3 — Sign up

8. Click the upgrade button for your chosen plan.
   - If redirected to sign-in/sign-up: create a new account with a fresh email address.
   - Use Clerk's standard sign-up flow (email + password or OAuth).
9. **Pass:** Account created and you are redirected back toward checkout.
10. **Friction log:** Note any confusing steps in the Clerk sign-up flow.

---

### Step 4 — Stripe Checkout (live mode, real card)

11. Complete the Stripe Checkout with your real card.
    - Use a physical card or Apple/Google Pay.
12. **Pass:** You see the success confirmation screen at `/dashboard?checkout=success`.
13. Note the time elapsed since step 1 — target is under 2 minutes to reach this screen.

---

### Step 4b — Confirmation email

14. Check your inbox for a receipt/confirmation email from Stripe.
    - Also check spam.
15. **Pass:** Receipt arrives within 60 seconds and is not in spam.
16. **Friction log:** If it lands in spam, file a follow-up issue for SPF/DKIM tuning.

---

### Step 5 — Find the API keys dashboard

17. Without being told the URL, navigate to the API keys dashboard.
    - Hint: it is somewhere in the dashboard/account section.
18. **Pass:** You find `/dashboard/api-keys` within 90 seconds.
19. **Friction log:** Note any missing navigation links.

---

### Step 6 — Create a key and make an API call

20. Create a new API key. Copy the key to your clipboard.
21. Open a terminal and run:
    ```
    curl -s -H "Authorization: Bearer <YOUR_KEY>" \
      https://cap-alpha.co/api/v1/leaderboard | head -c 200
    ```
22. **Pass:** You receive a JSON response (not an auth error).
23. Note time elapsed from step 1 — target is under 5 minutes total.

---

### Step 7 — Usage reflected in dashboard

24. Navigate to the usage dashboard (look in the account/dashboard area).
25. **Pass:** Your just-made API call appears in usage stats within 60 seconds.
26. **Friction log:** If usage is empty, file a follow-up issue.

---

### Step 8 — Cancel subscription

27. Navigate to Billing (look in the dashboard or account area).
28. Click "Manage billing" or "Customer portal".
29. Cancel your subscription immediately (not "cancel at period end").
30. **Pass:** You are returned to the app with a success message.

---

### Step 9 — Verify downgrade within 10 seconds

31. Immediately (within 10 seconds of canceling), run the curl command again:
    ```
    curl -s -o /dev/null -w "%{http_code}" \
      -H "Authorization: Bearer <YOUR_KEY>" \
      https://cap-alpha.co/api/v1/leaderboard
    ```
32. **Pass:** The response is either:
    - `402` (payment required for paid tier endpoints), or
    - `200` with free-tier rate limits applied (check `X-RateLimit-Limit` header — free tier cap is 100 req/min).
33. **Fail if:** The response is still `200` with paid-tier limits after more than 10 seconds.

---

## Stop the stopwatch

Record total elapsed time from step 1 (cold landing) to step 6 (successful API call).

---

## Friction log template

For each friction point, note:

| Step | What happened | Severity (P0/P1/P2) | Fix or Accept |
|------|--------------|----------------------|---------------|
| e.g. 4 | Confirmation email landed in spam | P1 | Fix: add DKIM record |
| ...  | ...          | ...                  | ...           |

Attach this table as a comment on issue #150 with screenshots.

---

## Acceptance criteria checklist

- [ ] Non-founder completes flow end-to-end without verbal help
- [ ] Total time from cold landing to working API call is under 5 minutes
- [ ] Cancellation downgrades tier within 10 seconds
- [ ] Document with friction log and screenshots attached to issue #150
- [ ] Every P0/P1 friction point is either fixed or explicitly accepted before launch

---

## Known constraints (as of 2026-05-05)

- **Cancellation is immediate** — the system downgrades to free the moment you cancel via the Customer Portal, not at period end. This is intentional to satisfy the 10-second criterion.
- **Usage dashboard latency** — usage metrics may have up to 60 seconds of lag due to BigQuery streaming buffer delays.
- **Rate limit enforcement** — after downgrade, the free rate limit (100 req/min) applies. Pro-tier endpoints that check the tier explicitly will return 402.
