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

## Identity

Construct your agent identity once at the start of your session:

```bash
HEX="$(echo $RANDOM | md5sum | head -c4)"
AGENT_ID="<your-model-short-name>-go-${HEX}"
# e.g. "opus-4-go-a3f1" or "sonnet-4-go-b7c2"
```

**ALL** GitHub comments (issues and PRs) MUST go through `.agent/gh-comment.sh`:
```bash
echo "your message" | .agent/gh-comment.sh issue <number> "$AGENT_ID"
echo "your message" | .agent/gh-comment.sh pr <number> "$AGENT_ID"
```

Never post bare `gh issue comment` or `gh pr comment` — always use the wrapper.
This ensures every comment is signed and traceable to the specific agent session.

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

POST signed comment:
```bash
echo "🤖 intending to work on this" | .agent/gh-comment.sh issue <number> "$AGENT_ID"
```

WAIT ~2 minutes

---

# STATE 5: VERIFY

Re-read comments

Extract all claims
Sort by timestamp in comment body

IF your claim is earliest:
  proceed

ELSE:
  POST signed: `echo "🤖 yielding to earlier claim" | .agent/gh-comment.sh issue <number> "$AGENT_ID"`
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
- Request reviews: `gh pr edit <number> --add-reviewer copilot`
- Post signed comment with PR link:
  ```bash
  echo "✅ PR opened: <url>. Copilot review requested." | .agent/gh-comment.sh issue <number> "$AGENT_ID"
  ```

## BLOCKED
- Post signed comment with details:
  ```bash
  echo "🤖 releasing issue — blocked: <what failed, what you tried, what is needed>" | .agent/gh-comment.sh issue <number> "$AGENT_ID"
  ```
- Mark blocked if label exists

## INVALID
- Post signed comment explaining why
- Close issue:
  ```bash
  echo "🤖 releasing issue — invalid: <reason>" | .agent/gh-comment.sh issue <number> "$AGENT_ID"
  ```

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
