---
description: Safely claim and complete one issue using a shared orientation cache
---

# Multi-Agent Orchestrator

You are the **orchestrator**. Your job:
1. Load orientation + process feedback (once)
2. Build a shortlist of up to 3 unclaimed, unblocked issues
3. Spawn one subagent per issue in parallel using the Agent tool
4. Report a summary of all outcomes + workflow improvement suggestions

If you cannot reliably perform any required step, EXIT safely.

## Autonomy

Run autonomously. Do NOT prompt the user for:
- Read-only / exploratory commands (git log, git status, gh issue/pr queries)
- Running tests (pytest)
- Creating branches, committing, pushing feature branches
- Opening/commenting on issues and PRs
- Any command whose purpose is understanding current state

Only pause for: product decisions, schema changes, billing, scope ambiguity (per CLAUDE.md).

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
  EXIT (do not spawn subagents -- bootstrap comes first)

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

# STATE 3: BUILD_SHORTLIST

List all open issues. For each, apply:

**Exclude if any of:**
- Labels: `icebox`, `agent-feedback`, `do-not-touch`, `blocked`
- Umbrella/tracker issues: #204, #177, #139
- External-action issues (require human action outside repo): #140, #141, #149, #150
- Active claim: an "intending to work" comment within the last 2 hours with no subsequent "releasing" comment

**Score each (higher = prefer):**
- `critical-path` label: +3
- `backend`, `data`, `infrastructure` labels: +2 each
- Title starts with `fix(` (bug fix): +2
- `product` label: +1

Select the **top 3 scoring** issues (or fewer if fewer qualify).

IF shortlist is empty:
  Print "No unclaimed, unblocked issues found. Exiting."
  EXIT

---

# STATE 4: SPAWN_SUBAGENTS

For each issue in the shortlist, spawn one subagent using the Agent tool.

**Configuration:**
- `isolation: "worktree"` -- mandatory, no exceptions
- Spawn all subagents simultaneously (parallel Agent tool calls in one response)
- Maximum 3 concurrent subagents (avoids GitHub secondary rate limits)

**Subagent prompt** (substitute the real issue number for ISSUE_NUMBER before spawning):

---
You are a focused implementation agent. Your ONLY job: claim and complete issue #ISSUE_NUMBER.

Read `.claude/agent-orientation.md` before doing anything else.

**Autonomy:** Run without asking permission for read-only commands, tests, commits, branches, or opening PRs. Only pause for: product decisions, schema changes, billing, scope ambiguity.

### CLAIM

Read issue #ISSUE_NUMBER comments:

  gh issue view ISSUE_NUMBER --comments --json comments

If an active "intending to work" comment exists within the last 2h with no "releasing" after it:
  Post "yielding -- active claim found on #ISSUE_NUMBER" and EXIT.

Otherwise, post your claim comment (use identity footer from orientation cache):

  intending to work on this at <current UTC timestamp in ISO 8601>

  -- go

While waiting ~2 minutes, do useful exploration:
- Read the issue body thoroughly
- Identify files to change (Glob, Grep, Read)
- Draft your implementation approach

### VERIFY

Re-read issue #ISSUE_NUMBER comments. Extract all claim timestamps from
"intending to work on this at <timestamp>" lines. Sort ascending.

IF your claim is NOT the earliest: post "yielding to earlier claim" and EXIT.

### CHECKPOINT

Before writing any code, confirm ALL are true:
- Claim posted
- ~2 min elapsed
- My claim is the earliest
- Issue not already covered by an existing open PR

IF any false: EXIT cleanly.

### WORK

Create a branch per orientation naming convention:

  git checkout -b worktree-<type>-ISSUE_NUMBER-<slug>

Then:
- Read existing code before modifying it
- Follow all conventions from agent-orientation.md
- Claim shared files if needed: `.agent/claim.sh claim file:<path> claude-sonnet-<session>`
- Run: `make check` (lint + unit tests via local .venv, no Docker)
- Fix all failures before opening a PR

Never: force-push, push to main, open a PR with failing tests.

### COMPLETE

**DONE** -- open PR and queue for merge:

  gh pr create --title "<type>(<scope>): <description> (#ISSUE_NUMBER)" --body "$(cat <<'EOF'
  ## Summary
  - <bullet>

  Closes #ISSUE_NUMBER

  ## Test plan
  - [x] <item>

  Generated with Claude Code
  EOF
  )"

  gh pr merge <PR_NUMBER> --rebase --auto

Then comment on issue #ISSUE_NUMBER with PR link and summary, ending with:

  -- go

**BLOCKED** -- post what failed, what you tried, what is needed. Comment "releasing issue -- go" and EXIT.

**INVALID** -- explain why, close issue, comment "releasing issue -- go".
---

*(end of subagent prompt)*

---

# STATE 5: REPORT

After all subagents complete, print a summary table:

  ## /go run summary

  | Issue | Title | Outcome | PR |
  |-------|-------|---------|-----|
  | #N    | ...   | DONE / BLOCKED / YIELDED / INVALID | #PR or reason |

Then add a **Workflow improvements** section with concrete suggestions from this run,
or explicitly state "No improvements needed this run." This section is mandatory.

---

# CACHE LOCK (orientation updates only)

Before editing `.claude/agent-orientation.md`:
- Search GitHub for an open issue titled "agent-orientation cache lock" created <30 min ago
- If found and recent: do not proceed
- If absent or stale: create the lock issue, update cache, close the lock issue

---

# HARD RULES

- Never spawn more than 3 subagents per run
- Never skip the 2-minute claim wait inside a subagent
- Never force-push shared branches
- Never modify the default branch directly
- Never override documented conventions
- When unsure: EXIT or file an `agent-feedback` issue

---

# SUCCESS =

- Shortlist built cleanly
- Up to 3 subagents spawned in parallel
- Each subagent: DONE, BLOCKED, YIELDED, or INVALID
- Summary table printed
- Workflow improvements section included
