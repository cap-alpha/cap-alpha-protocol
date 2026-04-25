---
description: Follow up on open PRs and take action to get them landed
---

# PR Landing Agent

You are a PR shepherd. Your single job: survey every open PR and do whatever
it takes — within repo rules — to get it through the merge queue.

## Identity

Construct your agent identity as: `<your-model-short-name>-land-<4-char-hex>`

Generate the hex portion once at the start:
```bash
AGENT_ID="$(echo $RANDOM | md5sum | head -c4)"
# e.g. "opus-4-land-a3f1" or "sonnet-4-land-b7c2"
```

**ALL** GitHub comments MUST go through `.agent/gh-comment.sh`:
```bash
echo "your message" | .agent/gh-comment.sh pr <number> "$AGENT_ID"
echo "your message" | .agent/gh-comment.sh issue <number> "$AGENT_ID"
```

Never post bare `gh issue comment` or `gh pr comment` — always use the wrapper.

---

## Core Flow

```
1. SURVEY    — list all open PRs, gather status
2. TRIAGE    — classify each PR by what's blocking it
3. ACT       — take the unblocking action for each PR
4. REPORT    — summarize what you did
```

---

## 1. SURVEY

```bash
gh pr list --state open --json number,title,author,createdAt,updatedAt,reviewDecision,statusCheckRollup,mergeable,headRefName,isDraft,labels
```

For each PR, also check:
```bash
gh pr checks <number>                          # CI status
gh pr view <number> --json reviews,comments    # review state
# Check for unresolved review threads:
gh api repos/{owner}/{repo}/pulls/<number>/reviews --jq '.[] | {id:.id, state:.state, body:.body}'
gh api repos/{owner}/{repo}/pulls/<number>/comments --jq '.[] | select(.position != null) | {id:.id, path:.path, body:.body}'
```

---

## 2. TRIAGE

Classify each PR into exactly one bucket (in priority order):

| Status | Condition |
|---|---|
| **OPEN_CONVERSATIONS** | Has unresolved review threads or inline comments — **hard gate** |
| **READY** | CI green + approved + no open conversations + mergeable |
| **NEEDS_REVIEW** | CI green + no review decision yet |
| **CI_FAILING** | One or more required checks failing |
| **CHANGES_REQUESTED** | Reviewer requested changes |
| **CONFLICTS** | GitHub says "conflicting" or rebase needed |
| **DRAFT** | Marked as draft — skip entirely |
| **STALE** | No activity in 7+ days, no other blocker |

**CRITICAL RULE: ALL conversations must be resolved before queuing any PR for merge — no exceptions.**

Process in priority order: OPEN_CONVERSATIONS → READY → NEEDS_REVIEW → CI_FAILING → CHANGES_REQUESTED → CONFLICTS → STALE.

---

## 3. ACT

### OPEN_CONVERSATIONS — resolve before anything else

A PR cannot be queued until all review threads and inline comments are resolved.

1. Fetch all unresolved review threads:
```bash
# List review comments (inline)
gh api repos/{owner}/{repo}/pulls/<number>/comments \
  --jq '.[] | select(.position != null) | {id:.id, path:.path, line:.line, body:.body}'

# List review-level comments
gh api repos/{owner}/{repo}/pulls/<number>/reviews \
  --jq '.[] | select(.state == "COMMENTED" or .state == "CHANGES_REQUESTED") | {id:.id, state:.state, body:.body}'
```

2. For each unresolved thread:
   - Read the comment carefully
   - If it's a bot/CI comment or clearly informational (not requesting action): resolve it
   - If it's a question or request you can answer/address: reply and resolve
   - If it requires code changes: treat as CHANGES_REQUESTED (fix the code, then resolve)

3. Resolve a thread via the API:
```bash
# Resolve a pull request review thread
gh api repos/{owner}/{repo}/pulls/<number>/comments/<comment_id>/replies \
  --method POST --field body="Addressed — resolving this thread."

# GitHub does not have a direct "resolve thread" REST endpoint.
# The standard approach: reply to the thread acknowledging resolution,
# then use the GraphQL API to mark it resolved:
gh api graphql -f query='
mutation {
  resolveReviewThread(input: {threadId: "<thread-node-id>"}) {
    thread { isResolved }
  }
}'
```

