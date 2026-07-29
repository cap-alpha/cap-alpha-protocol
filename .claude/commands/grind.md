---
description: Continuous progress driver — self-perpetuating /go+/land cycle that keeps cap-alpha moving and yields when your attention is engaged.
---

# /grind — continuous progress driver

Keep cap-alpha moving forward on its own: land what's ready, verify it's live, dispatch the
next highest-leverage work, then schedule the next pass — **and get out of the way the moment
Andrew is actively steering.** This composes the existing commands (`/go`, `/land-prs`,
`/audit-prs`, `/roi-audit`); it does not duplicate their internals. Source of truth is **GitHub
Issues/PRs**, never local markdown or `docs/sprints/*`.

**Argument:** optional pacing. `/grind` self-paces (default ~25 min idle). `/grind 15m` fixes the
interval. `/grind 1` also caps MAX_PARALLEL at 1 (a bare number sets parallelism; a duration sets cadence).

---

## Rule 0 — Attention gate (check FIRST, every pass)

This is the whole point of `/grind` vs `/go`: **never compete with a present user.**

- If **a real user message is being handled this turn** (Andrew is in the conversation, directing) →
  do exactly what he asked, then **DEFER the grind pass**. Do not spin up competing background agents,
  do not schedule a tick. His attention is the signal; stay out of the way.
- If the turn is a **scheduled wake-up / the user said "go run it" and left** → run the full autonomous
  pass below.
- If Andrew says he's heads-down, or the thread is a focused back-and-forth on one thing → **pause the
  loop** (`ScheduleWakeup stop:true`), finish the thing in front of you, and let his next message re-arm it.
- Ambiguous? Prefer yielding. A quiet loop that resumes on his word beats one that talks over him.

---

## The pass (run only when Rule 0 says the user is away/quiet)

Do these in order; each preempts the ones below it.

1. **Land what's ready.** Run the `/land-prs` flow: `/audit-prs` thread sweep → fix/resolve →
   `scripts/git-rebase-safe.sh` → `scripts/preflight-merge.sh` → `scripts/gh-lars pr merge <n> --rebase --auto`
   on anything green + approved. Confirm each queued PR actually merged.

2. **Publish gate — a data/site change is not DONE until it is LIVE.** After landing anything that
   changes what `cap-alpha.co` shows: (a) merge/confirm the fresh `leaderboard-snapshot` regen PR,
   (b) confirm `production.yml` Vercel deploy fired + succeeded, (c) verify the live site reflects it
   (WebFetch the route / check the snapshot `generated_at`). Once per session, flag if the committed
   snapshot is stale.

3. **CI / job failures are top priority.** A red non-advisory check on an owned PR, or any failed
   scheduled run (pipeline, cron, monitor, deploy), **preempts new work.** Diagnose from the actual
   logs (`gh run view --log-failed`). Verify async jobs with **one observed successful run** before
   calling them done — never "it's deployed" = done.

4. **ROI gate.** Quick `/roi-audit`-style self-check: am I bleeding tokens on something low-leverage,
   or spinning wheels (2–3 failed attempts at the same fix)? If so, **stop that thread, document on the
   issue/PR, and move on** — don't grind a dead end.

5. **Dispatch the next work.** If there's headroom, run the `/go` orchestrator: scan open, unclaimed,
   unblocked, non-`[Planning]` issues → pick highest-leverage → spawn up to **MAX_PARALLEL** subagents
   (worktree isolation, right model tier, one-concern PRs). If the backlog is empty, pull the next slice
   of the active plan (e.g. #1129 resolver / #1133 funnel) instead of idling.

6. **Surface decisions without blocking.** Anything that's genuinely Andrew's call (product, scope,
   external service / API keys / **quota / billing**, altering existing BQ schema) → surface it clearly
   as an A/B/C, **but keep other work moving** — one MC question at a time with agents already running.
   Never sit idle waiting on an answer.

7. **Report + reschedule.** Emit a concise per-stream status (building / PR-open / merged / blocked).
   Then, unless a stop condition holds, schedule the next pass via `ScheduleWakeup` (self-paced ~25 min
   idle, or matched to a specific run you're waiting on). **Do not poll harness-tracked background work**
   — completion notifications re-invoke you automatically; a wakeup is only a fallback heartbeat.

---

## Stop conditions (end the loop — do not idle-tick)

`ScheduleWakeup stop:true` and report a summary when **any** hold:
- Nothing actionable **and** no async work in flight **and** every open decision is already with Andrew.
- Rule 0 says the user is present/steering.
- A hard blocker: missing credentials, or an irreversible high-risk action that needs explicit sign-off.
- ROI red on the critical path, or a quota/billing wall (e.g. Gemini 429) that only Andrew can clear —
  surface the decision and stop rather than burning ticks.

Idle-ticking an already-finished batch wastes tokens (each pass is a full parent invocation). When the
work is done, **stop and let his next message restart you** — that is not "sitting idle," it's yielding.

---

## Guardrails (inherit CLAUDE.md + `/go`'s hard rules)

- Worktrees always; **never edit the main checkout.** Rebase-only — never `--squash`/`--merge`,
  never `--force-push` a shared branch, never `--no-verify` / `gh pr merge --admin`, never push to `main`.
- **Adversarial review before land** (Copilot or an agent `## Adversarial review (agent)` comment).
- **PRs need human approval.** Queue with `--auto` and surface for approval. Only self-approve as owner
  (`ucalegon206`, bare `gh`) when Andrew has durably authorized it **this session** — otherwise leave it queued.
- All issue/PR ops via `scripts/gh-lars` (App identity). **Repo settings are OFF LIMITS.**
- Model tiers: Opus = planning/architecture (**cap 1 total incl. parent**), Sonnet = implementation,
  Haiku = triage — anchor Haiku prompts with "answer only from tool output."
- One concern per PR. Pre-assign migration numbers before parallel dispatch. Claim shared files/namespaces.

---

## End-of-pass improvement note (mandatory)

End every pass with exactly one of:

> **Friction:** `<what slowed you down>`
> **Proposed change:** `<exact edit, file:line if possible>`
> **Why:** `<one sentence>`

…or the literal line `No improvements needed.`
