---
description: Safely claim and complete one issue using a shared orientation cache
---

# Multi-Agent Work Protocol (Minimal)

You are one of multiple agents working in parallel.

Your goal:
- Complete exactly one unblocked issue
- Avoid duplicate work
- Follow repository conventions via a shared cache

If you cannot reliably perform any required step, EXIT safely.

## Autonomy

Run autonomously. Do NOT prompt the user for permission on:
- Read-only / exploratory commands (git log, git status, cat, ls, grep, gh issue/pr queries)
- Running tests (pytest)
- Creating branches, committing, pushing feature branches
- Opening/commenting on issues and PRs
- Any command whose purpose is understanding the current state of the codebase or infrastructure

Only pause for user input on items listed in CLAUDE.md "When to ask the user" (reward changes, schema changes, universe changes, billing, scope ambiguity).

---

# Core Flow

1. LOAD_ORIENTATION
2. PROCESS_FEEDBACK
3. SELECT_ISSUE
4. CLAIM
5. VERIFY
6. WORK
7. COMPLETE

---

# STATE 1: LOAD_ORIENTATION

IF `.claude/agent-orientation.md` exists:
  READ it and follow it strictly

ELSE:
  You are the bootstrap agent:
    - Discover repo conventions
    - Define how to perform required operations (issues, comments, PRs, etc.)
    - Write `.claude/agent-orientation.md`
    - Open a PR: "bootstrap agent orientation cache"
  EXIT

---

# STATE 2: PROCESS_FEEDBACK

Check for:
- Issues labeled `agent-feedback`
- Comments mentioning "agent"
- Recently failed/closed PRs

IF feedback affects conventions:
  Update orientation cache (use lock)
  IF substantial change:
    EXIT

---

# STATE 3: SELECT_ISSUE

List open issues

Exclude:
- do-not-touch labels
- agent-feedback
- blocked / dependency issues
- issues with active claim (<2h)
- issues already covered by an open PR (check with `gh pr list --search "Closes #<N>" --state open`)

Prefer:
- clear scope
- small surface area
- ready-to-work labels

IF none:
  EXIT

---

# STATE 4: CLAIM

Check issue comments for active claim:
- contains "🤖" or "claim" or "working"
- within last 2 hours
- not released

IF exists:
  return to SELECT_ISSUE

POST comment (with identity footer per agent-orientation.md):
  "🤖 intending to work on this at <UTC timestamp>

  — 🤖 `go`"

WAIT ~2 minutes

---

# STATE 5: VERIFY

Re-read comments

Extract all claims
Sort by timestamp in comment body

IF your claim is earliest:
  proceed

ELSE:
  POST "🤖 yielding to earlier claim"
  return to SELECT_ISSUE

---

# CHECKPOINT (MANDATORY)

Before work:

[ ] Claim posted
[ ] Wait completed
[ ] No earlier claim
[ ] You are earliest

IF any false:
  STOP

---

# STATE 6: WORK

- Create branch per repo convention (or fallback: agent/issue-<id>)
- Implement solution
- Follow all conventions from cache
- Run all required checks

DO NOT:
- modify restricted paths
- disable checks
- perform destructive git actions

---

# STATE 7: COMPLETE

Choose ONE:

## DONE
- Open PR (use repo conventions)
- Include closing keyword (e.g., Closes #id)
- Comment with PR link

## BLOCKED
- Comment:
  - what failed
  - what you tried
  - what is needed
- Mark blocked if label exists
- POST "🤖 releasing issue"

## INVALID
- Explain and close issue
- POST "🤖 releasing issue"

---

# CACHE LOCK (for updates only)

Before editing `.claude/agent-orientation.md`:

- Check for open "agent-orientation cache lock"
- If recent (<30 min): do not proceed
- If stale: take over
- If none: create lock

After update:
- Close lock with PR reference

---

# HARD RULES

- One issue per run
- Never override documented conventions
- Never ignore active claims
- Never force-push shared branches
- Never modify default branch directly
- When unsure: EXIT or file `agent-feedback`

---

# SUCCESS =

- One issue claimed without conflict
- Valid PR OR clear blocked report
- Clean repository state
