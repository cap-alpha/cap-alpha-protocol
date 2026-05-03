# Waitlist Removal Criteria

This document tracks the three gates that must all pass before the waitlist on
`cap-alpha.co` is removed and public access is opened.

Live status is visible at **[cap-alpha.co/quality](https://cap-alpha.co/quality)**.

---

## Gate (i) — Testability Score

**Criterion:** ≥30 consecutive days with mean `testability_score` ≥ 0.65

**Why:** A mean score below 0.65 means the majority of extracted claims are
vague or un-verifiable ("the team might make a move"). At 0.65+ the claims
are specific enough to resolve against ground truth.

**Configurable via env var:** `WAITLIST_TESTABILITY_THRESHOLD` (default `0.65`)

**Current status:** See [/quality](https://cap-alpha.co/quality)

---

## Gate (ii) — Metadata Completeness

**Criterion:** ≥99% metadata completeness for 30 consecutive days

**Why:** Every claim in the ledger must have a `speaker_entity_id` (who said it),
`source_doc_id` (where it was said), and `domain` (which sport). Missing metadata
makes claims un-attributable and legally risky.

**Completeness definition:** A row is complete if all three fields
(`speaker_entity_id`, `source_doc_id`, `domain`) are non-null and non-empty.

**Configurable via env var:** `WAITLIST_METADATA_THRESHOLD` (default `0.99`)

**Current status:** See [/quality](https://cap-alpha.co/quality)

---

## Gate (iii) — Zero 0-Output Production Runs

**Criterion:** No extraction run produced 0 utterances in the last 30 days

**Why:** A 0-output run means the pipeline silently failed — no data was
extracted for that day. Silent failures in the ledger corrupt historical
completeness claims.

**Implementation note:** This gate requires the `silver_v2_claims.extraction_run`
table ([Issue #4](https://github.com/andrewjsmith00/nfl-dead-money/issues/4)).
Until that table exists, this gate shows as failing by default (safe default).

**Configurable via env var:** `WAITLIST_CONSECUTIVE_DAYS` (default `30`)

**Current status:** See [/quality](https://cap-alpha.co/quality)

---

## Authorization

When all three gates show green on the live dashboard, the waitlist can be
removed. The decision is made by @andrewsmith and documented as a comment
on Issue #599.

Removal steps:
1. Confirm all three gates are green for a full 30-day window (not just
   the most recent day).
2. Remove or bypass `WaitlistForm` from `web/app/page.tsx`.
3. Update `LAUNCH_CHECKLIST.md`.
4. Announce via the existing waitlist email list.
