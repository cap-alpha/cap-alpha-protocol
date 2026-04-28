---
description: Protocol for resolving Copilot/reviewer threads on a PR — fetch, fix, resolve via GraphQL
---

# PR review-thread resolution skill

Reviewer threads (especially Copilot) come back as a JSON list with stable IDs.
The merge queue's `required_review_thread_resolution` rule blocks landing
until every thread is `isResolved: true`. This skill is the canonical recipe.

## Step 1 — Pull only the unresolved threads

```bash
gh api graphql -f query='query { repository(owner: "cap-alpha", name: "cap-alpha-protocol") { pullRequest(number: <N>) { reviewThreads(first: 100) { nodes { id isResolved path line comments(first: 1) { nodes { body author { login } } } } } } } }' \
  --jq '.data.repository.pullRequest.reviewThreads.nodes | map(select(.isResolved == false)) | .[] | {id, path, line, body: .comments.nodes[0].body[0:400]}'
```

REST endpoints (`/pulls/<n>/comments`) **do not expose `isResolved`** — they
will return resolved threads too, wasting subagent attention. Always use the
GraphQL `reviewThreads` query.

## Step 2 — Fix in the PR's worktree

- Find or create a worktree on the PR branch:
  ```bash
  gh pr view <N> --json headRefName -q .headRefName
  git worktree list | grep <branch>     # or: git worktree add .claude/worktrees/<name> -b <branch> origin/<branch>
  ```
- Apply the requested change. When a Copilot comment includes a code suggestion
  block, prefer that exact text unless it conflicts with another thread.
- For each comment that asks for a test, **write the test** — Copilot is
  consistently right that test gaps need filling.
- `make check` (or the equivalent ruff format/check + pytest subset).
- Commit with a message that names each thread you addressed.
- `git push`.

## Step 3 — Resolve threads via GraphQL

```bash
gh api graphql -f query='mutation($id: ID!) { resolveReviewThread(input: {threadId: $id}) { thread { id isResolved } } }' -f id="<THREAD_ID>"
```

For bulk resolution after a sweep:

```bash
gh api graphql -f query='query { repository(owner: "cap-alpha", name: "cap-alpha-protocol") { pullRequest(number: <N>) { reviewThreads(first: 100) { nodes { id isResolved } } } } }' \
  --jq '.data.repository.pullRequest.reviewThreads.nodes | map(select(.isResolved == false)) | .[].id' \
  | while read tid; do
      gh api graphql -f query='mutation($id: ID!) { resolveReviewThread(input: {threadId: $id}) { thread { isResolved } } }' -f id="$tid"
    done
```

## Step 4 — Confirm and queue

- Re-query unresolved count. It must be `0`.
- Confirm auto-merge: `gh pr merge <N> --rebase --auto` (rebase only — never
  squash, per `feedback_rebase_only.md`).
- Never `gh pr review --approve` your own work; the user approves.

## When to dispatch a subagent vs do it inline

- **>2 threads, or threads spanning >1 file**: dispatch a Sonnet subagent with
  the worktree path, the thread ID list, and each comment body. Resolve threads
  in the subagent prompt — don't make a second turn for it.
- **1 trivial thread (typo, unused import)**: just fix it inline.
- **A thread asking a product question**: surface to the user, do not guess.

## Heuristics on what Copilot is usually right about

- Schema/contract drift — when a new field is filtered on but never emitted
  by the provider schema, Copilot catches that almost every time.
- Test gaps — if Copilot asks for a test, write the test. Don't argue.
- Hardcoded project IDs / dataset names — convert to `{project_id}` placeholder
  to match other scripts in `pipeline/scripts/`.

## Heuristics on what Copilot is sometimes wrong about

- "Consider extracting a shared helper" — only do this if the duplication is
  both real and load-bearing. Two short functions ≠ premature abstraction.
- "This could grow expensive" — usually fine to defer with a TODO unless the
  table is already known to be large.
- "Update PR description" — do it if the description is genuinely misleading
  about scope, but don't rewrite it just because Copilot asked.

When you decide a Copilot suggestion is wrong, **resolve the thread anyway**
with a one-line reply via `gh pr comment` explaining why. Don't leave it open.
