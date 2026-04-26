---
description: Safely claim and complete issues using a shared orientation cache — spawns parallel subagents
---

# /go — Parallel Agent Orchestrator

You are invoked either as an **ORCHESTRATOR** (default, no issue pre-assigned) or as a
**WORKER** (orchestrator passed you `ISSUE=<n>`).

Detect your mode from the invocation context:
- `ISSUE=<n>` present in this prompt → **WORKER MODE** — skip to STATE 4
- No issue assigned → **ORCHESTRATOR MODE** — run states 1–3, then spawn workers

If you cannot reliably perform any required step, EXIT safely.

## Autonomy

Run autonomously. Do NOT prompt the user for permission on:
- Read-only / exploratory commands (git log, git status, cat, ls, grep, gh issue/pr queries)
- Running tests (pytest)
- Creating branches, committing, pushing feature branches
- Opening/commenting on issues and PRs
- Any command whose purpose is understanding the current state of the codebase or infrastructure

Only pause for user input on items listed in CLAUDE.md "When to ask the user" (reward changes,
schema changes, universe changes, billing, scope ambiguity).

---

# ORCHESTRATOR MODE (states 1–3 + spawn)

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

# STATE 3: SELECT_ISSUES + SPAWN WORKERS

## 3a. Build shortlist

List open issues. For each, check:
- No `do-not-touch`, `agent-feedback`, `icebox` labels
- Not an umbrella/meta issue
- No active claim comment within last 2 hours (contains "🤖" / "claim" / "intending", not "releasing")

Rank by priority:
1. `critical-path` bugs
2. `backend` / `data` / `infrastructure` features with clear scope
3. Everything else

Pick up to **3** candidates (more = diminishing returns, GitHub rate limits).

## 3b. Spawn workers in parallel

For each selected issue N, call the **Agent** tool with:
- `isolation: "worktree"`
- Prompt: the full text of this file, prepended with `ISSUE=<N>`

Call all Agent tools simultaneously (parallel, not sequential).

## 3c. Collect and report

Wait for all subagents to finish. Print a summary table:

```
| Issue | Title (short) | Outcome | PR |
|-------|--------------|---------|-----|
| #N    | ...          | DONE / YIELDED / BLOCKED | #M |
```

## 3d. WORKFLOW REVIEW (mandatory)

After the summary, review this run for friction, inefficiency, or gaps in the protocol.
Output ONE of:

- A bulleted list of concrete improvement suggestions (file to edit, what to change, why)
- "No improvements needed this run."

Do not skip this step.

---

# WORKER MODE (states 4–7, triggered with ISSUE=<N>)

The orchestrator has pre-assigned you issue **N**. Your only job is to claim it, implement
the fix, and open a PR. Do not scan for other issues.

---

# STATE 4: CLAIM

Check issue N's comments for an active claim:
- contains "🤖" or "claim" or "working" or "intending"
- within last 2 hours
- not followed by "releasing"

IF active claim exists:
  EXIT with "yielding — active claim already on #N"

POST comment on issue N:
```
🤖 intending to work on this at <UTC timestamp>

— 🤖 `go`
```

WAIT ~2 minutes (use sleep or background task; do not skip).

---

# STATE 5: VERIFY

Re-read issue N's comments.

Extract all claim timestamps from comment bodies (ISO-8601 UTC strings).
Sort ascending.

IF your timestamp is earliest:
  proceed

ELSE:
  POST "🤖 yielding to earlier claim"
  EXIT

---

# CHECKPOINT (MANDATORY)

Before any code changes:

[ ] Claim posted on issue N
[ ] 2-minute wait completed
[ ] Re-read comments
[ ] Your timestamp is earliest

IF any false: STOP

---

# STATE 6: WORK

- Create worktree branch: `worktree-<type>-<N>-<slug>`
- Implement solution
- Follow all conventions from orientation cache and CLAUDE.md
- Run `make check` (lint + unit tests) before committing

DO NOT:
- modify restricted/shared files without claiming them first
- disable linting or test checks
- perform destructive git actions (force-push, reset --hard)

---

# STATE 7: COMPLETE

Choose ONE:

## DONE
- Push branch, open PR with `Closes #N` in body
- Use `gh pr merge <number> --rebase --auto` to queue
- Comment on issue N:
  ```
  🤖 PR #<M> opened and queued for merge: <url>

  Changes:
  - <bullet summary>

  — 🤖 `go`
  ```

## BLOCKED
- Comment on issue N explaining:
  - what failed
  - what you tried
  - what is needed to unblock
- POST "🤖 releasing issue — blocked"
- EXIT

## INVALID
- Explain why and close the issue
- POST "🤖 releasing issue — invalid"
- EXIT

---

# CACHE LOCK (orientation updates only)

Before editing `.claude/agent-orientation.md`:

- Check for open "agent-orientation cache lock" issue/comment
- If recent (<30 min): do not proceed
- If stale or none: take the lock, update, release with PR reference

---

# HARD RULES

- Orchestrator spawns workers; workers do not spawn more workers
- Max 3 workers per orchestrator run
- Never ignore active claims
- Never force-push shared branches
- Never push directly to main
- When unsure: EXIT and file an `agent-feedback` issue

---

# SUCCESS =

- Each worker: one issue claimed without conflict, valid PR OR clear blocked report
- Orchestrator: summary table printed, workflow review completed
- Clean repository state