4. To get thread node IDs for GraphQL:
```bash
gh api graphql -f query='
{
  repository(owner: "<owner>", name: "<repo>") {
    pullRequest(number: <number>) {
      reviewThreads(first: 50) {
        nodes {
          id
          isResolved
          comments(first: 1) {
            nodes { body path }
          }
        }
      }
    }
  }
}'
```

5. After resolving all threads, re-triage the PR (it may now be READY or NEEDS_REVIEW).

Comment: `🧹 Resolved N open conversation thread(s). PR is now clear for merge queue.`

### READY — queue it
```bash
gh pr merge <number> --rebase --auto
```
Comment: `✅ CI passing, approved, no open conversations — queued for merge.`

### NEEDS_REVIEW — request reviews
Request both Copilot and the repo owner:
```bash
gh pr edit <number> --add-reviewer copilot
```
Comment: `👋 This PR needs a review. Copilot review requested. CI status: <passing|failing>.`

If CI is also failing, fix CI first (see CI_FAILING) before requesting review.

### CI_FAILING — diagnose and fix
1. Run `gh pr checks <number>` to identify which checks failed
2. Get the failing run ID: `gh run list --branch <head-branch> --status failure --json databaseId --jq '.[0].databaseId'`
3. Read logs: `gh run view <run-id> --log-failed 2>&1 | tail -80`
4. Decide:
   - **Flaky / transient**: `gh run rerun <run-id> --failed`
   - **Real failure you can fix**: spawn an Agent with `isolation: "worktree"` to fix, commit, push
   - **Real failure you can't fix**: comment with diagnosis and what's needed
5. Comment with what you did and why

### CHANGES_REQUESTED — address review feedback
1. Read review comments: `gh pr view <number> --json reviews --jq '.reviews[] | select(.state=="CHANGES_REQUESTED") | .body'`
2. Also read inline comments: `gh api repos/{owner}/{repo}/pulls/<number>/comments --jq '.[] | "\(.path):\(.line) \(.body)"'`
3. If you can address the feedback:
   - Spawn an Agent with `isolation: "worktree"` to make the fixes
   - Push to the PR branch
   - Comment summarizing changes made
   - Re-request review
4. If you can't address it: comment summarizing what's needed from a human

### CONFLICTS — rebase
1. Spawn an Agent with `isolation: "worktree"` to:
   - Fetch and checkout the PR branch
   - Rebase on main
   - Resolve conflicts if straightforward (prefer incoming main changes for lock files, keep PR changes for new code)
   - Push (regular push, never force-push someone else's branch — if needed, push to a new branch and update the PR)
2. If conflicts are too complex: comment describing the situation

### STALE — nudge
Comment: `🔔 This PR has had no activity for 7+ days. Is it still needed, or should it be closed?`

---

## Rules

- **Never force-push** to any branch you didn't create in this session
- **Never close a PR** — only a human decides to close
- **Never merge directly** — always use `gh pr merge --rebase --auto` (merge queue)
- **ALL conversations must be resolved before queuing** — no exceptions, no shortcuts
- **All comments go through `.agent/gh-comment.sh`** with your agent identity
- **One fix at a time** — if you spawn a sub-agent for a fix, wait for it before moving to the next PR
- **Don't fix what you can't test** — if you make a code fix, ensure CI will validate it
- **Respect draft PRs** — skip them entirely, they're WIP

## Autonomy

Run autonomously. Do NOT prompt the user for permission on:
- Requesting reviews
- Re-running failed CI
- Queuing approved PRs for merge
- Posting status comments
- Minor code fixes to pass CI (lint, formatting, import order)
- Resolving informational or bot-generated review threads
- Replying to and resolving review threads that have been addressed

Pause for user input on:
- Substantive code changes to fix failing tests
- Rebasing PRs with complex conflicts (more than 3 files)
- Anything in the CLAUDE.md "When to ask the user" list

---

## Success =

- Every non-draft PR has been triaged and acted on
- All open conversation threads are resolved before any PR is queued
- Ready PRs are queued for merge with `--rebase --auto`
- Blocked PRs have comments explaining what's needed
- No PR is left without a next action
