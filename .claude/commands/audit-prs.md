---
description: Audit every open PR for unresolved review threads before reporting status
---

# /audit-prs

Before ever telling the user a PR is "blocked" or "waiting," prove every reviewer
thread is resolved across the open backlog. Reporting `mergeStateStatus=BLOCKED`
without a thread audit shifts triage onto the user — that's the rule.

## Procedure

1. **List open PRs**
   ```bash
   gh pr list --state open --limit 50 --json number,title,reviewDecision,mergeStateStatus
   ```

2. **For each PR, count unresolved threads** via GraphQL (REST `/comments` does
   not expose thread resolution state):
   ```bash
   for n in <numbers>; do
     gh api graphql -f query="query { repository(owner: \"cap-alpha\", name: \"cap-alpha-protocol\") { pullRequest(number: $n) { reviewThreads(first: 100) { nodes { isResolved } } reviewDecision mergeStateStatus } } }" \
       --jq '"PR #'$n': \(.data.repository.pullRequest.reviewThreads.nodes | map(select(.isResolved == false)) | length) unresolved | review=\(.data.repository.pullRequest.reviewDecision // "none") | merge=\(.data.repository.pullRequest.mergeStateStatus)"'
   done
   ```

3. **Triage non-zero counts**
   - For each PR with `>0` unresolved: pull the actual thread bodies and IDs:
     ```bash
     gh api graphql -f query='query { repository(owner: "cap-alpha", name: "cap-alpha-protocol") { pullRequest(number: <N>) { reviewThreads(first: 100) { nodes { id isResolved path line comments(first: 1) { nodes { body author { login } } } } } } } }' \
       --jq '.data.repository.pullRequest.reviewThreads.nodes | map(select(.isResolved == false))'
     ```
   - Dispatch a Sonnet subagent per PR with: branch, worktree path, the thread
     ID list, and the comment bodies. The subagent fixes, pushes, and resolves
     each thread via the GraphQL mutation in `pr-comments` skill.

4. **Verify clean state**
   - Re-run step 2. Confirm `0 unresolved` for every PR before any "blocked" status update.
   - `BLOCKED` is fine to report only when threads are clean — that means the
     blocker is genuinely CI / approval / merge-queue, not pending review work.

## Anti-pattern

- ❌ Reporting "PR #N is blocked" while comments sit unaddressed.
- ❌ Using `gh pr view --json reviews` alone — that returns review *summaries*, not thread resolution state.
- ❌ Trusting `gh pr view --json comments` — those are issue comments, not review threads.

## Exit criteria

A status update is allowed once: every open PR shows `0 unresolved`, and the
remaining `BLOCKED`/`UNKNOWN` states are due to CI, approval, or merge queue —
which the user can see at a glance.
