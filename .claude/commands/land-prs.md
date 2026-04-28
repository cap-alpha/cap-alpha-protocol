---
description: End-to-end landing flow for the open PR backlog — audit, fix, resolve, queue, verify
---

# /land-prs

Drive every open PR to merged or to a clean blocker the user can see at a
glance. Composes `/audit-prs` (thread sweep) with the per-PR fix-and-resolve
loop. Run autonomously — no permission needed for diagnostic commands.

## Procedure

1. **Audit** — run `/audit-prs` to get the unresolved-thread map.

2. **Fix in parallel** — for each PR with unresolved threads, dispatch a
   Sonnet subagent (fan out — they're independent). Each subagent must:
   - Work in the PR's existing worktree (find via `git worktree list` or
     create one off the PR branch with `git worktree add`)
   - Apply the requested fix per thread; add tests where the comment asks
   - Run `make lint` (or `ruff format` + `ruff check`) and the relevant
     pytest subset until green
   - Commit with a message that names each thread it addresses
   - `git push`
   - Resolve each thread via the GraphQL mutation in the `pr-comments` skill
   - Confirm `gh pr merge <n> --rebase --auto` is queued
   - Never approve a PR — only the user does that

3. **Cherry-pick stale-base bleeds** — if a PR rebase fails on commits that
   already landed on main as different SHAs (the "stale-base bleed"), recover
   it cleanly:
   ```bash
   git fetch origin main
   git reset --hard origin/main
   git cherry-pick <unique-commit-sha>
   git push --force-with-lease
   ```
   Only do this for the unique commits in the branch — never reset away work.

4. **Re-audit** — run `/audit-prs` again. Every PR must show `0 unresolved`.
   Only after this is the loop allowed to report status.

5. **Watch CI** — for PRs queued via `--rebase --auto`, the merge queue
   handles the rest. If a PR shows `mergeStateStatus=DIRTY`, that's a
   genuine merge conflict — re-dispatch a subagent to rebase it.

## What to never do

- Squash. Always `--rebase --auto` per `feedback_rebase_only.md`.
- Direct merge. Always go through the merge queue per CLAUDE.md.
- Force-push to `main`. Force-push only with `--force-with-lease` on feature branches.
- Approve the user's own PRs as themselves. The user approves; we queue.
- Report "blocked" before the audit is clean. See `feedback_never_report_blocked_with_unresolved_comments.md`.

## Output format

When the loop terminates, surface a tight table:

```
PR  | title (≤60 chars)              | unresolved | review     | merge
----+--------------------------------+------------+------------+--------
336 | fix(pipeline): ...             | 0          | APPROVED   | CLEAN
324 | feat(sources): ...             | 0          | none       | BLOCKED (CI)
```

Plus one line per still-open thread (none if clean). Nothing else.
